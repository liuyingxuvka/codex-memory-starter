from __future__ import annotations

from pathlib import Path
from typing import Any

from local_kb.common import normalize_string_list, parse_route_segments, safe_float
from local_kb.store import load_yaml_file


APPLY_MODE_SEMANTIC_REVIEW = "semantic-review"
SEMANTIC_REVIEW_PLAN_KIND = "local-kb-semantic-review-plan"
SEMANTIC_REVIEW_TRUSTED_AUTO_LIMIT = 3

SEMANTIC_REVIEW_ACTION_TYPES = {
    "review-candidate",
    "review-confidence",
    "review-entry-update",
}

SEMANTIC_REVIEW_DECISIONS = {
    "keep",
    "rewrite",
    "adjust-confidence",
    "promote",
    "demote",
    "deprecate",
    "split",
    "merge",
}

SEMANTIC_REVIEW_AUTO_APPLY_DECISIONS = {
    "keep",
    "rewrite",
    "adjust-confidence",
    "promote",
    "demote",
    "deprecate",
}

SEMANTIC_REVIEW_ALLOWED_UPDATE_FIELDS = {
    "title",
    "type",
    "domain_path",
    "cross_index",
    "related_cards",
    "tags",
    "trigger_keywords",
    "if",
    "action",
    "predict",
    "use",
    "confidence",
}

SEMANTIC_REVIEW_TEXT_FIELDS = {
    "title",
    "if",
    "action",
    "predict",
    "use",
}


def is_semantic_review_action(action: dict[str, Any]) -> bool:
    return str(action.get("action_type", "") or "").strip() in SEMANTIC_REVIEW_ACTION_TYPES


def is_trusted_card(entry: dict[str, Any]) -> bool:
    return str(entry.get("status", "") or "").strip().lower() == "trusted"


def normalize_trusted_card_limit(value: Any) -> int:
    try:
        raw_limit = int(value)
    except (TypeError, ValueError):
        raw_limit = SEMANTIC_REVIEW_TRUSTED_AUTO_LIMIT
    return max(0, min(raw_limit, SEMANTIC_REVIEW_TRUSTED_AUTO_LIMIT))


def normalize_semantic_decision(value: Any) -> str:
    decision = str(value or "").strip().lower()
    return decision if decision in SEMANTIC_REVIEW_DECISIONS else ""


def normalize_semantic_risk(value: Any, *, trusted_surface: bool, decision: str) -> str:
    risk = str(value or "").strip().lower()
    if risk in {"low", "medium", "high"}:
        return risk
    if decision in {"promote", "demote", "deprecate", "split", "merge"}:
        return "high"
    if trusted_surface:
        return "medium"
    return "low"


def normalize_semantic_review_plan(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "kind": SEMANTIC_REVIEW_PLAN_KIND,
            "trusted_card_limit": SEMANTIC_REVIEW_TRUSTED_AUTO_LIMIT,
            "decisions": [],
        }

    payload = load_yaml_file(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid semantic review plan: {path}")
    raw_decisions = payload.get("decisions", [])
    if not isinstance(raw_decisions, list):
        raise ValueError(f"semantic review plan decisions must be a list: {path}")
    decisions = [dict(item) for item in raw_decisions if isinstance(item, dict)]
    return {
        "kind": str(payload.get("kind") or SEMANTIC_REVIEW_PLAN_KIND),
        "trusted_card_limit": normalize_trusted_card_limit(payload.get("trusted_card_limit")),
        "decisions": decisions,
    }


def semantic_review_decisions_by_action_key(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    for decision in plan.get("decisions", []):
        if not isinstance(decision, dict):
            continue
        action_key = str(decision.get("action_key", "") or "").strip()
        if action_key and action_key not in decisions:
            decisions[action_key] = dict(decision)
    return decisions


def normalize_semantic_evidence_event_ids(decision: dict[str, Any]) -> list[str]:
    return normalize_string_list(decision.get("evidence_event_ids") or decision.get("event_ids") or [])


def semantic_review_updated_fields(decision: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    updates = decision.get("updated_fields", {})
    if not isinstance(updates, dict):
        return {}, ["updated_fields"]
    disallowed = sorted(str(field) for field in updates if str(field) not in SEMANTIC_REVIEW_ALLOWED_UPDATE_FIELDS)
    return dict(updates), disallowed


def semantic_review_changed_fields(previous: dict[str, Any], updated: dict[str, Any]) -> list[str]:
    fields = sorted(set(previous) | set(updated))
    return [field for field in fields if previous.get(field) != updated.get(field)]


def semantic_review_needs_i18n_followup(changed_fields: list[str], entry: dict[str, Any]) -> bool:
    return bool(set(changed_fields) & SEMANTIC_REVIEW_TEXT_FIELDS)


def semantic_review_entry_storage_path(repo_root: Path, entry: dict[str, Any], *, force_candidates: bool = False) -> Path:
    entry_id = str(entry.get("id", "") or "").strip()
    if not entry_id:
        raise ValueError("Semantic review entry storage requires an entry id.")
    if force_candidates:
        return repo_root / "kb" / "candidates" / f"{entry_id}.yaml"

    scope = str(entry.get("scope", "") or "").strip().lower() or "private"
    if scope not in {"public", "private"}:
        scope = "private"
    route_segments = parse_route_segments(entry.get("domain_path", []))
    target_dir = repo_root / "kb" / scope
    for segment in route_segments:
        target_dir = target_dir / segment
    return target_dir / f"{entry_id}.yaml"


def semantic_review_confidence(value: Any) -> float | None:
    confidence = safe_float(value, -1.0)
    if confidence < 0 or confidence > 1:
        return None
    return round(confidence, 2)


def build_semantic_review_suggestion(
    action: dict[str, Any],
    entry_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not is_semantic_review_action(action):
        return {}
    target = action.get("target", {}) if isinstance(action.get("target"), dict) else {}
    if str(target.get("kind", "") or "") != "entry":
        return {}
    entry_id = str(target.get("ref", "") or "").strip()
    entry = entry_lookup.get(entry_id)
    if not entry:
        return {}

    trusted = is_trusted_card(entry)
    return {
        "entry_id": entry_id,
        "current_status": str(entry.get("status", "") or "").strip(),
        "current_scope": str(entry.get("scope", "") or "").strip(),
        "current_confidence": semantic_review_confidence(entry.get("confidence")),
        "trusted_card_auto_limit": SEMANTIC_REVIEW_TRUSTED_AUTO_LIMIT,
        "supported_decisions": sorted(SEMANTIC_REVIEW_DECISIONS),
        "auto_apply_supported_decisions": sorted(SEMANTIC_REVIEW_AUTO_APPLY_DECISIONS),
        "trusted_surface": trusted,
        "required_artifact": "AI-authored semantic review plan YAML",
        "required_decision_fields": [
            "action_key",
            "entry_id",
            "apply",
            "decision",
            "risk",
            "evidence_event_ids",
            "rationale",
            "expected_retrieval_effect",
            "rollback_note",
        ],
        "risk_policy": {
            "low": "Candidate-card edits and explicit keep decisions are eligible when evidence is cited.",
            "medium": "Trusted-card rewrites or confidence changes count against the trusted-card budget.",
            "high": "Promotion, demotion, deprecation, split, and merge decisions require explicit AI rationale and still count against the trusted-card budget when they touch trusted surfaces.",
        },
    }
