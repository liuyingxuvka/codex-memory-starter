from __future__ import annotations

from pathlib import Path
from typing import Any

from local_kb.org_checks import check_organization_repository
from local_kb.org_cleanup import apply_organization_cleanup_proposal, build_organization_cleanup_proposal
from local_kb.org_outbox import organization_outbox_dir
from local_kb.org_sources import validate_organization_repo
from local_kb.skill_sharing import find_local_skill_metadata
from local_kb.store import load_organization_entries


ORGANIZATION_REVIEW_SKILL_ID = "organization-review"


def _report_layout_policy(validation: dict[str, Any]) -> dict[str, Any]:
    legacy_compatibility = bool(validation.get("legacy_compatibility"))
    return {
        "target_layout": "main-imports",
        "incoming_lane_path": str(validation.get("incoming_lane_path") or "kb/imports"),
        "exchange_surface_path": str(validation.get("exchange_surface_path") or "kb/main"),
        "local_download_primary_path": str(validation.get("local_download_primary_path") or "kb/main"),
        "local_download_paths": validation.get("local_download_paths") or ["kb/main"],
        "local_download_excluded_paths": validation.get("local_download_excluded_paths") or ["kb/imports"],
        "contribution_writes": ["kb/imports"],
        "maintenance_moves_reviewed_cards_to": "kb/main",
        "legacy_compatibility": legacy_compatibility,
        "legacy_paths": validation.get("legacy_paths") or ["kb/trusted", "kb/candidates"],
        "legacy_notice": (
            "Legacy kb/trusted and kb/candidates are compatibility inputs only, not the target organization structure."
            if legacy_compatibility
            else ""
        ),
    }


def build_organization_cleanup_review(proposal: dict[str, Any]) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    selected_action_ids: list[str] = []
    selected_action_types: set[str] = set()
    allow_trusted = False
    allow_delete = False
    allow_promote = False

    for action in proposal.get("actions") or []:
        if not isinstance(action, dict):
            continue
        action_id = str(action.get("action_id") or "").strip()
        action_type = str(action.get("action_type") or "").strip()
        target_path = str(action.get("target_path") or "").replace("\\", "/")
        risk = str(action.get("risk") or "").strip()
        approve = False
        decision = "watch"
        reason = ""

        if action.get("apply_supported") is False:
            reason = "Current organization tooling keeps this watch-only until a concrete safe apply path exists."
        elif action_type == "delete-card":
            current_status = str(action.get("current_status") or "").strip()
            current_confidence = float(action.get("current_confidence") or 1.0)
            approve = (
                not target_path.startswith(("kb/main/", "kb/trusted/"))
                and current_status in {"rejected", "deprecated"}
                and current_confidence <= 0.2
            )
            reason = (
                "Rejected or deprecated low-confidence organization card can be deleted with audit."
                if approve
                else "Deletion did not meet the audited low-confidence rejected/deprecated card rule."
            )
        elif action_type == "promote-card":
            proposed_path = str(action.get("proposed_path") or "").replace("\\", "/")
            approve = (
                str(action.get("current_status") or "") == "candidate"
                and str(action.get("proposed_status") or "") == "trusted"
                and proposed_path.startswith("kb/main/")
                and float(action.get("current_confidence") or 0.0) >= 0.85
            )
            reason = (
                "High-confidence candidate has a concrete main target path and can be promoted."
                if approve
                else "Promotion did not meet the organization Sleep promotion rule."
            )
        elif action_type == "accept-import":
            proposed_path = str(action.get("proposed_path") or "").replace("\\", "/")
            approve = (
                target_path.startswith("kb/imports/")
                and str(action.get("current_status") or "") == "candidate"
                and str(action.get("proposed_status") or "") == "candidate"
                and proposed_path.startswith("kb/main/")
            )
            reason = (
                "Imported candidate has a concrete main target path and can enter the organization exchange surface."
                if approve
                else "Import acceptance did not meet the organization Sleep main-transfer rule."
            )
        elif action_type in {"status-adjust", "confidence-adjust", "mark-duplicate"}:
            approve = True
            reason = "Deterministic organization cleanup action is selected for Sleep-style apply."
        else:
            reason = "Unknown organization cleanup action type remains watch-only."

        if approve:
            decision = "selected-for-apply"
            selected_action_ids.append(action_id)
            selected_action_types.add(action_type)
            if target_path.startswith(("kb/main/", "kb/trusted/")):
                allow_trusted = True
            if action_type == "delete-card":
                allow_delete = True
            if action_type in {"accept-import", "promote-card"}:
                allow_promote = True

        decisions.append(
            {
                "action_id": action_id,
                "action_type": action_type,
                "target_path": target_path,
                "decision": decision,
                "risk": risk,
                "reason": reason,
            }
        )

    return {
        "decision_count": len(decisions),
        "selected_count": len(selected_action_ids),
        "selected_action_ids": selected_action_ids,
        "selected_action_types": sorted(selected_action_types),
        "approved_count": len(selected_action_ids),
        "approved_action_ids": selected_action_ids,
        "approved_action_types": sorted(selected_action_types),
        "allow_trusted": allow_trusted,
        "allow_delete": allow_delete,
        "allow_promote": allow_promote,
        "decisions": decisions,
    }


