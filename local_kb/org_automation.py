from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from local_kb.adoption import record_exchange_hash, recorded_exchange_hashes
from local_kb.card_ids import installation_short_label
from local_kb.feedback import build_observation, record_observation
from local_kb.github_repo_config import create_github_pull_request_for_branch
from local_kb.maintenance_lanes import acquire_lane_lock, release_lane_lock
from local_kb.org_checks import check_organization_repository
from local_kb.org_contribution import current_git_branch, prepare_organization_import_branch, push_organization_branch
from local_kb.org_maintenance import build_organization_maintenance_report
from local_kb.org_outbox import _organization_exchange_hashes, build_organization_outbox, organization_outbox_dir
from local_kb.org_sources import _run_git, clone_or_fetch_organization_repo, utc_timestamp, validate_organization_repo
from local_kb.search import search_entries
from local_kb.settings import (
    load_desktop_settings,
    maintenance_participation_status_from_settings,
    organization_sources_from_settings,
    save_desktop_settings,
)
from local_kb.store import load_yaml_file


ORG_AUTOMATION_ROUTE = "system/knowledge-library/organization"
ORG_LANE_POLICY = {
    "incoming_lane": "kb/imports",
    "exchange_surface": "kb/main",
    "local_download_primary_path": "kb/main",
    "local_download_excluded_paths": ["kb/imports"],
    "contribution_writes": ["kb/imports"],
    "maintenance_moves_reviewed_cards_to": "kb/main",
    "legacy_compatibility_paths": ["kb/trusted", "kb/candidates"],
}


def _preflight(repo_root: Path, *, query: str) -> dict[str, Any]:
    results = search_entries(
        repo_root,
        query=query,
        path_hint=ORG_AUTOMATION_ROUTE,
        top_k=5,
    )
    return {
        "route_hint": ORG_AUTOMATION_ROUTE,
        "query": query,
        "matched_entry_ids": [str(item.data.get("id") or item.path.stem) for item in results],
        "matched_entry_count": len(results),
    }


def _record_postflight(
    repo_root: Path,
    *,
    task_summary: str,
    preflight: dict[str, Any],
    outcome: str,
    comment: str,
    action_taken: str,
    observed_result: str,
    operational_use: str,
    agent_name: str,
    suggested_action: str = "none",
) -> str:
    observation = build_observation(
        task_summary=task_summary,
        route_hint=ORG_AUTOMATION_ROUTE,
        entry_ids=",".join(preflight.get("matched_entry_ids", [])),
        hit_quality="hit" if preflight.get("matched_entry_ids") else "none",
        outcome=outcome,
        comment=comment,
        scenario="Scheduled organization KB automation ran against a locally configured organization source.",
        action_taken=action_taken,
        observed_result=observed_result,
        operational_use=operational_use,
        reuse_judgment="Reusable as an audit trail for organization KB automation behavior.",
        suggested_action=suggested_action,
        source_kind="automation",
        agent_name=agent_name,
        project_ref="organization-kb",
        workspace_root=str(repo_root),
    )
    path = record_observation(repo_root, observation)
    return str(path)


