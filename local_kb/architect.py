from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from local_kb.common import normalize_text, slugify, utc_now_iso
from local_kb.consolidate import APPLY_MODE_NONE, consolidate_history, sanitize_run_id
from local_kb.consolidate_events import load_history_events, relative_repo_path
from local_kb.feedback import build_observation, record_observation
from local_kb.search import render_search_payload, search_entries
from local_kb.store import history_events_path


ARCHITECT_SCHEMA_VERSION = 1
ARCHITECT_REPORT_KIND = "local-kb-architect-report"
ARCHITECT_QUEUE_KIND = "local-kb-architect-proposal-queue"
ARCHITECT_ROUTE_HINT = "system/knowledge-library/maintenance"
ARCHITECT_PREFLIGHT_QUERY = (
    "KB Architect automation proposal queue lifecycle evidence impact safety "
    "sleep dream automation runbook prompt install check validation rollback"
)

PLAN_FILENAME = "plan.json"
PREFLIGHT_FILENAME = "preflight.json"
SIGNALS_FILENAME = "signals.json"
PROPOSALS_FILENAME = "proposals.json"
DECISIONS_FILENAME = "decisions.json"
EXECUTION_PLAN_FILENAME = "execution_plan.json"
REPORT_FILENAME = "report.json"
QUEUE_FILENAME = "proposal_queue.json"

LEVELS = {"low": 1, "medium": 2, "high": 3}
TERMINAL_STATUSES = {"applied", "rejected", "superseded"}
ARCHITECT_ACTION_TYPES = {
    "review-code-change",
    "investigate-gap",
    "review-observation-evidence",
}

MECHANISM_KEYWORDS = {
    "architect",
    "automation",
    "automations",
    "check",
    "checklist",
    "codex",
    "dream",
    "install",
    "installer",
    "maintenance",
    "postflight",
    "preflight",
    "prompt",
    "proposal",
    "queue",
    "rollback",
    "runbook",
    "sleep",
    "snapshot",
    "test",
    "validation",
    "workflow",
}

MECHANISM_ROUTE_PREFIXES = (
    "system/knowledge-library",
    "kb/",
    "predictive-kb",
    "repository/usage/local-kb-retrieve",
    "codex/workflow/postflight",
)

MECHANISM_PHRASES = {
    "kb architect",
    "kb dream",
    "kb sleep",
    "khaos brain",
    "local kb",
    "predictive kb",
    "knowledge library",
    "knowledge-library",
}

HIGH_IMPACT_KEYWORDS = {
    "automation",
    "install",
    "installer",
    "postflight",
    "preflight",
    "rollback",
    "safety",
    "validation",
}

LOW_SAFETY_KEYWORDS = {
    "delete",
    "dependency",
    "lockfile",
    "migration",
    "rename",
    "reset",
    "route move",
    "taxonomy",
}

PATCH_ONLY_CATEGORIES = {"automation", "install-check", "core-tooling"}
AUTO_APPLY_CATEGORIES = {"prompt", "runbook", "proposal-queue", "validation"}

CATEGORY_KEYWORDS = (
    ("automation", {"automation", "automations", "cron", "schedule"}),
    ("install-check", {"install", "installer", "checklist", "manifest"}),
    ("prompt", {"prompt", "preflight", "postflight"}),
    ("runbook", {"runbook", "docs", "documentation"}),
    ("rollback", {"rollback", "snapshot", "restore"}),
    ("validation", {"test", "validation", "check"}),
    ("proposal-queue", {"proposal", "queue", "status", "watching"}),
    ("sleep-dream-boundary", {"sleep", "dream", "overlap", "cooldown"}),
)


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def architecture_root(repo_root: Path) -> Path:
    return repo_root / "kb" / "history" / "architecture"


def architect_run_dir(repo_root: Path, run_id: str) -> Path:
    return architecture_root(repo_root) / "runs" / run_id


def architect_queue_path(repo_root: Path) -> Path:
    return architecture_root(repo_root) / QUEUE_FILENAME