def build_organization_maintenance_report(
    org_root: Path,
    *,
    repo_root: Path | None = None,
    organization_id: str = "",
    apply_reviewed_cleanup: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    validation = validate_organization_repo(org_root)
    if not validation.get("ok"):
        return {
            "ok": False,
            "validation": validation,
            "entry_count": 0,
            "outbox_count": 0,
            "recommendations": ["fix-organization-repository-validation"],
        }

    organization_id = organization_id or str(validation.get("organization_id") or "")
    entries = load_organization_entries(
        Path(org_root),
        organization_id,
        source_commit=str(validation.get("commit") or ""),
    )
    organization_check = check_organization_repository(org_root)
    duplicate_content_hashes = (
        organization_check.get("checks", {})
        .get("cards", {})
        .get("duplicate_content_hashes", {})
    )
    if not isinstance(duplicate_content_hashes, dict):
        duplicate_content_hashes = {}

    outbox_count = 0
    review_skill: dict[str, Any] = {
        "id": ORGANIZATION_REVIEW_SKILL_ID,
        "installed": False,
        "status": "missing",
    }
    if repo_root is not None:
        outbox_dir = organization_outbox_dir(Path(repo_root), organization_id)
        outbox_count = len(list(outbox_dir.glob("*.yaml"))) if outbox_dir.exists() else 0
        skill_metadata = find_local_skill_metadata(Path(repo_root), ORGANIZATION_REVIEW_SKILL_ID)
        if skill_metadata is not None:
            review_skill = {
                **skill_metadata,
                "installed": True,
            }

    recommendations: list[str] = []
    imports_count = int(validation.get("imports_count") or 0)
    main_active_count = int(validation.get("main_active_count") or 0)
    if imports_count:
        recommendations.append("review-organization-imports")
    if main_active_count:
        recommendations.append("review-main-exchange-surface")
    if validation.get("legacy_compatibility"):
        recommendations.append("migrate-legacy-compatible-layout-to-main-imports")
        if validation.get("candidate_count", 0):
            recommendations.append("review-legacy-compatible-candidates")
    if outbox_count:
        recommendations.append("review-local-outbox-proposals")
    if validation.get("skill_count", 0):
        recommendations.append("review-skill-registry")
    if duplicate_content_hashes:
        recommendations.append("review-duplicate-card-content-hashes")
    if organization_check.get("errors"):
        recommendations.append("fix-organization-check-errors")
    cleanup_proposal = build_organization_cleanup_proposal(org_root, organization_id=organization_id)
    cleanup_actions = cleanup_proposal.get("actions") if isinstance(cleanup_proposal.get("actions"), list) else []
    cleanup_review = build_organization_cleanup_review(cleanup_proposal)
    cleanup_apply: dict[str, Any] = {"attempted": False}
    post_apply_check: dict[str, Any] = {}
    post_apply_validation: dict[str, Any] = {}
    if apply_reviewed_cleanup and cleanup_review["selected_action_ids"]:
        cleanup_apply = apply_organization_cleanup_proposal(
            Path(org_root),
            cleanup_proposal,
            allow_actions=set(cleanup_review["selected_action_types"]),
            allow_action_ids=set(cleanup_review["selected_action_ids"]),
            allow_trusted=bool(cleanup_review["allow_trusted"]),
            allow_delete=bool(cleanup_review["allow_delete"]),
            allow_promote=bool(cleanup_review["allow_promote"]),
            dry_run=dry_run,
        )
        cleanup_apply["attempted"] = True
        post_validation = validate_organization_repo(org_root)
        post_check = check_organization_repository(org_root)
        post_apply_check = {
            "ok": bool(post_check.get("ok")),
            "validation_ok": bool(post_validation.get("ok")),
            "error_count": len(post_check.get("errors") or []),
            "warning_count": len(post_check.get("warnings") or []),
            "auto_merge_blockers": post_check.get("auto_merge_blockers") or [],
        }
        post_apply_validation = {
            "ok": bool(post_validation.get("ok")),
            "layout": post_validation.get("layout"),
            "incoming_lane_path": post_validation.get("incoming_lane_path"),
            "exchange_surface_path": post_validation.get("exchange_surface_path"),
            "main_count": post_validation.get("main_count", 0),
            "main_active_count": post_validation.get("main_active_count", 0),
            "main_status_counts": post_validation.get("main_status_counts") or {},
            "imports_count": post_validation.get("imports_count", 0),
            "imports_status_counts": post_validation.get("imports_status_counts") or {},
            "legacy_trusted_count": post_validation.get("legacy_trusted_count", 0),
            "legacy_candidate_count": post_validation.get("legacy_candidate_count", 0),
            "trusted_count": post_validation.get("trusted_count", 0),
            "candidate_count": post_validation.get("candidate_count", 0),
        }
    trusted_cleanup_actions = [
        action
        for action in cleanup_actions
        if str(action.get("target_path") or "").replace("\\", "/").startswith(("kb/main/", "kb/trusted/"))
    ]
    if cleanup_actions:
        recommendations.append("review-organization-cleanup-proposals")
    if trusted_cleanup_actions:
        recommendations.append("review-trusted-organization-card-maintenance")

    return {
        "ok": True,
        "maintenance_model": cleanup_proposal.get("maintenance_model") or {},
        "validation": validation,
        "layout_policy": _report_layout_policy(validation),
        "organization_check": {
            "ok": bool(organization_check.get("ok")),
            "error_count": len(organization_check.get("errors") or []),
            "warning_count": len(organization_check.get("warnings") or []),
            "auto_merge_eligible": bool(organization_check.get("auto_merge_eligible")),
            "auto_merge_blockers": organization_check.get("auto_merge_blockers") or [],
        },
        "cleanup": {
            "duplicate_content_hash_count": len(duplicate_content_hashes),
            "duplicate_content_hashes": duplicate_content_hashes,
            "proposal_action_count": len(cleanup_actions),
            "proposal_counts": cleanup_proposal.get("counts") or {},
            "trusted_card_action_count": len(trusted_cleanup_actions),
            "exchange_surface_action_count": len(trusted_cleanup_actions),
            "exchange_surface_maintenance": "in-scope-like-local-sleep",
            "trusted_card_maintenance": "in-scope-like-local-sleep",
            "similar_card_merge_apply": "planned",
            "weak_card_rejection_apply": "planned",
            "candidate_delete_apply": "planned",
            "skill_bundle_cleanup_apply": "partial",
            "review": cleanup_review,
            "apply": cleanup_apply,
            "post_apply_check": post_apply_check,
            "post_apply_validation": post_apply_validation,
        },
        "organization_id": organization_id,
        "entry_count": len(entries),
        "main_count": validation.get("main_count", 0),
        "main_active_count": validation.get("main_active_count", 0),
        "main_status_counts": validation.get("main_status_counts") or {},
        "imports_count": validation.get("imports_count", 0),
        "imports_status_counts": validation.get("imports_status_counts") or {},
        "legacy_compatibility": bool(validation.get("legacy_compatibility")),
        "legacy_notice": _report_layout_policy(validation)["legacy_notice"],
        "legacy_trusted_count": validation.get("legacy_trusted_count", 0),
        "legacy_candidate_count": validation.get("legacy_candidate_count", 0),
        "trusted_count": validation.get("trusted_count", 0),
        "candidate_count": validation.get("candidate_count", 0),
        "skill_count": validation.get("skill_count", 0),
        "outbox_count": outbox_count,
        "organization_review_skill": review_skill,
        "recommendations": recommendations,
    }
