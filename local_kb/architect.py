from __future__ import annotations

import fnmatch
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from local_kb.common import normalize_text, slugify, utc_now_iso
from local_kb.consolidate import APPLY_MODE_NONE, consolidate_history, sanitize_run_id
from local_kb.consolidate_events import load_history_events, relative_repo_path
from local_kb.feedback import build_observation, record_observation
from local_kb.history import build_history_event, record_history_event
from local_kb.maintenance_lanes import acquire_lane_lock, build_lane_guard, release_lane_lock, write_lane_status
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
TRIAL_SELECTION_FILENAME = "sandbox_trial_selection.json"

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
    "codex/workflow/skills",
    "codex/skill-use",
    "codex/workflow/postflight",
)

MECHANISM_PHRASES = {
    "codex skill",
    "kb architect",
    "kb dream",
    "kb sleep",
    "khaos brain",
    "local kb",
    "predictive kb",
    "skill maintenance",
    "skill-use",
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

PATCH_ONLY_CATEGORIES = {"automation", "install-check", "core-tooling", "skill-maintenance"}
AUTO_APPLY_CATEGORIES = {"prompt", "runbook", "proposal-queue", "validation"}
EXECUTION_CLOSURE_STATES = {"applied", "blocked"}
EXECUTION_CONTINUATION_STATES = {"ready-for-agent", "patch-required"}

AUTO_APPLY_ALLOWED_PATHS = {
    "prompt": [
        ".agents/skills/local-kb-retrieve/ARCHITECT_PROMPT.md",
        ".agents/skills/local-kb-retrieve/DREAM_PROMPT.md",
        ".agents/skills/local-kb-retrieve/MAINTENANCE_PROMPT.md",
        ".agents/skills/kb-architect-pass/SKILL.md",
        ".agents/skills/kb-dream-pass/SKILL.md",
        ".agents/skills/kb-sleep-maintenance/SKILL.md",
    ],
    "runbook": [
        "docs/architecture_runbook.md",
        "docs/dream_runbook.md",
        "docs/maintenance_runbook.md",
    ],
    "proposal-queue": [
        "kb/history/architecture/proposal_queue.json",
    ],
    "validation": [
        "tests/test_kb_architect.py",
        "tests/test_kb_dream.py",
        "tests/test_codex_install.py",
    ],
}

PATCH_PLAN_ALLOWED_PATHS = {
    "automation": ["$CODEX_HOME/automations/*/automation.toml", "local_kb/install.py"],
    "install-check": ["scripts/install_codex_kb.py", "local_kb/install.py", "tests/test_codex_install.py"],
    "skill-maintenance": [".agents/skills/**"],
    "core-tooling": ["local_kb/**", "tests/**"],
    "rollback": ["local_kb/snapshots.py", "local_kb/rollback.py", "tests/**"],
    "sleep-dream-boundary": ["local_kb/maintenance_lanes.py", "local_kb/dream.py", "local_kb/consolidate.py", "tests/**"],
}

DISALLOWED_EXECUTION_PATHS = [
    "kb/public/**",
    "kb/private/**",
    "kb/candidates/**",
    "VERSION",
    "pyproject.toml",
    "uv.lock",
]
SANDBOX_TRIAL_ROOT = ".local/architect/sandbox"
SANDBOX_TRIAL_DECISIONS = {"applied", "blocked"}
SANDBOX_TRIAL_CATEGORY_PRIORITY = {
    "prompt": 0,
    "runbook": 1,
    "validation": 2,
    "proposal-queue": 3,
}

CATEGORY_KEYWORDS = (
    ("automation", {"automation", "automations", "cron", "schedule"}),
    ("install-check", {"install", "installer", "checklist", "manifest"}),
    ("skill-maintenance", {"codex skill", "skill maintenance", "skill-use", "skill/plugin", "skills"}),
    ("prompt", {"prompt", "preflight", "postflight"}),
    ("runbook", {"runbook", "docs", "documentation"}),
    ("rollback", {"rollback", "snapshot", "restore"}),
    ("validation", {"test", "validation", "check"}),
    ("proposal-queue", {"proposal", "queue", "status", "watching"}),
    ("sleep-dream-boundary", {"sleep", "dream", "overlap", "lane-status"}),
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


def build_architect_guards(repo_root: Path) -> dict[str, Any]:
    lane_guard = build_lane_guard(repo_root, "kb-architect")
    return {
        "blocked": bool(lane_guard["blocked"]),
        "lane": lane_guard,
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
            _checkpoint("sandbox-trial-selection", "Select at most one sandbox-ready packet for this Architect pass"),
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
        return "medium", "The proposal affects automation, installer, Skill workflow, or core tooling and should start as a patch."
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


def _prior_execution_state(prior: dict[str, Any]) -> dict[str, Any]:
    packet = prior.get("execution_packet", {})
    packet_state = packet.get("execution_state") if isinstance(packet, dict) else None
    for source in (prior.get("execution_state"), packet_state):
        if not isinstance(source, dict):
            continue
        state = str(source.get("state", "") or "").strip().lower()
        if state in EXECUTION_CLOSURE_STATES:
            copied = dict(source)
            copied["state"] = state
            return copied

    status = str(prior.get("status", "") or "").strip().lower()
    if status == "blocked":
        return {
            "state": "blocked",
            "reason": str(prior.get("status_reason", "") or "Proposal was marked blocked by an earlier execution attempt."),
        }
    if status == "applied":
        return {
            "state": "applied",
            "reason": str(prior.get("status_reason", "") or "Proposal was marked applied by an earlier execution attempt."),
        }
    return {}


def _prior_continuation_state(prior: dict[str, Any]) -> dict[str, Any]:
    packet = prior.get("execution_packet", {})
    packet_state = packet.get("execution_state") if isinstance(packet, dict) else None
    for source in (prior.get("execution_state"), packet_state):
        if not isinstance(source, dict):
            continue
        state = str(source.get("state", "") or "").strip().lower()
        if state in EXECUTION_CONTINUATION_STATES:
            copied = dict(source)
            copied["state"] = state
            return copied
    return {}


def _execution_state_reason(state: dict[str, Any]) -> str:
    for key in ("reason", "blocked_reason", "result", "notes"):
        value = str(state.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _apply_prior_execution_closure(
    proposal: dict[str, Any],
    prior: dict[str, Any],
    *,
    generated_at: str,
) -> None:
    state = _prior_execution_state(prior)
    if not state:
        return

    state.setdefault("updated_at", generated_at)
    reason = _execution_state_reason(state)
    proposal["execution_state"] = state
    if state["state"] == "applied":
        proposal["status"] = "applied"
        proposal["status_reason"] = "Preserved execution closure state: applied."
        if reason:
            proposal["status_reason"] = f"{proposal['status_reason']} {reason}"
        proposal["next_action"] = _next_action_for_status("applied")
        return

    proposal["status"] = "watching"
    proposal["status_reason"] = "Execution packet was marked blocked; keep the proposal out of the immediate apply lane."
    if reason:
        proposal["status_reason"] = f"{proposal['status_reason']} Blocker: {reason}"
    proposal["next_action"] = "Resolve the recorded execution blocker before returning this proposal to ready-for-apply or ready-for-patch."


def _allowed_paths_for_category(category: str) -> list[str]:
    if category in AUTO_APPLY_ALLOWED_PATHS:
        return list(AUTO_APPLY_ALLOWED_PATHS[category])
    if category in PATCH_PLAN_ALLOWED_PATHS:
        return list(PATCH_PLAN_ALLOWED_PATHS[category])
    return ["local_kb/**", "tests/**", "docs/**", ".agents/skills/**"]


def _validation_plan_for_category(category: str) -> dict[str, Any]:
    commands = ["python -m unittest tests.test_kb_architect"]
    manual_checks = [
        "Confirm the diff stays inside the execution packet allowed_paths.",
        "Confirm no trusted cards, private cards, candidates, taxonomy routes, dependencies, or lockfiles changed.",
    ]

    if category == "install-check":
        commands = ["python -m unittest tests.test_codex_install"]
        manual_checks.append("Run python scripts/install_codex_kb.py --check --json after installer-affecting changes.")
    elif category == "core-tooling":
        commands.append(
            "python .agents/skills/local-kb-retrieve/scripts/kb_architect.py --run-id architect-smoke --max-events 20 --json"
        )
    elif category == "validation":
        manual_checks.append("The test change must fail against the old behavior or assert a new Architect closure contract.")
    elif category == "proposal-queue":
        manual_checks.append("Inspect kb/history/architecture/proposal_queue.json and confirm only queue metadata changed.")
    elif category in {"prompt", "runbook", "skill-maintenance"}:
        manual_checks.append("Inspect required prompt/runbook markers and run the matching prompt or install test when available.")

    return {
        "commands": commands,
        "manual_checks": manual_checks,
        "success_criteria": [
            "All listed commands pass.",
            "The implementation stays inside allowed_paths.",
            "The proposal is marked applied only after validation succeeds.",
        ],
        "failure_criteria": [
            "Any validation command fails.",
            "The needed change touches disallowed paths or broad mechanism code outside the packet.",
            "The implementation requires card-content maintenance, taxonomy movement, dependency changes, or human product judgment.",
        ],
    }


def _expected_effect_for_proposal(proposal: dict[str, Any], mode: str) -> str:
    title = str(proposal.get("title", "") or "the mechanism proposal")
    target = proposal.get("target", {})
    target_ref = ""
    if isinstance(target, dict):
        target_ref = str(target.get("ref", "") or "")
    target_label = f" for {target_ref}" if target_ref else ""
    if mode == "agent-ready-apply":
        return f"Trial a narrow mechanism update{target_label}: {title}."
    if mode == "patch-plan":
        return f"Prepare patch evidence{target_label} without applying repository writes: {title}."
    if mode == "blocked":
        return f"Keep the proposal out of apply until the recorded blocker is resolved{target_label}."
    if mode == "closed-applied":
        return f"Preserve applied mechanism history{target_label}; no sandbox write is expected."
    return f"Observe mechanism evidence{target_label}; no sandbox write is expected."


def _sandbox_apply_metadata(
    proposal: dict[str, Any],
    *,
    packet_id: str,
    mode: str,
    allowed_paths: list[str],
    disallowed_paths: list[str],
    validation_plan: dict[str, Any],
) -> dict[str, Any]:
    sandbox_ready = mode == "agent-ready-apply"
    planned_sandbox_path = f"{SANDBOX_TRIAL_ROOT}/{packet_id}"
    validation_commands = list(validation_plan.get("commands", []))
    manual_checks = list(validation_plan.get("manual_checks", []))
    return {
        "strategy": "sandbox-trial",
        "sandbox_ready": sandbox_ready,
        "sandbox_path": "",
        "planned_sandbox_path": planned_sandbox_path,
        "allowed_writes": list(allowed_paths) if sandbox_ready else [],
        "planned_write_surface": list(allowed_paths),
        "disallowed_writes": list(disallowed_paths),
        "expected_effect": _expected_effect_for_proposal(proposal, mode),
        "validation_commands": validation_commands,
        "manual_checks": manual_checks,
        "merge_decision": {
            "decision_required": sandbox_ready,
            "merge_when": [
                "Sandbox diff stays inside allowed_writes.",
                "Validation commands pass and manual checks are satisfied.",
                "The reviewed effect matches expected_effect.",
            ],
            "record_fields": {
                "proposal.status": "applied",
                "proposal.execution_state.state": "applied",
                "proposal.execution_state.sandbox_path": "<sandbox_path_or_planned_sandbox_path>",
                "proposal.execution_state.validation": "passed",
            },
        },
        "block_decision": {
            "decision_required": sandbox_ready,
            "block_when": [
                "Sandbox diff touches disallowed_writes or escapes allowed_writes.",
                "Validation commands fail or cannot be run.",
                "Manual checks fail, expected_effect is not achieved, or the change needs human/card-content judgment.",
            ],
            "record_fields": {
                "proposal.status": "watching",
                "proposal.execution_state.state": "blocked",
                "proposal.execution_state.blocker": "<concrete_blocker>",
                "proposal.execution_state.sandbox_path": "<sandbox_path_or_planned_sandbox_path>",
            },
        },
    }


def _execution_state_for_proposal(proposal: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
    existing = proposal.get("execution_state")
    status = str(proposal.get("status", "") or "").strip()
    state_name = {
        "ready-for-apply": "ready-for-agent",
        "ready-for-patch": "patch-required",
        "applied": "applied",
        "rejected": "closed",
        "superseded": "closed",
        "watching": "watching",
        "new": "watching",
    }.get(status, "watching")
    if isinstance(existing, dict):
        state = str(existing.get("state", "") or "").strip().lower()
        if state in EXECUTION_CLOSURE_STATES:
            carried = dict(existing)
            carried["state"] = state
            carried.setdefault("updated_at", generated_at)
            return carried
        if state == state_name and state in EXECUTION_CONTINUATION_STATES:
            carried = dict(existing)
            carried["state"] = state
            carried.setdefault("ready_since_at", existing.get("updated_at") or generated_at)
            carried["last_seen_at"] = generated_at
            carried["updated_at"] = generated_at
            return carried

    result = {
        "state": state_name,
        "updated_at": generated_at,
        "reason": str(proposal.get("status_reason", "") or ""),
    }
    if state_name in EXECUTION_CONTINUATION_STATES:
        result["ready_since_at"] = generated_at
        result["last_seen_at"] = generated_at
    return result


def _execution_mode_for(proposal: dict[str, Any], execution_state: dict[str, Any]) -> str:
    state = str(execution_state.get("state", "") or "")
    if state == "applied":
        return "closed-applied"
    if state == "blocked":
        return "blocked"
    status = str(proposal.get("status", "") or "")
    category = str(proposal.get("category", "") or "")
    if status == "ready-for-apply" and category in AUTO_APPLY_CATEGORIES:
        return "agent-ready-apply"
    if status == "ready-for-patch":
        return "patch-plan"
    if status in {"rejected", "superseded"}:
        return "terminal-record"
    return "watch"


def _implementation_prompt_for_mode(mode: str, category: str) -> str:
    if mode == "agent-ready-apply":
        return (
            "A follow-on Architect agent may implement this now only if the edit stays inside allowed_paths, "
            "keeps the diff narrow and reversible, runs the validation_plan immediately, and then marks the proposal applied."
        )
    if mode == "patch-plan":
        return (
            "Generate or refine a patch and validation plan for this medium-safety mechanism change. "
            "Do not mark it applied until the patch is implemented and validated."
        )
    if mode == "blocked":
        return "Resolve the recorded blocker before returning this proposal to a ready execution lane."
    if mode == "closed-applied":
        return "Keep this applied mechanism change as terminal history unless a concrete regression appears."
    if mode == "terminal-record":
        return "Do not execute this proposal; preserve the terminal decision as queue history."
    return f"Keep observing this {category} proposal until evidence, impact, safety, and validation readiness justify action."


def _build_execution_packet(
    proposal: dict[str, Any],
    *,
    generated_at: str,
    execution_state: dict[str, Any],
) -> dict[str, Any]:
    proposal_id = str(proposal.get("proposal_id", "") or "")
    category = str(proposal.get("category", "") or "")
    status = str(proposal.get("status", "") or "")
    mode = _execution_mode_for(proposal, execution_state)
    architect_agent_may_apply = mode == "agent-ready-apply"
    packet_id = f"arch-exec-{proposal_id}"
    allowed_paths = _allowed_paths_for_category(category)
    disallowed_paths = list(DISALLOWED_EXECUTION_PATHS)
    validation_plan = _validation_plan_for_category(category)
    return {
        "schema_version": ARCHITECT_SCHEMA_VERSION,
        "kind": "local-kb-architect-execution-packet",
        "packet_id": packet_id,
        "proposal_id": proposal_id,
        "generated_at": generated_at,
        "category": category,
        "status": status,
        "execution_mode": mode,
        "runner_direct_write_allowed": False,
        "architect_agent_direct_apply_allowed": architect_agent_may_apply,
        "requires_patch_or_human": mode == "patch-plan",
        "allowed_action_surface": (
            "prompt/runbook/validation/proposal-queue"
            if architect_agent_may_apply
            else "patch-plan-or-human-review"
        ),
        "allowed_paths": allowed_paths,
        "disallowed_paths": disallowed_paths,
        "implementation_prompt": _implementation_prompt_for_mode(mode, category),
        "validation_plan": validation_plan,
        "sandbox_apply": _sandbox_apply_metadata(
            proposal,
            packet_id=packet_id,
            mode=mode,
            allowed_paths=allowed_paths,
            disallowed_paths=disallowed_paths,
            validation_plan=validation_plan,
        ),
        "closure_contract": {
            "mark_applied_when": [
                "The implementation stayed inside allowed_paths.",
                "All validation_plan commands passed.",
                "A KB postflight observation records the applied mechanism change when the pass exposed a reusable lesson.",
            ],
            "mark_blocked_when": [
                "The required change touches disallowed_paths or broad mechanism code.",
                "The validation bundle cannot be run or fails after a reasonable fix attempt.",
                "The change requires card-content maintenance, taxonomy movement, dependency installation, or unresolved human judgment.",
            ],
            "applied_update": {
                "proposal.status": "applied",
                "proposal.execution_state.state": "applied",
            },
            "blocked_update": {
                "proposal.status": "watching",
                "proposal.execution_state.state": "blocked",
            },
        },
        "execution_state": execution_state,
    }


def _attach_execution_packets(proposals: list[dict[str, Any]], *, generated_at: str) -> None:
    for proposal in proposals:
        execution_state = _execution_state_for_proposal(proposal, generated_at=generated_at)
        proposal["execution_state"] = execution_state
        proposal["execution_packet"] = _build_execution_packet(
            proposal,
            generated_at=generated_at,
            execution_state=execution_state,
        )


def _execution_summary(proposals: list[dict[str, Any]]) -> dict[str, Any]:
    mode_counts: dict[str, int] = {}
    state_counts: dict[str, int] = {}
    sandbox_ready_count = 0
    for proposal in proposals:
        packet = proposal.get("execution_packet", {})
        mode = str(packet.get("execution_mode", "") or "unknown") if isinstance(packet, dict) else "unknown"
        sandbox_apply = packet.get("sandbox_apply", {}) if isinstance(packet, dict) else {}
        if isinstance(sandbox_apply, dict) and sandbox_apply.get("sandbox_ready") is True:
            sandbox_ready_count += 1
        state = str(proposal.get("execution_state", {}).get("state", "") or "unknown")
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        state_counts[state] = state_counts.get(state, 0) + 1
    return {
        "mode_counts": dict(sorted(mode_counts.items())),
        "state_counts": dict(sorted(state_counts.items())),
        "agent_ready_count": mode_counts.get("agent-ready-apply", 0),
        "patch_plan_count": mode_counts.get("patch-plan", 0),
        "blocked_count": state_counts.get("blocked", 0),
        "applied_count": state_counts.get("applied", 0),
        "sandbox_ready_count": sandbox_ready_count,
    }


def _sandbox_ready_packets(proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ready_packets: list[dict[str, Any]] = []
    for proposal in proposals:
        packet = proposal.get("execution_packet", {})
        sandbox_apply = packet.get("sandbox_apply", {}) if isinstance(packet, dict) else {}
        if not isinstance(sandbox_apply, dict) or sandbox_apply.get("sandbox_ready") is not True:
            continue
        ready_packets.append(
            {
                "packet_id": str(packet.get("packet_id", "") or ""),
                "proposal_id": str(proposal.get("proposal_id", "") or ""),
                "category": str(proposal.get("category", "") or ""),
                "status": str(proposal.get("status", "") or ""),
                "execution_mode": str(packet.get("execution_mode", "") or ""),
                "planned_sandbox_path": str(sandbox_apply.get("planned_sandbox_path", "") or ""),
                "allowed_writes": list(sandbox_apply.get("allowed_writes", [])),
                "disallowed_writes": list(sandbox_apply.get("disallowed_writes", [])),
                "expected_effect": str(sandbox_apply.get("expected_effect", "") or ""),
                "validation_commands": list(sandbox_apply.get("validation_commands", [])),
                "manual_checks": list(sandbox_apply.get("manual_checks", [])),
                "ready_since_at": str(proposal.get("execution_state", {}).get("ready_since_at", "") or ""),
                "merge_decision_fields": dict(sandbox_apply.get("merge_decision", {}).get("record_fields", {})),
                "block_decision_fields": dict(sandbox_apply.get("block_decision", {}).get("record_fields", {})),
            }
        )
    return ready_packets


def select_sandbox_trial_packet(queue: dict[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for proposal in queue.get("proposals", []):
        if not isinstance(proposal, dict):
            continue
        if str(proposal.get("status", "") or "") != "ready-for-apply":
            continue
        execution_state = proposal.get("execution_state", {})
        if not isinstance(execution_state, dict) or str(execution_state.get("state", "") or "") != "ready-for-agent":
            continue
        packet = proposal.get("execution_packet", {})
        if not isinstance(packet, dict):
            continue
        sandbox_apply = packet.get("sandbox_apply", {})
        if not isinstance(sandbox_apply, dict) or sandbox_apply.get("sandbox_ready") is not True:
            continue
        if packet.get("runner_direct_write_allowed") is not False:
            continue
        if packet.get("architect_agent_direct_apply_allowed") is not True:
            continue
        candidates.append(
            {
                "proposal": proposal,
                "packet": packet,
                "sandbox_apply": sandbox_apply,
                "ready_since_at": str(execution_state.get("ready_since_at", "") or ""),
            }
        )

    if not candidates:
        return {}

    candidates.sort(
        key=lambda item: (
            item["ready_since_at"] or "9999",
            SANDBOX_TRIAL_CATEGORY_PRIORITY.get(str(item["proposal"].get("category", "") or ""), 99),
            str(item["proposal"].get("proposal_id", "") or ""),
        )
    )
    selected = candidates[0]
    proposal = selected["proposal"]
    packet = selected["packet"]
    sandbox_apply = selected["sandbox_apply"]
    sandbox_path = str(sandbox_apply.get("planned_sandbox_path", "") or "")
    return {
        "schema_version": ARCHITECT_SCHEMA_VERSION,
        "kind": "local-kb-architect-sandbox-trial-selection",
        "proposal_id": str(proposal.get("proposal_id", "") or ""),
        "packet_id": str(packet.get("packet_id", "") or ""),
        "category": str(proposal.get("category", "") or ""),
        "status": str(proposal.get("status", "") or ""),
        "execution_state": str(proposal.get("execution_state", {}).get("state", "") or ""),
        "planned_sandbox_path": sandbox_path,
        "allowed_writes": list(sandbox_apply.get("allowed_writes", [])),
        "disallowed_writes": list(sandbox_apply.get("disallowed_writes", [])),
        "expected_effect": str(sandbox_apply.get("expected_effect", "") or ""),
        "validation_commands": list(sandbox_apply.get("validation_commands", [])),
        "manual_checks": list(sandbox_apply.get("manual_checks", [])),
        "ready_since_at": selected["ready_since_at"],
        "result_record_command": (
            "python .agents/skills/local-kb-retrieve/scripts/kb_architect.py "
            f"--record-trial-result {sandbox_path}/trial_result.json --json"
        ),
        "decision_required": "run-sandbox-trial-or-record-blocker",
    }


def _attach_selected_sandbox_trial(queue: dict[str, Any]) -> dict[str, Any]:
    selected = select_sandbox_trial_packet(queue)
    queue["selected_sandbox_trial"] = selected
    return selected


def _normalize_repo_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.strip("/")


def _path_matches(pattern: str, path: str) -> bool:
    normalized_pattern = _normalize_repo_path(pattern)
    normalized_path = _normalize_repo_path(path)
    if not normalized_pattern or not normalized_path:
        return False
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3].rstrip("/")
        return normalized_path == prefix or normalized_path.startswith(f"{prefix}/")
    return normalized_path == normalized_pattern or fnmatch.fnmatch(normalized_path, normalized_pattern)


def _touched_path_check(touched_paths: list[str], allowed_writes: list[str], disallowed_writes: list[str]) -> dict[str, Any]:
    normalized_paths = [_normalize_repo_path(path) for path in touched_paths if _normalize_repo_path(path)]
    disallowed = [
        path
        for path in normalized_paths
        if any(_path_matches(pattern, path) for pattern in disallowed_writes)
    ]
    outside_allowed = [
        path
        for path in normalized_paths
        if not any(_path_matches(pattern, path) for pattern in allowed_writes)
    ]
    return {
        "touched_paths": normalized_paths,
        "allowed_writes": list(allowed_writes),
        "disallowed_writes": list(disallowed_writes),
        "disallowed_touched_paths": disallowed,
        "outside_allowed_paths": outside_allowed,
        "passed": bool(normalized_paths) and not disallowed and not outside_allowed,
    }


def _all_results_passed(results: list[dict[str, Any]]) -> bool:
    if not results:
        return False
    for result in results:
        status = str(result.get("status", "") or "").strip().lower()
        if status not in {"passed", "ok", "success"}:
            return False
    return True


def _find_proposal(proposals: list[dict[str, Any]], proposal_id: str) -> dict[str, Any]:
    for proposal in proposals:
        if str(proposal.get("proposal_id", "") or "") == proposal_id:
            return proposal
    raise ValueError(f"Architect proposal not found: {proposal_id}")


def _normalize_trial_results(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _validate_trial_target(proposal: dict[str, Any], packet_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if str(proposal.get("status", "") or "") != "ready-for-apply":
        raise ValueError("Architect sandbox trial result can only close a ready-for-apply proposal.")
    packet = proposal.get("execution_packet", {})
    if not isinstance(packet, dict):
        raise ValueError("Architect proposal does not have an execution packet.")
    if packet_id and str(packet.get("packet_id", "") or "") != packet_id:
        raise ValueError("Architect sandbox trial packet_id does not match the proposal execution packet.")
    sandbox_apply = packet.get("sandbox_apply", {})
    if not isinstance(sandbox_apply, dict) or sandbox_apply.get("sandbox_ready") is not True:
        raise ValueError("Architect proposal is not sandbox-ready.")
    if packet.get("architect_agent_direct_apply_allowed") is not True:
        raise ValueError("Architect proposal is not agent-ready for direct sandbox apply.")
    return packet, sandbox_apply


def _build_trial_result_payload(
    *,
    trial_result: dict[str, Any],
    proposal: dict[str, Any],
    packet: dict[str, Any],
    sandbox_apply: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    touched_paths = [
        _normalize_repo_path(path)
        for path in trial_result.get("touched_paths", [])
        if _normalize_repo_path(path)
    ]
    allowed_writes = list(sandbox_apply.get("allowed_writes", []))
    disallowed_writes = list(sandbox_apply.get("disallowed_writes", []))
    path_check = _touched_path_check(touched_paths, allowed_writes, disallowed_writes)
    validation_results = _normalize_trial_results(trial_result.get("validation_results", []))
    manual_check_results = _normalize_trial_results(trial_result.get("manual_check_results", []))
    return {
        "schema_version": ARCHITECT_SCHEMA_VERSION,
        "kind": "local-kb-architect-sandbox-trial-result",
        "recorded_at": generated_at,
        "run_id": str(trial_result.get("run_id", "") or ""),
        "proposal_id": str(proposal.get("proposal_id", "") or ""),
        "packet_id": str(packet.get("packet_id", "") or ""),
        "decision": str(trial_result.get("decision", "") or "").strip().lower(),
        "sandbox_path": str(
            trial_result.get("sandbox_path")
            or sandbox_apply.get("sandbox_path")
            or sandbox_apply.get("planned_sandbox_path")
            or ""
        ),
        "touched_paths": touched_paths,
        "diff_within_allowed": bool(trial_result.get("diff_within_allowed", False)),
        "path_check": path_check,
        "validation_results": validation_results,
        "manual_check_results": manual_check_results,
        "validation_passed": _all_results_passed(validation_results),
        "manual_checks_passed": _all_results_passed(manual_check_results),
        "reason": str(trial_result.get("reason", "") or "").strip(),
        "expected_effect": str(sandbox_apply.get("expected_effect", "") or ""),
    }


def _trial_result_supports_applied(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("diff_within_allowed", False)
        and payload.get("path_check", {}).get("passed", False)
        and payload.get("validation_passed", False)
        and payload.get("manual_checks_passed", False)
    )


def _record_architect_trial_event(repo_root: Path, payload: dict[str, Any]) -> str:
    event = build_history_event(
        "architect-sandbox-trial",
        source={
            "kind": "architect-maintenance",
            "agent": "kb-architect",
            "thread_ref": payload.get("run_id", ""),
            "project_ref": repo_root.name,
            "workspace_root": str(repo_root),
        },
        target={
            "kind": "architect-proposal",
            "proposal_id": payload.get("proposal_id", ""),
            "packet_id": payload.get("packet_id", ""),
        },
        rationale=str(payload.get("reason", "") or f"Architect sandbox trial recorded {payload.get('decision', '')}."),
        context={"sandbox_trial": payload},
    )
    record_history_event(repo_root, event)
    return str(event["event_id"])


def _sandbox_trial_final_state(
    *,
    repo_root: Path,
    queue: dict[str, Any],
    proposal: dict[str, Any],
    payload: dict[str, Any],
    event_id: str,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": ARCHITECT_SCHEMA_VERSION,
        "kind": "local-kb-architect-sandbox-trial-final-state",
        "recorded_at": generated_at,
        "run_id": str(payload.get("run_id", "") or ""),
        "proposal_id": str(payload.get("proposal_id", "") or ""),
        "packet_id": str(payload.get("packet_id", "") or ""),
        "decision": str(payload.get("decision", "") or ""),
        "history_event_id": event_id,
        "sandbox_path": str(payload.get("sandbox_path", "") or ""),
        "touched_paths": list(payload.get("touched_paths", [])),
        "validation_passed": bool(payload.get("validation_passed", False)),
        "manual_checks_passed": bool(payload.get("manual_checks_passed", False)),
        "final_status": str(proposal.get("status", "") or ""),
        "final_status_reason": str(proposal.get("status_reason", "") or ""),
        "final_execution_state": dict(proposal.get("execution_state", {}))
        if isinstance(proposal.get("execution_state"), dict)
        else {},
        "final_status_counts": _status_counts(queue.get("proposals", [])),
        "final_execution_summary": dict(queue.get("execution_summary", {}))
        if isinstance(queue.get("execution_summary"), dict)
        else {},
        "final_selected_sandbox_trial": dict(queue.get("selected_sandbox_trial", {}))
        if isinstance(queue.get("selected_sandbox_trial"), dict)
        else {},
    }


def _write_sandbox_trial_final_state(
    repo_root: Path,
    *,
    queue: dict[str, Any],
    proposal: dict[str, Any],
    payload: dict[str, Any],
    event_id: str,
    generated_at: str,
) -> dict[str, Any]:
    run_id = sanitize_run_id(str(payload.get("run_id", "") or ""))
    if not run_id:
        return {"updated": False, "reason": "trial result did not include run_id"}
    run_dir = architect_run_dir(repo_root, run_id)
    if not run_dir.exists():
        return {
            "updated": False,
            "reason": "architect run directory was not found",
            "run_dir": relative_repo_path(repo_root, run_dir),
        }

    final_state = _sandbox_trial_final_state(
        repo_root=repo_root,
        queue=queue,
        proposal=proposal,
        payload=payload,
        event_id=event_id,
        generated_at=generated_at,
    )
    final_state_path = run_dir / "sandbox_trial_final_state.json"
    write_json_file(final_state_path, final_state)

    report_path = run_dir / REPORT_FILENAME
    report_updated = False
    if report_path.exists():
        report = load_json_object(report_path)
        report["trial_result_summary"] = final_state
        report["final_status_counts"] = final_state["final_status_counts"]
        report["final_execution_summary"] = final_state["final_execution_summary"]
        report["final_selected_sandbox_trial"] = final_state["final_selected_sandbox_trial"]
        report["finalized_at"] = generated_at
        artifact_paths = report.setdefault("artifact_paths", {})
        if isinstance(artifact_paths, dict):
            artifact_paths["trial_final_state_path"] = relative_repo_path(repo_root, final_state_path)
        write_json_file(report_path, report)
        report_updated = True

    return {
        "updated": True,
        "run_id": run_id,
        "final_state_path": relative_repo_path(repo_root, final_state_path),
        "report_path": relative_repo_path(repo_root, report_path),
        "report_updated": report_updated,
    }


def record_architect_sandbox_trial_result(
    repo_root: Path,
    trial_result: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now_iso()
    proposal_id = str(trial_result.get("proposal_id", "") or "").strip()
    packet_id = str(trial_result.get("packet_id", "") or "").strip()
    decision = str(trial_result.get("decision", "") or "").strip().lower()
    if decision not in SANDBOX_TRIAL_DECISIONS:
        raise ValueError("Architect sandbox trial decision must be applied or blocked.")
    if not proposal_id:
        raise ValueError("Architect sandbox trial result requires proposal_id.")

    queue_path = architect_queue_path(repo_root)
    queue = load_json_object(queue_path)
    proposals = list(queue.get("proposals", []))
    proposal = _find_proposal(proposals, proposal_id)
    packet, sandbox_apply = _validate_trial_target(proposal, packet_id)
    payload = _build_trial_result_payload(
        trial_result=trial_result,
        proposal=proposal,
        packet=packet,
        sandbox_apply=sandbox_apply,
        generated_at=generated_at,
    )
    if decision == "applied" and not _trial_result_supports_applied(payload):
        raise ValueError("Architect sandbox trial cannot be marked applied until paths, validation, and manual checks pass.")
    if decision == "blocked" and not payload["reason"]:
        raise ValueError("Architect blocked sandbox trial requires a concrete reason.")

    proposal["sandbox_trial"] = payload
    proposal.setdefault("sandbox_trials", []).append(payload)
    proposal["updated_at"] = generated_at
    if decision == "applied":
        proposal["status"] = "applied"
        proposal["status_reason"] = str(payload["reason"] or "Sandbox trial stayed inside allowed writes and validation passed.")
        proposal["next_action"] = _next_action_for_status("applied")
        proposal["execution_state"] = {
            "state": "applied",
            "updated_at": generated_at,
            "reason": proposal["status_reason"],
            "sandbox_path": payload["sandbox_path"],
            "validation": "passed",
            "trial_recorded_at": generated_at,
        }
    else:
        proposal["status"] = "watching"
        proposal["status_reason"] = f"Sandbox trial blocked. Blocker: {payload['reason']}"
        proposal["next_action"] = "Resolve the recorded execution blocker before returning this proposal to ready-for-apply."
        proposal["execution_state"] = {
            "state": "blocked",
            "updated_at": generated_at,
            "reason": payload["reason"],
            "blocker": payload["reason"],
            "sandbox_path": payload["sandbox_path"],
            "validation": "failed" if not payload["validation_passed"] else "blocked",
            "trial_recorded_at": generated_at,
        }

    _attach_execution_packets(proposals, generated_at=generated_at)
    queue["proposals"] = proposals
    queue["proposal_count"] = len(proposals)
    queue["updated_at"] = generated_at
    queue["execution_summary"] = _execution_summary(proposals)
    queue["sandbox_ready_packets"] = _sandbox_ready_packets(proposals)
    queue["selected_sandbox_trial"] = select_sandbox_trial_packet(queue)
    event_id = _record_architect_trial_event(repo_root, payload)
    queue["last_sandbox_trial_event_id"] = event_id
    write_json_file(queue_path, queue)
    run_report_update = _write_sandbox_trial_final_state(
        repo_root,
        queue=queue,
        proposal=proposal,
        payload=payload,
        event_id=event_id,
        generated_at=generated_at,
    )
    return {
        "schema_version": ARCHITECT_SCHEMA_VERSION,
        "kind": "local-kb-architect-sandbox-trial-record",
        "recorded_at": generated_at,
        "queue_path": relative_repo_path(repo_root, queue_path),
        "history_event_id": event_id,
        "proposal_id": proposal_id,
        "packet_id": payload["packet_id"],
        "decision": decision,
        "sandbox_trial": payload,
        "execution_summary": queue["execution_summary"],
        "selected_sandbox_trial": queue["selected_sandbox_trial"],
        "run_report_update": run_report_update,
    }


def _proposal_cluster_key(proposal: dict[str, Any]) -> str:
    category = str(proposal.get("category", "") or "").strip().lower()
    target = proposal.get("target", {})
    if isinstance(target, dict):
        target_ref = str(target.get("ref", "") or "").strip().lower()
    else:
        target_ref = str(proposal.get("target_ref", "") or "").strip().lower()
    return f"{category}::{target_ref}"


def _proposal_primary_rank(proposal: dict[str, Any]) -> tuple[int, int, str]:
    status = str(proposal.get("status", "") or "").strip()
    status_rank = {
        "applied": 0,
        "ready-for-apply": 1,
        "ready-for-patch": 2,
        "watching": 3,
        "new": 4,
        "rejected": 5,
        "superseded": 6,
    }.get(status, 7)
    support_count = int(proposal.get("evidence", {}).get("supporting_run_count", 0) or 0)
    return (status_rank, -support_count, str(proposal.get("proposal_id", "") or ""))


def _merge_duplicate_source_actions(primary: dict[str, Any], duplicate: dict[str, Any]) -> None:
    primary_actions = primary.setdefault("source_actions", [])
    if not isinstance(primary_actions, list):
        primary_actions = []
        primary["source_actions"] = primary_actions
    seen = {
        str(item.get("action_key", "") or "")
        for item in primary_actions
        if isinstance(item, dict)
    }
    for action in duplicate.get("source_actions", []):
        if not isinstance(action, dict):
            continue
        key = str(action.get("action_key", "") or "")
        if key and key in seen:
            continue
        primary_actions.append(action)
        if key:
            seen.add(key)
    if isinstance(primary.get("evidence"), dict):
        primary["evidence"]["source_action_count"] = len(primary_actions)


def _collapse_duplicate_proposals(
    proposals: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    *,
    generated_at: str,
) -> list[dict[str, Any]]:
    clusters: dict[str, list[dict[str, Any]]] = {}
    for proposal in proposals:
        key = _proposal_cluster_key(proposal)
        if not key or key == "::":
            continue
        clusters.setdefault(key, []).append(proposal)

    for cluster_items in clusters.values():
        if len(cluster_items) <= 1:
            continue
        primary = sorted(cluster_items, key=_proposal_primary_rank)[0]
        primary_id = str(primary.get("proposal_id", "") or "")
        for duplicate in cluster_items:
            if duplicate is primary:
                continue
            previous_status = str(duplicate.get("status", "") or "")
            _merge_duplicate_source_actions(primary, duplicate)
            duplicate["status"] = "superseded"
            duplicate["status_reason"] = f"Superseded by {primary_id} during Architect queue hygiene for the same mechanism target."
            duplicate["superseded_by"] = primary_id
            duplicate["next_action"] = _next_action_for_status("superseded")
            duplicate["updated_at"] = generated_at
            decisions.append(
                {
                    "proposal_id": str(duplicate.get("proposal_id", "") or ""),
                    "previous_status": previous_status,
                    "new_status": "superseded",
                    "reason": duplicate["status_reason"],
                }
            )
    return proposals


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
    if prior.get("status") in TERMINAL_STATUSES:
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
    if prior:
        _apply_prior_execution_closure(proposal, prior, generated_at=generated_at)
        if "execution_state" not in proposal:
            prior_state = _prior_continuation_state(prior)
            if prior_state:
                proposal["execution_state"] = prior_state
    status = str(proposal.get("status", status) or status)
    status_reason = str(proposal.get("status_reason", status_reason) or status_reason)
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
    _apply_prior_execution_closure(carried, proposal, generated_at=generated_at)
    status = str(carried.get("status", "watching") or "watching")
    if status not in TERMINAL_STATUSES:
        state = carried.get("execution_state", {})
        state_name = str(state.get("state", "") or "") if isinstance(state, dict) else ""
        if state_name != "blocked":
            carried["status_reason"] = "No fresh matching signal appeared in this run."
            carried["next_action"] = _next_action_for_status("watching")
        status = "watching"
        carried["status"] = status
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

    proposals = _collapse_duplicate_proposals(proposals, decisions, generated_at=generated_at)
    _attach_execution_packets(proposals, generated_at=generated_at)

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
        "execution_summary": _execution_summary(proposals),
        "sandbox_ready_packets": _sandbox_ready_packets(proposals),
        "proposals": proposals,
    }
    _attach_selected_sandbox_trial(queue)
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
        outcome="Architect skipped before proposal review because another core maintenance lane was still running.",
        comment="Architect should not overlap with Sleep or Dream maintenance runs.",
        suggested_action="none",
        scenario="Scheduled Architect run starts while another KB maintenance lane is still running.",
        action_taken="Skipped mechanism proposal maintenance and wrote a history note.",
        observed_result="No proposal queue changes were made.",
        operational_use="Retry on the next scheduled Architect run after the active maintenance lane completes.",
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
) -> dict[str, Any]:
    generated_at = utc_now_iso()
    resolved_run_id = sanitize_run_id(run_id or f"kb-architect-{utc_now_compact()}")
    run_dir = architect_run_dir(repo_root, resolved_run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    lane_lock = acquire_lane_lock(repo_root, "kb-architect", run_id=resolved_run_id)
    lock_released = False
    try:
        write_lane_status(repo_root, "kb-architect", "running", run_id=resolved_run_id)

        execution_plan = build_initial_execution_plan(repo_root, run_id=resolved_run_id, generated_at=generated_at)
        write_json_file(run_dir / EXECUTION_PLAN_FILENAME, execution_plan)

        guards = build_architect_guards(repo_root)
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
            write_lane_status(repo_root, "kb-architect", "skipped", run_id=resolved_run_id)
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
                "reason": "maintenance-lane-active",
                "guards": guards,
                "history_event_ids": [event_id],
                "artifact_paths": {
                    "run_dir": relative_repo_path(repo_root, run_dir),
                    "plan_path": relative_repo_path(repo_root, run_dir / PLAN_FILENAME),
                    "execution_plan_path": relative_repo_path(repo_root, run_dir / EXECUTION_PLAN_FILENAME),
                    "report_path": relative_repo_path(repo_root, run_dir / REPORT_FILENAME),
                },
            }
            result["lane_lock"] = lane_lock
            result["lock_release"] = release_lane_lock(repo_root, "kb-architect", run_id=resolved_run_id)
            lock_released = True
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
        selected_sandbox_trial = dict(queue.get("selected_sandbox_trial", {}))
        write_json_file(run_dir / SIGNALS_FILENAME, signals)
        write_json_file(run_dir / PROPOSALS_FILENAME, queue)
        write_json_file(run_dir / DECISIONS_FILENAME, decisions)
        write_json_file(
            run_dir / TRIAL_SELECTION_FILENAME,
            selected_sandbox_trial
            if selected_sandbox_trial
            else {
                "schema_version": ARCHITECT_SCHEMA_VERSION,
                "kind": "local-kb-architect-sandbox-trial-selection",
                "run_id": resolved_run_id,
                "selected": False,
                "reason": "No sandbox-ready ready-for-apply packet is available in this run.",
            },
        )
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
        _set_checkpoint_status(
            execution_plan,
            "sandbox-trial-selection",
            "completed" if selected_sandbox_trial else "skipped",
            (
                f"Selected {selected_sandbox_trial.get('packet_id')} for one sandbox trial."
                if selected_sandbox_trial
                else "No sandbox-ready ready-for-apply packet was available."
            ),
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

        execution_summary = queue.get("execution_summary", {})
        sandbox_ready_packets = list(queue.get("sandbox_ready_packets", []))
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
            "execution_summary": execution_summary,
            "agent_ready_count": int(execution_summary.get("agent_ready_count", 0) or 0),
            "patch_plan_count": int(execution_summary.get("patch_plan_count", 0) or 0),
            "sandbox_ready_count": int(execution_summary.get("sandbox_ready_count", 0) or 0),
            "sandbox_ready_packets": sandbox_ready_packets,
            "selected_sandbox_trial": selected_sandbox_trial,
            "blocked_execution_count": int(execution_summary.get("blocked_count", 0) or 0),
            "applied_execution_count": int(execution_summary.get("applied_count", 0) or 0),
            "skipped_non_mechanism_action_count": signals["skipped_non_mechanism_action_count"],
            "artifact_paths": {
                "run_dir": relative_repo_path(repo_root, run_dir),
                "plan_path": relative_repo_path(repo_root, run_dir / PLAN_FILENAME),
                "preflight_path": relative_repo_path(repo_root, run_dir / PREFLIGHT_FILENAME),
                "signals_path": relative_repo_path(repo_root, run_dir / SIGNALS_FILENAME),
                "proposals_path": relative_repo_path(repo_root, run_dir / PROPOSALS_FILENAME),
                "decisions_path": relative_repo_path(repo_root, run_dir / DECISIONS_FILENAME),
                "trial_selection_path": relative_repo_path(repo_root, run_dir / TRIAL_SELECTION_FILENAME),
                "execution_plan_path": relative_repo_path(repo_root, run_dir / EXECUTION_PLAN_FILENAME),
                "queue_path": relative_repo_path(repo_root, architect_queue_path(repo_root)),
                "report_path": relative_repo_path(repo_root, run_dir / REPORT_FILENAME),
                "source_consolidation_proposal_path": consolidation.get("artifact_paths", {}).get("proposal_path", ""),
            },
        }
        write_json_file(run_dir / REPORT_FILENAME, result)
        write_lane_status(repo_root, "kb-architect", "completed", run_id=resolved_run_id)
        result["lock_release"] = release_lane_lock(repo_root, "kb-architect", run_id=resolved_run_id)
        lock_released = True
        write_json_file(run_dir / REPORT_FILENAME, result)
        return result
    except Exception as exc:
        write_lane_status(repo_root, "kb-architect", "failed", run_id=resolved_run_id, note=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if not lock_released:
            release_lane_lock(repo_root, "kb-architect", run_id=resolved_run_id)