def _first_organization_source(repo_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    settings = load_desktop_settings(repo_root)
    sources = organization_sources_from_settings(settings)
    if not sources:
        return {}, [], settings
    return sources[0], sources, settings


def _checkout_organization_base_branch(org_root: Path, *, base_branch: str = "main") -> dict[str, Any]:
    org_root = Path(org_root)
    if not (org_root / ".git").exists():
        return {"attempted": False, "ok": True, "reason": "organization mirror is not a git checkout"}
    status = _run_git(["status", "--porcelain"], cwd=org_root)
    if status.returncode != 0:
        return {"attempted": True, "ok": False, "errors": [status.stderr.strip() or status.stdout.strip()]}
    if status.stdout.strip():
        return {"attempted": True, "ok": False, "errors": ["organization mirror has uncommitted changes"]}
    current = current_git_branch(org_root)
    if current == base_branch:
        return {"attempted": False, "ok": True, "branch": current}
    checkout = _run_git(["checkout", base_branch], cwd=org_root)
    if checkout.returncode != 0:
        return {"attempted": True, "ok": False, "branch": current, "errors": [checkout.stderr.strip() or checkout.stdout.strip()]}
    return {"attempted": True, "ok": True, "branch": base_branch, "previous_branch": current}


def _sync_first_organization_source(
    repo_root: Path,
    settings: dict[str, Any],
    *,
    base_branch: str = "main",
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    sources = organization_sources_from_settings(settings)
    if not sources:
        return {}, [], settings, {"attempted": False, "ok": False, "reason": "no validated organization source"}

    source = sources[0]
    org_root = Path(str(source.get("path") or ""))
    repo_url = str(source.get("repo_url") or "").strip()
    sync_result: dict[str, Any] = {"attempted": False, "ok": True, "action": "none", "commit": str(source.get("source_commit") or "")}
    base_checkout = _checkout_organization_base_branch(org_root, base_branch=base_branch)
    if not base_checkout.get("ok"):
        sync_result.update(
            {
                "attempted": True,
                "ok": False,
                "action": "checkout-base",
                "errors": base_checkout.get("errors") or ["failed to checkout organization base branch"],
                "base_checkout": base_checkout,
            }
        )
        return source, sources, settings, sync_result
    if repo_url and ((org_root / ".git").exists() or not org_root.exists()):
        sync_result = clone_or_fetch_organization_repo(repo_url, org_root)
        sync_result["attempted"] = True
    else:
        validation = validate_organization_repo(org_root)
        sync_result.update(
            {
                "attempted": False,
                "ok": bool(validation.get("ok")),
                "action": "validate-local-mirror",
                "errors": validation.get("errors") or [],
                "commit": str(validation.get("commit") or source.get("source_commit") or ""),
            }
        )
    sync_result["base_checkout"] = base_checkout

    validation = validate_organization_repo(org_root)
    if validation.get("ok"):
        updated = dict(settings)
        organization = dict(updated.get("organization") if isinstance(updated.get("organization"), dict) else {})
        organization["last_sync_commit"] = str(validation.get("commit") or sync_result.get("commit") or "")
        organization["last_sync_at"] = utc_timestamp()
        organization["validation_status"] = "valid"
        organization["validated"] = True
        organization["organization_id"] = str(validation.get("organization_id") or organization.get("organization_id") or "")
        updated["organization"] = organization
        save_desktop_settings(repo_root, updated)
        settings = load_desktop_settings(repo_root)
        sources = organization_sources_from_settings(settings)
        source = sources[0] if sources else source
    return source, sources, settings, sync_result


def _commit_and_push_organization_maintenance(
    repo_root: Path,
    org_root: Path,
    *,
    changed_files: list[str] | None = None,
    push: bool = True,
    remote: str = "origin",
    base_branch: str = "main",
    repo_url: str = "",
) -> dict[str, Any]:
    org_root = Path(org_root)
    if not (org_root / ".git").exists():
        return {"attempted": False, "ok": True, "reason": "organization mirror is not a git checkout"}

    status = _run_git(["status", "--porcelain"], cwd=org_root)
    if status.returncode != 0:
        return {"attempted": True, "ok": False, "errors": [status.stderr.strip() or status.stdout.strip()]}
    if not status.stdout.strip():
        return {"attempted": False, "ok": True, "reason": "no organization maintenance changes to commit"}

    branch = current_git_branch(org_root)
    if not branch or branch in {base_branch, "master"}:
        stamp = utc_timestamp().replace(":", "").replace("-", "").replace("Z", "")
        branch = f"maintenance/{installation_short_label(repo_root)}/{stamp}"
        checkout = _run_git(["checkout", "-B", branch], cwd=org_root)
        if checkout.returncode != 0:
            return {"attempted": True, "ok": False, "errors": [checkout.stderr.strip() or checkout.stdout.strip()], "branch": branch}

    stage_files = [item for item in (changed_files or []) if item and not item.startswith("/") and ".." not in Path(item).parts]
    if not stage_files:
        return {"attempted": False, "ok": False, "reason": "no reviewed maintenance paths to stage"}

    add = _run_git(["add", "--", *stage_files], cwd=org_root)
    if add.returncode != 0:
        return {"attempted": True, "ok": False, "errors": [add.stderr.strip() or add.stdout.strip()], "branch": branch}
    commit = _run_git(
        [
            "-c",
            "user.name=Khaos Brain",
            "-c",
            "user.email=khaos-brain@example.invalid",
            "commit",
            "-m",
            "Apply organization KB maintenance review",
        ],
        cwd=org_root,
    )
    if commit.returncode != 0:
        message = commit.stderr.strip() or commit.stdout.strip()
        if "nothing to commit" not in message:
            return {"attempted": True, "ok": False, "errors": [message], "branch": branch}

    push_result: dict[str, Any] = {"pushed": False, "pull_request_url": "", "errors": []}
    if push:
        push_result = push_organization_branch(org_root, branch, remote=remote, base_branch=base_branch)
        if not push_result.get("ok"):
            return {
                "attempted": True,
                "ok": False,
                "errors": push_result.get("errors") or ["failed to push organization maintenance branch"],
                "branch": branch,
                "push": push_result,
            }
        auto_merge_labels = ["org-kb:auto-merge"] if _maintenance_pr_auto_merge_eligible(stage_files) else []
        push_result["pull_request"] = create_github_pull_request_for_branch(
            repo_url,
            branch=branch,
            base_branch=base_branch,
            title="Apply organization KB maintenance review",
            body=(
                "This PR contains organization maintenance changes that were produced by the reviewed "
                "organization Sleep-style cleanup loop."
            ),
            labels=auto_merge_labels,
        )
        if push_result["pull_request"].get("url"):
            push_result["pull_request_url"] = str(push_result["pull_request"]["url"])
        if push_result["pull_request"].get("attempted") and not push_result["pull_request"].get("ok"):
            return {
                "attempted": True,
                "ok": False,
                "errors": push_result["pull_request"].get("errors") or ["failed to create organization maintenance pull request"],
                "branch": branch,
                "push": push_result,
            }
    restore_base = _checkout_organization_base_branch(org_root, base_branch=base_branch)
    if not restore_base.get("ok"):
        return {
            "attempted": True,
            "ok": False,
            "errors": restore_base.get("errors") or ["failed to restore organization base branch after maintenance push"],
            "branch": branch,
            "push": push_result,
            "restore_base": restore_base,
            "pull_request_url": push_result.get("pull_request_url") or "",
        }

    return {
        "attempted": True,
        "ok": True,
        "branch": branch,
        "push": push_result,
        "restore_base": restore_base,
        "pull_request_url": push_result.get("pull_request_url") or "",
    }


def _organization_proposal_content_hash(path: Path) -> str:
    payload = load_yaml_file(path)
    proposal = payload.get("organization_proposal") if isinstance(payload.get("organization_proposal"), dict) else {}
    return str(proposal.get("content_hash") or "").strip()


def _maintenance_pr_auto_merge_eligible(changed_files: list[str]) -> bool:
    if not changed_files:
        return False
    has_audit = "maintenance/cleanup_audit.jsonl" in changed_files
    allowed_prefixes = ("kb/imports/", "kb/main/")
    allowed_exact = {"maintenance/cleanup_audit.jsonl"}
    return has_audit and all(path.startswith(allowed_prefixes) or path in allowed_exact for path in changed_files)


def _outbox_proposal_files(
    repo_root: Path,
    organization_id: str,
    organization_sources: list[dict[str, Any]] | None = None,
) -> list[Path]:
    outbox_dir = organization_outbox_dir(repo_root, organization_id)
    if not outbox_dir.exists():
        return []
    blocked_hashes = recorded_exchange_hashes(repo_root, {"downloaded", "used", "absorbed", "exported", "uploaded"})
    blocked_hashes.update(_organization_exchange_hashes(organization_sources, organization_id=organization_id))
    pending: list[Path] = []
    for path in sorted(outbox_dir.glob("*.yaml")):
        content_hash = _organization_proposal_content_hash(path)
        if content_hash and content_hash not in blocked_hashes:
            pending.append(path)
    return pending


def _clear_organization_outbox(repo_root: Path, organization_id: str) -> dict[str, Any]:
    outbox_dir = organization_outbox_dir(repo_root, organization_id)
    try:
        resolved = outbox_dir.resolve()
        allowed_root = (Path(repo_root) / "kb" / "outbox" / "organization").resolve()
        resolved.relative_to(allowed_root)
    except (OSError, ValueError):
        return {"attempted": False, "ok": False, "reason": "outbox path is outside the organization outbox root"}
    if not outbox_dir.exists():
        return {"attempted": False, "ok": True, "reason": "outbox already empty"}
    shutil.rmtree(outbox_dir)
    return {"attempted": True, "ok": True, "path": str(outbox_dir)}


def _maintenance_stage_paths(apply_result: dict[str, Any]) -> list[str]:
    paths: set[str] = set()
    for item in apply_result.get("applied") or []:
        if not isinstance(item, dict):
            continue
        for key in ("target_path", "updated_path"):
            value = str(item.get(key) or "").strip().replace("\\", "/")
            if value:
                paths.add(value)
    audit_path = str(apply_result.get("audit_path") or "").strip()
    if audit_path:
        try:
            paths.add(Path(audit_path).resolve().relative_to(Path(audit_path).parents[1].resolve()).as_posix())
        except (ValueError, IndexError):
            audit = Path(audit_path)
            if audit.parts[-2:] == ("maintenance", "cleanup_audit.jsonl"):
                paths.add("maintenance/cleanup_audit.jsonl")
    return sorted(paths)


def run_organization_contribution(
    repo_root: Path,
    *,
    dry_run: bool = False,
    prepare_branch: bool = True,
    contributor_id: str = "",
    branch_name: str = "",
    commit: bool = True,
    push: bool = True,
    remote: str = "origin",
    base_branch: str = "main",
    record_postflight: bool = True,
) -> dict[str, Any]:
    repo_root = Path(repo_root)
    source, sources, settings = _first_organization_source(repo_root)
    if not source:
        return {
            "ok": True,
            "skipped": True,
            "reason": "organization mode is not connected to a validated repository",
            "settings_gate": {
                "available": False,
                "mode": str(settings.get("mode") or "personal"),
                "organization_validated": bool(
                    (settings.get("organization") if isinstance(settings.get("organization"), dict) else {}).get(
                        "validated"
                    )
                ),
            },
            "settings_mode": str(settings.get("mode") or "personal"),
            "preflight": {},
            "postflight_recorded": False,
        }

    lane_lock = acquire_lane_lock(repo_root, "kb-org-contribute", run_id=f"org-contribute-{utc_timestamp()}")
    source, sources, settings, sync_result = _sync_first_organization_source(repo_root, settings, base_branch=base_branch)
    if not sync_result.get("ok"):
        result = {
            "ok": False,
            "skipped": False,
            "settings_gate": {
                "available": True,
                "mode": str(settings.get("mode") or "personal"),
                "organization_validated": True,
            },
            "organization_id": str(source.get("organization_id") or "").strip(),
            "source": source,
            "sync": sync_result,
            "preflight": {},
            "outbox": {},
            "branch": {"attempted": False},
            "postflight_recorded": False,
            "postflight_path": "",
        }
        result["lane_lock"] = lane_lock
        result["lock_release"] = release_lane_lock(repo_root, "kb-org-contribute", run_id=str(lane_lock.get("run_id") or ""))
        return result
    organization_id = str(source.get("organization_id") or "").strip()
    preflight = _preflight(
        repo_root,
        query="organization contribution outbox upload imports incoming lane main exchange surface content hash skill dependency",
    )
    outbox = build_organization_outbox(
        repo_root,
        organization_id=organization_id,
        dry_run=dry_run,
        organization_sources=sources,
    )
    branch_result: dict[str, Any] = {"attempted": False}
    pending_outbox_files = _outbox_proposal_files(repo_root, organization_id, sources)
    if outbox.get("ok") and prepare_branch and not dry_run and pending_outbox_files:
        branch_result = prepare_organization_import_branch(
            Path(str(source.get("path") or "")),
            organization_outbox_dir(repo_root, organization_id),
            contributor_id=contributor_id or installation_short_label(repo_root),
            branch_name=branch_name,
            commit=commit,
            push=push,
            remote=remote,
            base_branch=base_branch,
            proposal_files=pending_outbox_files,
        )
        branch_result["attempted"] = True
        if branch_result.get("ok"):
            branch_persisted = bool(branch_result.get("committed"))
            if branch_persisted:
                for proposal_file in pending_outbox_files:
                    payload = load_yaml_file(proposal_file)
                    proposal = payload.get("organization_proposal") if isinstance(payload.get("organization_proposal"), dict) else {}
                    content_hash = str(proposal.get("content_hash") or "").strip()
                    if not content_hash:
                        continue
                    record_exchange_hash(
                        repo_root,
                        content_hash,
                        direction="exported",
                        organization_id=organization_id,
                        source_repo=str(source.get("repo_url") or ""),
                        source_path=str(proposal.get("source_path") or ""),
                        local_path=str(proposal_file),
                        entry_id=str(payload.get("id") or proposal_file.stem),
                    )
                    if (branch_result.get("push") or {}).get("pushed"):
                        record_exchange_hash(
                            repo_root,
                            content_hash,
                            direction="uploaded",
                            organization_id=organization_id,
                            source_repo=str(source.get("repo_url") or ""),
                            source_path=str(proposal.get("source_path") or ""),
                            local_path=str(proposal_file),
                            entry_id=str(payload.get("id") or proposal_file.stem),
                        )
            created_files = [str(item) for item in branch_result.get("created_files") or []]
            org_check = check_organization_repository(Path(str(source.get("path") or "")), changed_files=created_files)
            branch_result["organization_check"] = {
                "ok": bool(org_check.get("ok")),
                "auto_merge_eligible": bool(org_check.get("auto_merge_eligible")),
                "auto_merge_blockers": org_check.get("auto_merge_blockers") or [],
            }
            auto_merge_labels = ["org-kb:auto-merge"] if org_check.get("auto_merge_eligible") else []
            if (branch_result.get("push") or {}).get("pushed"):
                branch_result["pull_request"] = create_github_pull_request_for_branch(
                    str(source.get("repo_url") or ""),
                    branch=str(branch_result.get("branch") or ""),
                    base_branch=base_branch,
                    title="Add organization KB import proposals",
                    body=(
                        "This PR uploads local trusted experience to the organization import lane. "
                        "Organization maintenance will decide what enters main."
                    ),
                    labels=auto_merge_labels,
                )
                if branch_result["pull_request"].get("url"):
                    branch_result["pull_request_url"] = str(branch_result["pull_request"]["url"])
                if branch_result["pull_request"].get("attempted") and not branch_result["pull_request"].get("ok"):
                    branch_result["ok"] = False
                    branch_result.setdefault("errors", []).extend(branch_result["pull_request"].get("errors") or [])
            branch_result["restore_base"] = _checkout_organization_base_branch(
                Path(str(source.get("path") or "")),
                base_branch=base_branch,
            )
            if not branch_result["restore_base"].get("ok"):
                branch_result["ok"] = False
                branch_result.setdefault("errors", []).extend(branch_result["restore_base"].get("errors") or [])
            elif branch_persisted:
                branch_result["clear_outbox"] = _clear_organization_outbox(repo_root, organization_id)
                if not branch_result["clear_outbox"].get("ok"):
                    branch_result["ok"] = False
                    branch_result.setdefault("errors", []).append(
                        str(branch_result["clear_outbox"].get("reason") or "failed to clear organization outbox after upload")
                    )

    ok = bool(outbox.get("ok")) and bool(branch_result.get("ok", True))
    postflight_path = ""
    if record_postflight and not dry_run:
        postflight_path = _record_postflight(
            repo_root,
            task_summary="Organization KB contribution automation",
            preflight=preflight,
            outcome=(
                f"created={outbox.get('created_count', 0)} skipped={outbox.get('skipped_count', 0)} "
                f"sync_attempted={bool(sync_result.get('attempted'))} branch_attempted={bool(branch_result.get('attempted'))} "
                f"pushed={bool((branch_result.get('push') or {}).get('pushed'))}"
            ),
            comment="Organization contribution automation synchronized the organization mirror, inspected local shareable cards, and uploaded eligible proposals to the organization import lane when possible.",
            action_taken="Read desktop organization settings, synchronized the organization source, ran content-hash-gated organization outbox export, prepared an import branch under kb/imports, and pushed it when enabled.",
            observed_result=f"Outbox created {outbox.get('created_count', 0)} proposal(s).",
            operational_use="Use this audit event to confirm scheduled contribution automation is syncing first, avoiding repeated exchanged hashes, writing only imports, and leaving main movement to organization maintenance.",
            agent_name="kb-organization-contribute",
        )

    result = {
        "ok": ok,
        "skipped": False,
        "settings_gate": {
            "available": True,
            "mode": str(settings.get("mode") or "personal"),
            "organization_validated": True,
        },
        "organization_id": organization_id,
        "source": source,
        "sync": sync_result,
        "lane_policy": ORG_LANE_POLICY,
        "preflight": preflight,
        "outbox": outbox,
        "branch": branch_result,
        "postflight_recorded": bool(postflight_path),
        "postflight_path": postflight_path,
    }
    result["lane_lock"] = lane_lock
    result["lock_release"] = release_lane_lock(repo_root, "kb-org-contribute", run_id=str(lane_lock.get("run_id") or ""))
    return result


def run_organization_maintenance(
    repo_root: Path,
    *,
    push: bool = True,
    remote: str = "origin",
    base_branch: str = "main",
    record_postflight: bool = True,
) -> dict[str, Any]:
    repo_root = Path(repo_root)
    settings = load_desktop_settings(repo_root)
    participation = maintenance_participation_status_from_settings(settings)
    sources = organization_sources_from_settings(settings)
    if not participation.get("available") or not sources:
        return {
            "ok": True,
            "skipped": True,
            "reason": str(participation.get("reason") or "organization maintenance participation is not available"),
            "settings_gate": {
                "available": False,
                "mode": str(settings.get("mode") or "personal"),
                "organization_validated": bool(
                    (settings.get("organization") if isinstance(settings.get("organization"), dict) else {}).get(
                        "validated"
                    )
                ),
                "maintenance_requested": bool(participation.get("requested")),
            },
            "participation": participation,
            "preflight": {},
            "postflight_recorded": False,
        }

    lane_lock = acquire_lane_lock(repo_root, "kb-org-maintenance", run_id=f"org-maintenance-{utc_timestamp()}")
    source, sources, settings, sync_result = _sync_first_organization_source(repo_root, settings, base_branch=base_branch)
    if not sync_result.get("ok"):
        result = {
            "ok": False,
            "skipped": False,
            "settings_gate": {
                "available": True,
                "mode": str(settings.get("mode") or "personal"),
                "organization_validated": True,
                "maintenance_requested": bool(participation.get("requested")),
            },
            "organization_id": str(source.get("organization_id") or "").strip(),
            "source": source,
            "participation": participation,
            "sync": sync_result,
            "preflight": {},
            "report": {},
            "maintenance_branch": {"attempted": False},
            "postflight_recorded": False,
        }
        result["lane_lock"] = lane_lock
        result["lock_release"] = release_lane_lock(repo_root, "kb-org-maintenance", run_id=str(lane_lock.get("run_id") or ""))
        return result
    organization_id = str(source.get("organization_id") or "").strip()
    preflight = _preflight(
        repo_root,
        query="organization maintenance review imports main exchange surface legacy compatibility skills merge split auto merge",
    )
    report = build_organization_maintenance_report(
        Path(str(source.get("path") or "")),
        repo_root=repo_root,
        organization_id=organization_id,
        apply_reviewed_cleanup=True,
    )
    maintenance_branch: dict[str, Any] = {"attempted": False}
    cleanup = report.get("cleanup") if isinstance(report.get("cleanup"), dict) else {}
    apply_result = cleanup.get("apply") if isinstance(cleanup.get("apply"), dict) else {}
    post_apply_check = cleanup.get("post_apply_check") if isinstance(cleanup.get("post_apply_check"), dict) else {}
    applied_count = int(apply_result.get("applied_count") or 0)
    if applied_count > 0:
        maintenance_branch = _commit_and_push_organization_maintenance(
            repo_root,
            Path(str(source.get("path") or "")),
            changed_files=_maintenance_stage_paths(apply_result),
            push=push,
            remote=remote,
            base_branch=base_branch,
            repo_url=str(source.get("repo_url") or ""),
        )
    postflight_path = ""
    if record_postflight:
        postflight_path = _record_postflight(
            repo_root,
            task_summary="Organization KB maintenance automation",
            preflight=preflight,
            outcome=(
                f"main_active_count={report.get('main_active_count', 0)} "
                f"imports_count={report.get('imports_count', 0)} "
                f"legacy_compatibility={bool(report.get('legacy_compatibility'))} "
                f"skill_count={report.get('skill_count', 0)} "
                f"recommendations={len(report.get('recommendations', []))} "
                f"sleep_selected={((report.get('cleanup') or {}).get('review') or {}).get('selected_count', 0)} "
                f"applied={applied_count} pushed={bool((maintenance_branch.get('push') or {}).get('pushed'))}"
            ),
            comment="Organization maintenance automation inspected the validated organization mirror, including the imports incoming lane and main exchange surface, then selected cleanup proposals and applied organization Sleep-style actions with audit evidence.",
            action_taken="Read desktop organization maintenance settings, validated participation, inspected the organization KB mirror with the organization maintenance worldview, selected cleanup proposals, and moved reviewed material toward main when selected actions allowed it.",
            observed_result=f"Report recommendations: {', '.join(report.get('recommendations', [])) or 'none'}.",
            operational_use="Use this audit event to confirm scheduled organization maintenance runs only on opted-in machines, treats legacy trusted/candidates as compatibility paths, and closes the imports-to-main decision/apply loop for supported cleanup actions.",
            agent_name="kb-organization-maintenance",
        )

    apply_ok = True
    if apply_result.get("attempted") or apply_result.get("ok") is False:
        apply_ok = bool(apply_result.get("ok"))
    post_apply_ok = True
    if post_apply_check:
        post_apply_ok = bool(post_apply_check.get("ok"))
    result = {
        "ok": bool(report.get("ok")) and apply_ok and post_apply_ok and bool(maintenance_branch.get("ok", True)),
        "skipped": False,
        "settings_gate": {
            "available": True,
            "mode": str(settings.get("mode") or "personal"),
            "organization_validated": True,
            "maintenance_requested": bool(participation.get("requested")),
        },
        "organization_id": organization_id,
        "source": source,
        "participation": participation,
        "sync": sync_result,
        "lane_policy": ORG_LANE_POLICY,
        "preflight": preflight,
        "report": report,
        "maintenance_branch": maintenance_branch,
        "postflight_recorded": bool(postflight_path),
        "postflight_path": postflight_path,
    }
    result["lane_lock"] = lane_lock
    result["lock_release"] = release_lane_lock(repo_root, "kb-org-maintenance", run_id=str(lane_lock.get("run_id") or ""))
    return result