def _latest_run_guard(
    repo_root: Path,
    *,
    root_parts: tuple[str, ...],
    prefix: str,
    cooldown_minutes: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    reference_time = now or datetime.now(timezone.utc)
    root = repo_root.joinpath(*root_parts)
    latest_run_dir: Path | None = None
    latest_mtime: float | None = None
    if root.exists():
        for path in root.iterdir():
            if not path.is_dir() or (prefix and not path.name.startswith(prefix)):
                continue
            stat = path.stat()
            if latest_mtime is None or stat.st_mtime > latest_mtime:
                latest_mtime = stat.st_mtime
                latest_run_dir = path

    minutes_since_latest: float | None = None
    if latest_mtime is not None:
        minutes_since_latest = max(0.0, (reference_time.timestamp() - latest_mtime) / 60.0)
    blocked = (
        cooldown_minutes > 0
        and minutes_since_latest is not None
        and minutes_since_latest < cooldown_minutes
    )
    return {
        "blocked": blocked,
        "cooldown_minutes": cooldown_minutes,
        "latest_run_dir": relative_repo_path(repo_root, latest_run_dir) if latest_run_dir else "",
        "minutes_since_latest_run": round(minutes_since_latest, 2)
        if minutes_since_latest is not None
        else None,
    }


def build_architect_guards(
    repo_root: Path,
    *,
    sleep_cooldown_minutes: int,
    dream_cooldown_minutes: int,
) -> dict[str, Any]:
    sleep_guard = _latest_run_guard(
        repo_root,
        root_parts=("kb", "history", "consolidation"),
        prefix="kb-sleep",
        cooldown_minutes=sleep_cooldown_minutes,
    )
    dream_guard = _latest_run_guard(
        repo_root,
        root_parts=("kb", "history", "dream"),
        prefix="kb-dream",
        cooldown_minutes=dream_cooldown_minutes,
    )
    return {
        "blocked": bool(sleep_guard["blocked"] or dream_guard["blocked"]),
        "sleep": sleep_guard,
        "dream": dream_guard,
    }


def _checkpoint(
    checkpoint_id: str,
    description: str,
    status: str = "pending",
    details: str = "",
) -> dict[str, Any]:
    payload = {
        "id": checkpoint_id,
        "description": description,
        "status": status,
    }
    if details:
        payload["details"] = details
    return payload


def _set_checkpoint_status(
    execution_plan: dict[str, Any],
    checkpoint_id: str,
    status: str,
    details: str = "",
) -> None:
    for checkpoint in execution_plan.get("checkpoints", []):
        if checkpoint.get("id") != checkpoint_id:
            continue
        checkpoint["status"] = status
        if details:
            checkpoint["details"] = details
        return


def build_initial_execution_plan(
    repo_root: Path,
    *,
    run_id: str,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": ARCHITECT_SCHEMA_VERSION,
        "kind": "local-kb-architect-execution-plan",
        "run_id": run_id,
        "generated_at": generated_at,
        "status": "running",
        "policy": {
            "scope": "KB operating mechanism only; card content maintenance stays in Sleep.",
            "decision_axes": ["evidence", "impact", "safety"],
            "statuses": [
                "new",
                "watching",
                "ready-for-patch",
                "ready-for-apply",
                "applied",
                "rejected",
                "superseded",
            ],
        },
        "artifact_paths": {
            "run_dir": relative_repo_path(repo_root, architect_run_dir(repo_root, run_id)),
            "queue_path": relative_repo_path(repo_root, architect_queue_path(repo_root)),
        },
        "checkpoints": [
            _checkpoint("guards", "Confirm Sleep/Dream maintenance windows do not overlap"),
            _checkpoint("kb-preflight", "Retrieve prior mechanism-maintenance lessons"),
            _checkpoint("input-gathering", "Read history, consolidation proposals, and old Architect queue"),
            _checkpoint("proposal-clustering", "Merge duplicate mechanism proposals"),
            _checkpoint("three-axis-review", "Assign Evidence, Impact, and Safety levels"),
            _checkpoint("status-decisions", "Decide watching, patch, apply, rejected, or superseded states"),
            _checkpoint("queue-write", "Write the maintained proposal queue"),
            _checkpoint("postflight-observation", "Append one KB observation for this Architect run"),
            _checkpoint("report", "Write final Architect report"),
        ],
    }


def _build_preflight(repo_root: Path, *, run_id: str, generated_at: str) -> dict[str, Any]:
    hits = search_entries(
        repo_root,
        query=ARCHITECT_PREFLIGHT_QUERY,
        path_hint=ARCHITECT_ROUTE_HINT,
        top_k=5,
    )
    payload = render_search_payload(hits, repo_root)
    return {
        "schema_version": ARCHITECT_SCHEMA_VERSION,
        "kind": "local-kb-architect-preflight",
        "run_id": run_id,
        "generated_at": generated_at,
        "route_hint": ARCHITECT_ROUTE_HINT,
        "query": ARCHITECT_PREFLIGHT_QUERY,
        "matched_entry_count": len(payload),
        "matched_entry_ids": [str(item.get("id", "") or "") for item in payload if item.get("id")],
        "results": payload,
    }


def _stable_id(*parts: str) -> str:
    source = "\n".join(parts)
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:12]
    return f"arch-prop-{digest}"


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(f"{key} {_stringify(item)}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(_stringify(item) for item in value)
    return str(value)


def _action_text(action: dict[str, Any]) -> str:
    parts = [
        action.get("action_key"),
        action.get("action_type"),
        action.get("target"),
        action.get("routes"),
        action.get("task_summaries"),
        action.get("signals"),
        action.get("recommended_next_step"),
        action.get("semantic_review_suggestion"),
        action.get("disposition_suggestion"),
    ]
    return normalize_text(" ".join(_stringify(part) for part in parts))


def _target_ref(action: dict[str, Any]) -> str:
    target = action.get("target", {})
    if not isinstance(target, dict):
        return ""
    for key in ("ref", "route", "entry_id", "entry_path", "id", "path"):
        value = str(target.get(key, "") or "").strip()
        if value:
            return value
    return str(action.get("action_key", "") or "").strip()


def _target_kind(action: dict[str, Any]) -> str:
    target = action.get("target", {})
    if isinstance(target, dict):
        kind = str(target.get("kind", "") or "").strip()
        if kind:
            return kind
    return "unknown"


def _contains_any(text: str, keywords: set[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _is_mechanism_action(action: dict[str, Any]) -> bool:
    text = _action_text(action).lower()
    routes = [str(item).lower() for item in action.get("routes", []) if str(item).strip()]
    target_ref = _target_ref(action).lower()
    route_text = " ".join(routes)
    route_and_target = " ".join([route_text, target_ref]).strip()
    if any(prefix in route_and_target for prefix in MECHANISM_ROUTE_PREFIXES):
        return True
    if any(phrase in text for phrase in MECHANISM_PHRASES):
        return True
    return False


def _category_for(text: str) -> str:
    lowered = text.lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "core-tooling"


def _level_from_signal_count(count: int) -> str:
    if count >= 3:
        return "high"
    if count >= 2:
        return "medium"
    return "low"


def _impact_level(text: str, category: str, signal_count: int) -> tuple[str, str]:
    lowered = text.lower()
    if _contains_any(lowered, HIGH_IMPACT_KEYWORDS):
        return "high", "The signal touches automation, installation, validation, rollback, or lifecycle defaults."
    if category in {"sleep-dream-boundary", "proposal-queue", "prompt"}:
        return "medium", "The signal affects the quality of scheduled maintenance behavior."
    if signal_count >= 3:
        return "medium", "The signal is repeated enough that ignoring it may preserve workflow friction."
    return "low", "The signal is currently narrow or weak."


def _safety_level(text: str, category: str) -> tuple[str, str]:
    lowered = text.lower()
    if _contains_any(lowered, LOW_SAFETY_KEYWORDS):
        return "low", "The proposal may touch taxonomy, deletion, dependency, migration, or broad movement."
    if category in PATCH_ONLY_CATEGORIES:
        return "medium", "The proposal affects automation, installer, or core tooling and should start as a patch."
    if category in AUTO_APPLY_CATEGORIES:
        return "high", "The proposal is limited to prompt, runbook, validation, or proposal-queue maintenance."
    return "medium", "The proposal is mechanism-scoped but needs patch-level review before code changes."


def _decide_status(evidence: str, impact: str, safety: str, category: str) -> tuple[str, str]:
    if safety == "low":
        return "watching", "Safety is low, so the proposal stays under long observation."
    if evidence == "high" and impact in {"high", "medium"} and safety == "high":
        if category in AUTO_APPLY_CATEGORIES:
            return "ready-for-apply", "Evidence is high and the safe action surface is narrow."
        return "ready-for-patch", "Evidence is high, but the category should still begin as a patch."
    if evidence == "high" and safety == "medium":
        return "ready-for-patch", "Evidence is high, but the change should be reviewed as a patch before application."
    if evidence == "medium" and impact == "high":
        return "watching", "Impact is high but evidence needs one more reinforcing signal."
    if evidence == "low" and impact == "low":
        return "rejected", "The proposal currently has weak evidence and low mechanism impact."
    return "watching", "The proposal is useful enough to keep, but not ready to execute."


def _source_action_summary(repo_root: Path, action: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_key": str(action.get("action_key", "") or ""),
        "action_type": str(action.get("action_type", "") or ""),
        "target_kind": _target_kind(action),
        "target_ref": _target_ref(action),
        "priority_score": action.get("priority_score", 0),
        "event_count": action.get("event_count", 0),
        "event_ids": list(action.get("event_ids", [])),
        "routes": list(action.get("routes", [])),
        "task_summaries": list(action.get("task_summaries", [])),
        "recommended_next_step": str(action.get("recommended_next_step", "") or ""),
        "stub_path": str(action.get("stub_path", "") or ""),
    }


def build_mechanism_signal_from_action(repo_root: Path, action: dict[str, Any]) -> dict[str, Any] | None:
    action_type = str(action.get("action_type", "") or "unknown")
    if action_type not in ARCHITECT_ACTION_TYPES:
        return None
    if not _is_mechanism_action(action):
        return None

    text = _action_text(action)
    category = _category_for(text)
    target_ref = _target_ref(action) or slugify(text)[:64]
    signal_count = max(
        int(action.get("event_count", 0) or 0),
        len(action.get("event_ids", []) or []),
        1,
    )
    proposal_id = _stable_id(category, action_type, target_ref)
    return {
        "proposal_id": proposal_id,
        "category": category,
        "title": f"Review {category} mechanism signal for {target_ref}",
        "target_kind": _target_kind(action),
        "target_ref": target_ref,
        "source_kind": "consolidation-action",
        "signal_count": signal_count,
        "source_actions": [_source_action_summary(repo_root, action)],
        "text": text,
    }


def _merge_signal(base: dict[str, Any], signal: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged["signal_count"] = int(merged.get("signal_count", 0) or 0) + int(signal.get("signal_count", 0) or 0)
    merged.setdefault("source_actions", [])
    existing_keys = {
        str(item.get("action_key", "") or "")
        for item in merged.get("source_actions", [])
        if isinstance(item, dict)
    }
    for action in signal.get("source_actions", []):
        if not isinstance(action, dict):
            continue
        key = str(action.get("action_key", "") or "")
        if key and key in existing_keys:
            continue
        merged["source_actions"].append(action)
        if key:
            existing_keys.add(key)
    merged["text"] = f"{merged.get('text', '')} {signal.get('text', '')}".strip()
    return merged


def _load_existing_queue(repo_root: Path) -> dict[str, Any]:
    path = architect_queue_path(repo_root)
    payload = load_json_object(path)
    proposals = payload.get("proposals", []) if isinstance(payload.get("proposals"), list) else []
    return {
        "schema_version": ARCHITECT_SCHEMA_VERSION,
        "kind": ARCHITECT_QUEUE_KIND,
        "proposals": [item for item in proposals if isinstance(item, dict)],
    }


def _proposal_from_signal(
    signal: dict[str, Any],
    *,
    existing: dict[str, Any] | None,
    run_id: str,
    generated_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    prior = existing or {}
    support_runs = sorted(set([*prior.get("supporting_run_ids", []), run_id]))
    signal_count = int(signal.get("signal_count", 0) or 0)
    prior_signal_count = int(prior.get("evidence", {}).get("signal_count", 0) or 0) if prior else 0
    combined_signal_count = max(signal_count, prior_signal_count + signal_count)
    evidence_level = _level_from_signal_count(combined_signal_count)
    impact_level, impact_reason = _impact_level(str(signal.get("text", "") or ""), signal["category"], combined_signal_count)
    safety_level, safety_reason = _safety_level(str(signal.get("text", "") or ""), signal["category"])
    status, status_reason = _decide_status(
        evidence=evidence_level,
        impact=impact_level,
        safety=safety_level,
        category=signal["category"],
    )
    if prior.get("status") in TERMINAL_STATUSES and status not in {"ready-for-apply", "ready-for-patch"}:
        status = str(prior.get("status"))
        status_reason = "Preserved terminal status from an earlier Architect decision."

    proposal = {
        "proposal_id": signal["proposal_id"],
        "title": prior.get("title") or signal["title"],
        "category": signal["category"],
        "status": status,
        "status_reason": status_reason,
        "target": {
            "kind": signal.get("target_kind", "unknown"),
            "ref": signal.get("target_ref", ""),
        },
        "evidence": {
            "level": evidence_level,
            "signal_count": combined_signal_count,
            "source_action_count": len(signal.get("source_actions", [])),
            "supporting_run_count": len(support_runs),
        },
        "impact": {
            "level": impact_level,
            "rationale": impact_reason,
        },
        "safety": {
            "level": safety_level,
            "rationale": safety_reason,
        },
        "next_action": _next_action_for_status(status),
        "scope_boundary": "Mechanism only. Do not rewrite trusted cards, promote candidates, or maintain card content here.",
        "source_actions": signal.get("source_actions", []),
        "supporting_run_ids": support_runs,
        "first_seen_at": prior.get("first_seen_at") or generated_at,
        "last_seen_at": generated_at,
        "updated_at": generated_at,
    }
    decision = {
        "proposal_id": proposal["proposal_id"],
        "previous_status": prior.get("status", "new") if prior else "new",
        "new_status": status,
        "evidence": evidence_level,
        "impact": impact_level,
        "safety": safety_level,
        "reason": status_reason,
    }
    return proposal, decision


def _next_action_for_status(status: str) -> str:
    if status == "ready-for-apply":
        return "Apply only if the scheduled agent can keep the change inside the narrow allowlist and run the validation bundle immediately."
    if status == "ready-for-patch":
        return "Generate a patch and validation plan; do not apply broad mechanism changes without passing tests."
    if status == "watching":
        return "Keep observing future Sleep, Dream, and Architect reports for repeated evidence."
    if status == "rejected":
        return "Do not act unless future runs produce stronger evidence."
    if status == "superseded":
        return "Follow the replacement proposal instead."
    if status == "applied":
        return "Keep the applied change under observation in future runs."
    return "Review during the next Architect pass."


def _carry_forward_proposal(proposal: dict[str, Any], *, generated_at: str) -> tuple[dict[str, Any], dict[str, Any]]:
    carried = dict(proposal)
    status = str(carried.get("status", "watching") or "watching")
    if status not in TERMINAL_STATUSES:
        status = "watching"
        carried["status"] = status
        carried["status_reason"] = "No fresh matching signal appeared in this run."
        carried["next_action"] = _next_action_for_status(status)
    carried["updated_at"] = generated_at
    return carried, {
        "proposal_id": str(carried.get("proposal_id", "") or ""),
        "previous_status": str(proposal.get("status", "") or ""),
        "new_status": status,
        "reason": str(carried.get("status_reason", "") or ""),
    }


def build_architect_queue(
    repo_root: Path,
    *,
    run_id: str,
    generated_at: str,
    actions: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    existing_queue = _load_existing_queue(repo_root)
    existing_by_id = {
        str(item.get("proposal_id", "") or ""): item
        for item in existing_queue.get("proposals", [])
        if str(item.get("proposal_id", "") or "")
    }

    signals_by_id: dict[str, dict[str, Any]] = {}
    skipped_actions: list[dict[str, Any]] = []
    for action in actions:
        signal = build_mechanism_signal_from_action(repo_root, action)
        if signal is None:
            skipped_actions.append(_source_action_summary(repo_root, action))
            continue
        proposal_id = signal["proposal_id"]
        if proposal_id in signals_by_id:
            signals_by_id[proposal_id] = _merge_signal(signals_by_id[proposal_id], signal)
        else:
            signals_by_id[proposal_id] = signal

    proposals: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for proposal_id, signal in sorted(signals_by_id.items()):
        proposal, decision = _proposal_from_signal(
            signal,
            existing=existing_by_id.get(proposal_id),
            run_id=run_id,
            generated_at=generated_at,
        )
        proposals.append(proposal)
        decisions.append(decision)
        seen_ids.add(proposal_id)

    for proposal_id, existing in sorted(existing_by_id.items()):
        if proposal_id in seen_ids:
            continue
        proposal, decision = _carry_forward_proposal(existing, generated_at=generated_at)
        proposals.append(proposal)
        decisions.append(decision)

    proposals = sorted(
        proposals,
        key=lambda item: (
            -LEVELS.get(str(item.get("evidence", {}).get("level", "low")), 0),
            -LEVELS.get(str(item.get("impact", {}).get("level", "low")), 0),
            str(item.get("status", "")),
            str(item.get("proposal_id", "")),
        ),
    )
    queue = {
        "schema_version": ARCHITECT_SCHEMA_VERSION,
        "kind": ARCHITECT_QUEUE_KIND,
        "run_id": run_id,
        "generated_at": generated_at,
        "updated_at": generated_at,
        "proposal_count": len(proposals),
        "proposals": proposals,
    }
    signals = {
        "schema_version": ARCHITECT_SCHEMA_VERSION,
        "kind": "local-kb-architect-signals",
        "run_id": run_id,
        "generated_at": generated_at,
        "mechanism_signal_count": len(signals_by_id),
        "skipped_non_mechanism_action_count": len(skipped_actions),
        "signals": list(signals_by_id.values()),
        "skipped_non_mechanism_actions": skipped_actions,
    }
    decision_payload = {
        "schema_version": ARCHITECT_SCHEMA_VERSION,
        "kind": "local-kb-architect-decisions",
        "run_id": run_id,
        "generated_at": generated_at,
        "decision_count": len(decisions),
        "decisions": decisions,
    }
    return queue, signals, decision_payload


def _status_counts(proposals: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for proposal in proposals:
        status = str(proposal.get("status", "") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _record_architect_observation(
    repo_root: Path,
    *,
    run_id: str,
    preflight: dict[str, Any],
    queue: dict[str, Any],
) -> str:
    proposals = list(queue.get("proposals", []))
    status_counts = _status_counts(proposals)
    ready_count = status_counts.get("ready-for-apply", 0) + status_counts.get("ready-for-patch", 0)
    suggested_action = "code-change" if ready_count else "none"
    outcome = (
        f"Maintained {len(proposals)} Architect mechanism proposal(s); "
        f"status_counts={status_counts}."
    )
    observation = build_observation(
        task_summary=f"KB Architect run {run_id} maintained the mechanism proposal queue",
        route_hint=ARCHITECT_ROUTE_HINT,
        entry_ids=",".join(preflight.get("matched_entry_ids", [])),
        hit_quality="hit" if preflight.get("matched_entry_ids") else "none",
        outcome=outcome,
        comment=(
            "Architect reviewed system-mechanism proposals with the minimal Evidence, Impact, "
            "and Safety model, leaving card-content maintenance to Sleep."
        ),
        suggested_action=suggested_action,
        scenario="Daily KB Architect automation reviews the KB system's own operating mechanisms.",
        action_taken=(
            "Ran preflight retrieval, gathered consolidation proposal signals, merged the mechanism proposal queue, "
            "and assigned proposal statuses without touching card content."
        ),
        observed_result=outcome,
        operational_use=(
            "Future Architect runs should keep using the three-axis review and only execute high-evidence, "
            "high-safety mechanism changes with immediate validation."
        ),
        reuse_judgment="Reusable as an audit trail for autonomous KB mechanism maintenance.",
        source_kind="architect-maintenance",
        agent_name="kb-architect",
        thread_ref=run_id,
        project_ref=repo_root.name,
        workspace_root=str(repo_root),
    )
    record_observation(repo_root, observation)
    return str(observation["event_id"])


def _write_skip_event(
    repo_root: Path,
    *,
    run_id: str,
    guards: dict[str, Any],
) -> str:
    observation = build_observation(
        task_summary=f"KB Architect run {run_id} skipped because another maintenance lane may overlap",
        route_hint=ARCHITECT_ROUTE_HINT,
        hit_quality="none",
        outcome="Architect skipped before proposal review because Sleep or Dream cooldown was still active.",
        comment="Architect should not overlap with Sleep or Dream maintenance windows.",
        suggested_action="none",
        scenario="Scheduled Architect run starts while another KB maintenance lane is still inside its cooldown window.",
        action_taken="Skipped mechanism proposal maintenance and wrote a history note.",
        observed_result="No proposal queue changes were made.",
        operational_use="Retry on the next scheduled Architect run after Sleep and Dream artifacts have settled.",
        reuse_judgment="Reusable as a concurrency guard event.",
        source_kind="architect-maintenance",
        agent_name="kb-architect",
        thread_ref=run_id,
        project_ref=repo_root.name,
        workspace_root=str(repo_root),
    )
    observation["context"]["guards"] = guards
    record_observation(repo_root, observation)
    return str(observation["event_id"])


def run_architect_maintenance(
    repo_root: Path,
    *,
    run_id: str | None = None,
    max_events: int | None = None,
    sleep_cooldown_minutes: int = 60,
    dream_cooldown_minutes: int = 20,
) -> dict[str, Any]:
    generated_at = utc_now_iso()
    resolved_run_id = sanitize_run_id(run_id or f"kb-architect-{utc_now_compact()}")
    run_dir = architect_run_dir(repo_root, resolved_run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    execution_plan = build_initial_execution_plan(repo_root, run_id=resolved_run_id, generated_at=generated_at)
    write_json_file(run_dir / EXECUTION_PLAN_FILENAME, execution_plan)

    guards = build_architect_guards(
        repo_root,
        sleep_cooldown_minutes=max(0, sleep_cooldown_minutes),
        dream_cooldown_minutes=max(0, dream_cooldown_minutes),
    )
    plan_payload = {
        "schema_version": ARCHITECT_SCHEMA_VERSION,
        "kind": "local-kb-architect-plan",
        "run_id": resolved_run_id,
        "generated_at": generated_at,
        "guards": guards,
        "required_order": [checkpoint["id"] for checkpoint in execution_plan["checkpoints"]],
    }
    write_json_file(run_dir / PLAN_FILENAME, plan_payload)
    _set_checkpoint_status(
        execution_plan,
        "guards",
        "blocked" if guards["blocked"] else "completed",
        "Sleep/Dream guard checked.",
    )
    write_json_file(run_dir / EXECUTION_PLAN_FILENAME, execution_plan)

    if guards["blocked"]:
        event_id = _write_skip_event(repo_root, run_id=resolved_run_id, guards=guards)
        _set_checkpoint_status(
            execution_plan,
            "postflight-observation",
            "completed",
            f"Wrote skip observation {event_id}.",
        )
        _set_checkpoint_status(execution_plan, "report", "completed", "Skip report prepared.")
        execution_plan["status"] = "skipped"
        execution_plan["completed_at"] = utc_now_iso()
        write_json_file(run_dir / EXECUTION_PLAN_FILENAME, execution_plan)
        result = {
            "schema_version": ARCHITECT_SCHEMA_VERSION,
            "kind": ARCHITECT_REPORT_KIND,
            "run_id": resolved_run_id,
            "generated_at": generated_at,
            "status": "skipped",
            "reason": "maintenance-lane-cooldown",
            "guards": guards,
            "history_event_ids": [event_id],
            "artifact_paths": {
                "run_dir": relative_repo_path(repo_root, run_dir),
                "plan_path": relative_repo_path(repo_root, run_dir / PLAN_FILENAME),
                "execution_plan_path": relative_repo_path(repo_root, run_dir / EXECUTION_PLAN_FILENAME),
                "report_path": relative_repo_path(repo_root, run_dir / REPORT_FILENAME),
            },
        }
        write_json_file(run_dir / REPORT_FILENAME, result)
        return result

    preflight = _build_preflight(repo_root, run_id=resolved_run_id, generated_at=generated_at)
    write_json_file(run_dir / PREFLIGHT_FILENAME, preflight)
    _set_checkpoint_status(
        execution_plan,
        "kb-preflight",
        "completed",
        f"Retrieved {preflight['matched_entry_count']} prior maintenance entries.",
    )

    history_events = load_history_events(repo_root, max_events=max_events)
    consolidation = consolidate_history(
        repo_root=repo_root,
        run_id=f"{resolved_run_id}-source",
        emit_files=True,
        max_events=max_events,
        apply_mode=APPLY_MODE_NONE,
    )
    actions = list(consolidation.get("actions", []))
    _set_checkpoint_status(
        execution_plan,
        "input-gathering",
        "completed",
        f"Read {len(history_events)} history events and {len(actions)} consolidation actions.",
    )

    queue, signals, decisions = build_architect_queue(
        repo_root,
        run_id=resolved_run_id,
        generated_at=generated_at,
        actions=actions,
    )
    write_json_file(run_dir / SIGNALS_FILENAME, signals)
    write_json_file(run_dir / PROPOSALS_FILENAME, queue)
    write_json_file(run_dir / DECISIONS_FILENAME, decisions)
    write_json_file(architect_queue_path(repo_root), queue)
    _set_checkpoint_status(
        execution_plan,
        "proposal-clustering",
        "completed",
        f"Merged {signals['mechanism_signal_count']} mechanism signal(s).",
    )
    _set_checkpoint_status(
        execution_plan,
        "three-axis-review",
        "completed",
        "Reviewed proposals with Evidence, Impact, and Safety only.",
    )
    _set_checkpoint_status(
        execution_plan,
        "status-decisions",
        "completed",
        f"Assigned statuses: {_status_counts(queue.get('proposals', []))}.",
    )
    _set_checkpoint_status(
        execution_plan,
        "queue-write",
        "completed",
        f"Wrote {relative_repo_path(repo_root, architect_queue_path(repo_root))}.",
    )

    observation_event_id = _record_architect_observation(
        repo_root,
        run_id=resolved_run_id,
        preflight=preflight,
        queue=queue,
    )
    _set_checkpoint_status(
        execution_plan,
        "postflight-observation",
        "completed",
        f"Wrote Architect observation {observation_event_id}.",
    )
    _set_checkpoint_status(execution_plan, "report", "completed", "Report payload prepared.")
    execution_plan["status"] = "completed"
    execution_plan["completed_at"] = utc_now_iso()
    write_json_file(run_dir / EXECUTION_PLAN_FILENAME, execution_plan)

    result = {
        "schema_version": ARCHITECT_SCHEMA_VERSION,
        "kind": ARCHITECT_REPORT_KIND,
        "run_id": resolved_run_id,
        "generated_at": generated_at,
        "status": "completed",
        "guards": guards,
        "history_path": relative_repo_path(repo_root, history_events_path(repo_root)),
        "preflight": preflight,
        "execution_plan": execution_plan,
        "history_event_ids": [observation_event_id],
        "consolidation_run_id": consolidation.get("run_id", f"{resolved_run_id}-source"),
        "consolidation_action_count": len(actions),
        "mechanism_signal_count": signals["mechanism_signal_count"],
        "proposal_count": queue["proposal_count"],
        "status_counts": _status_counts(queue.get("proposals", [])),
        "ready_for_apply_count": _status_counts(queue.get("proposals", [])).get("ready-for-apply", 0),
        "ready_for_patch_count": _status_counts(queue.get("proposals", [])).get("ready-for-patch", 0),
        "skipped_non_mechanism_action_count": signals["skipped_non_mechanism_action_count"],
        "artifact_paths": {
            "run_dir": relative_repo_path(repo_root, run_dir),
            "plan_path": relative_repo_path(repo_root, run_dir / PLAN_FILENAME),
            "preflight_path": relative_repo_path(repo_root, run_dir / PREFLIGHT_FILENAME),
            "signals_path": relative_repo_path(repo_root, run_dir / SIGNALS_FILENAME),
            "proposals_path": relative_repo_path(repo_root, run_dir / PROPOSALS_FILENAME),
            "decisions_path": relative_repo_path(repo_root, run_dir / DECISIONS_FILENAME),
            "execution_plan_path": relative_repo_path(repo_root, run_dir / EXECUTION_PLAN_FILENAME),
            "queue_path": relative_repo_path(repo_root, architect_queue_path(repo_root)),
            "report_path": relative_repo_path(repo_root, run_dir / REPORT_FILENAME),
            "source_consolidation_proposal_path": consolidation.get("artifact_paths", {}).get("proposal_path", ""),
        },
    }
    write_json_file(run_dir / REPORT_FILENAME, result)
    return result
