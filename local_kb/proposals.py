from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from local_kb.common import normalize_string_list, safe_float
from local_kb.snapshots import resolve_run_dir


SCHEMA_VERSION = 1
REPORT_KIND = "local-kb-proposal-inspection"
ACTIONS_DIRNAME = "actions"
EDITORIAL_SUMMARY_LIMIT = 5
REQUIRED_STUB_FIELDS = (
    "schema_version",
    "kind",
    "run_id",
    "generated_at",
    "action_key",
    "action_type",
    "target",
    "priority_score",
    "event_count",
    "event_ids",
    "routes",
    "task_summaries",
    "signals",
    "suggested_artifact_kind",
    "apply_eligibility",
    "recommended_next_step",
    "ai_decision_required",
)


def relative_repo_path(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def proposal_actions_dir(
    repo_root: Path,
    *,
    run_id: str | None = None,
    run_dir: str | Path | None = None,
) -> Path:
    resolved_run_dir = resolve_run_dir(repo_root, run_id=run_id, run_dir=run_dir)
    return resolved_run_dir / ACTIONS_DIRNAME


def load_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def _normalize_target(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _normalize_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _normalize_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_proposal_stub(repo_root: Path, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    missing_fields = [field for field in REQUIRED_STUB_FIELDS if field not in payload]
    target = _normalize_target(payload.get("target"))
    normalized = {
        "schema_version": payload.get("schema_version"),
        "kind": str(payload.get("kind", "") or "").strip(),
        "run_id": str(payload.get("run_id", "") or "").strip(),
        "generated_at": str(payload.get("generated_at", "") or "").strip(),
        "action_key": str(payload.get("action_key", "") or "").strip(),
        "action_type": str(payload.get("action_type", "") or "").strip(),
        "target": target,
        "priority_score": safe_float(payload.get("priority_score"), 0.0),
        "event_count": _normalize_int(payload.get("event_count")),
        "event_ids": normalize_string_list(payload.get("event_ids")),
        "routes": normalize_string_list(payload.get("routes")),
        "task_summaries": normalize_string_list(payload.get("task_summaries")),
        "signals": _normalize_dict(payload.get("signals")),
        "suggested_artifact_kind": str(payload.get("suggested_artifact_kind", "") or "").strip(),
        "apply_eligibility": _normalize_dict(payload.get("apply_eligibility")),
        "recommended_next_step": str(payload.get("recommended_next_step", "") or "").strip(),
        "ai_decision_required": bool(payload.get("ai_decision_required", False)),
        "provenance": _normalize_dict(payload.get("provenance")),
        "timeline_summary": _normalize_dict(payload.get("timeline_summary")),
        "predictive_evidence_summary": _normalize_dict(payload.get("predictive_evidence_summary")),
        "suggested_confidence_change": _normalize_dict(payload.get("suggested_confidence_change")),
        "disposition_suggestion": _normalize_dict(payload.get("disposition_suggestion")),
        "cross_index_suggestion": _normalize_dict(payload.get("cross_index_suggestion")),
        "related_card_suggestion": _normalize_dict(payload.get("related_card_suggestion")),
        "split_review_suggestion": _normalize_dict(payload.get("split_review_suggestion")),
        "semantic_review_suggestion": _normalize_dict(payload.get("semantic_review_suggestion")),
        "stub_path": relative_repo_path(repo_root, path),
        "missing_fields": missing_fields,
        "valid": not missing_fields,
    }
    return normalized


def load_proposal_stubs(
    repo_root: Path,
    *,
    run_id: str | None = None,
    run_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    actions_dir = proposal_actions_dir(repo_root, run_id=run_id, run_dir=run_dir)
    if not actions_dir.exists():
        return []

    stubs: list[dict[str, Any]] = []
    for path in sorted(actions_dir.glob("*.json")):
        payload = load_json_object(path)
        stubs.append(normalize_proposal_stub(repo_root, path, payload))

    return sorted(
        stubs,
        key=lambda item: (
            -(item.get("priority_score") or 0.0),
            item.get("action_type") or "",
            item.get("action_key") or "",
            item.get("stub_path") or "",
        ),
    )


def _group_key(stub: dict[str, Any], field: str) -> str:
    value = str(stub.get(field, "") or "").strip()
    return value or "<missing>"


def summarize_proposal_stubs(stubs: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for stub in stubs:
        key = _group_key(stub, field)
        bucket = grouped.setdefault(
            key,
            {
                field: key,
                "stub_count": 0,
                "event_count": 0,
                "ai_decision_required_count": 0,
                "valid_stub_count": 0,
                "invalid_stub_count": 0,
                "max_priority_score": 0.0,
                "action_keys": [],
            },
        )
        bucket["stub_count"] += 1
        bucket["event_count"] += int(stub.get("event_count", 0) or 0)
        bucket["ai_decision_required_count"] += 1 if stub.get("ai_decision_required") else 0
        bucket["valid_stub_count"] += 1 if stub.get("valid") else 0
        bucket["invalid_stub_count"] += 0 if stub.get("valid") else 1
        bucket["max_priority_score"] = max(
            float(bucket["max_priority_score"]),
            float(stub.get("priority_score", 0.0) or 0.0),
        )
        bucket["action_keys"].append(str(stub.get("action_key", "") or ""))

    return sorted(
        grouped.values(),
        key=lambda item: (
            -int(item["stub_count"]),
            -int(item["event_count"]),
            str(item[field]),
        ),
    )


def _target_label(target: dict[str, Any]) -> str:
    if not target:
        return "unknown"
    kind = str(target.get("kind", "") or "").strip()
    for key in ("ref", "route", "entry_id", "entry_path", "label", "id", "path"):
        value = str(target.get(key, "") or "").strip()
        if value:
            return f"{kind}:{value}" if kind else value
    if kind:
        return kind
    return "unknown"


def _count_label(value: Any) -> str:
    label = str(value or "").strip()
    return label or "<missing>"


def _count_summary(values: list[str], key_name: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    items = sorted(Counter(values).items(), key=lambda item: (-item[1], item[0]))
    if limit is not None:
        items = items[:limit]
    return [{key_name: key, "count": count} for key, count in items]


def _eligibility(stub: dict[str, Any]) -> dict[str, Any]:
    value = stub.get("apply_eligibility", {})
    return value if isinstance(value, dict) else {}


def _is_eligible(stub: dict[str, Any]) -> bool:
    return bool(_eligibility(stub).get("eligible", False))


def _supported_mode(stub: dict[str, Any]) -> str:
    return _count_label(_eligibility(stub).get("supported_mode"))


def _eligibility_reason(stub: dict[str, Any]) -> str:
    return _count_label(_eligibility(stub).get("reason"))


def _eligible_action_brief(stub: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_key": str(stub.get("action_key", "") or ""),
        "action_type": str(stub.get("action_type", "") or ""),
        "target": _target_label(stub.get("target", {})),
        "supported_mode": _supported_mode(stub),
        "reason": _eligibility_reason(stub),
        "priority_score": float(stub.get("priority_score", 0.0) or 0.0),
        "event_count": int(stub.get("event_count", 0) or 0),
    }


def _supported_mode_summary(stubs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for stub in stubs:
        mode = _supported_mode(stub)
        bucket = grouped.setdefault(
            mode,
            {
                "supported_mode": mode,
                "action_count": 0,
                "eligible_action_count": 0,
                "non_eligible_action_count": 0,
            },
        )
        bucket["action_count"] += 1
        if _is_eligible(stub):
            bucket["eligible_action_count"] += 1
        else:
            bucket["non_eligible_action_count"] += 1
    return sorted(
        grouped.values(),
        key=lambda item: (
            -int(item["action_count"]),
            str(item["supported_mode"]),
        ),
    )


def build_editorial_summary(stubs: list[dict[str, Any]]) -> dict[str, Any]:
    eligible_stubs = [stub for stub in stubs if _is_eligible(stub)]
    non_eligible_stubs = [stub for stub in stubs if not _is_eligible(stub)]
    return {
        "total_actions": len(stubs),
        "eligible_actions": len(eligible_stubs),
        "non_eligible_actions": len(non_eligible_stubs),
        "action_type_counts": _count_summary(
            [_count_label(stub.get("action_type")) for stub in stubs],
            "action_type",
        ),
        "eligibility_supported_mode_counts": _supported_mode_summary(stubs),
        "eligible_action_briefs": [
            _eligible_action_brief(stub) for stub in eligible_stubs[:EDITORIAL_SUMMARY_LIMIT]
        ],
        "non_eligible_reason_counts": _count_summary(
            [_eligibility_reason(stub) for stub in non_eligible_stubs],
            "reason",
            limit=EDITORIAL_SUMMARY_LIMIT,
        ),
    }


def build_proposal_report(
    repo_root: Path,
    *,
    run_id: str | None = None,
    run_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_run_dir = resolve_run_dir(repo_root, run_id=run_id, run_dir=run_dir)
    stubs = load_proposal_stubs(repo_root, run_id=run_id, run_dir=run_dir)
    valid_stub_count = sum(1 for stub in stubs if stub.get("valid"))
    ai_decision_required_count = sum(1 for stub in stubs if stub.get("ai_decision_required"))
    resolved_run_id = str(run_id or (stubs[0]["run_id"] if stubs else resolved_run_dir.name))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "run_id": resolved_run_id,
        "run_dir": relative_repo_path(repo_root, resolved_run_dir),
        "actions_dir": relative_repo_path(repo_root, resolved_run_dir / ACTIONS_DIRNAME),
        "stub_count": len(stubs),
        "valid_stub_count": valid_stub_count,
        "invalid_stub_count": len(stubs) - valid_stub_count,
        "ai_decision_required_count": ai_decision_required_count,
        "editorial_summary": build_editorial_summary(stubs),
        "action_type_summary": summarize_proposal_stubs(stubs, "action_type"),
        "suggested_artifact_kind_summary": summarize_proposal_stubs(stubs, "suggested_artifact_kind"),
        "stubs": stubs,
    }


def _summary_pairs(items: list[dict[str, Any]], key_name: str, count_name: str = "count") -> str:
    return ", ".join(f"{item[key_name]}={item[count_name]}" for item in items)


def format_proposal_report(report: dict[str, Any]) -> str:
    lines = [
        (
            f"Run {report['run_id']} has {report['stub_count']} proposal stubs "
            f"in {report['actions_dir']}."
        ),
        (
            f"Valid={report['valid_stub_count']}, invalid={report['invalid_stub_count']}, "
            f"ai_decision_required={report['ai_decision_required_count']}."
        ),
    ]

    editorial_summary = report.get("editorial_summary", {})
    if isinstance(editorial_summary, dict):
        lines.append("Editorial summary:")
        lines.append(
            (
                f"- total_actions={editorial_summary.get('total_actions', 0)}, "
                f"eligible_actions={editorial_summary.get('eligible_actions', 0)}, "
                f"non_eligible_actions={editorial_summary.get('non_eligible_actions', 0)}"
            )
        )
        action_type_counts = editorial_summary.get("action_type_counts", [])
        if action_type_counts:
            lines.append(f"- action_type_counts: {_summary_pairs(action_type_counts, 'action_type')}")
        supported_mode_counts = editorial_summary.get("eligibility_supported_mode_counts", [])
        if supported_mode_counts:
            mode_parts = [
                (
                    f"{item['supported_mode']}={item['action_count']} "
                    f"(eligible={item['eligible_action_count']})"
                )
                for item in supported_mode_counts
            ]
            lines.append(f"- eligibility_supported_modes: {', '.join(mode_parts)}")
        eligible_briefs = editorial_summary.get("eligible_action_briefs", [])
        if eligible_briefs:
            lines.append("- eligible_action_briefs:")
            for item in eligible_briefs:
                lines.append(
                    (
                        f"  - {item['action_key']} [{item['action_type']}] "
                        f"target={item['target']} mode={item['supported_mode']} "
                        f"events={item['event_count']} priority={item['priority_score']:.2f}"
                    )
                )
        reason_counts = editorial_summary.get("non_eligible_reason_counts", [])
        if reason_counts:
            lines.append(f"- non_eligible_reasons: {_summary_pairs(reason_counts, 'reason')}")

    lines.append("By action type:")
    for item in report.get("action_type_summary", []):
        lines.append(
            (
                f"- {item['action_type']}: {item['stub_count']} stubs, "
                f"{item['event_count']} events, max_priority={item['max_priority_score']:.2f}"
            )
        )

    lines.append("By suggested artifact:")
    for item in report.get("suggested_artifact_kind_summary", []):
        lines.append(
            (
                f"- {item['suggested_artifact_kind']}: {item['stub_count']} stubs, "
                f"{item['event_count']} events, max_priority={item['max_priority_score']:.2f}"
            )
        )

    if report.get("stubs"):
        lines.append("Stubs:")
    for stub in report.get("stubs", []):
        invalid_note = ""
        if stub.get("missing_fields"):
            invalid_note = f", missing={','.join(stub['missing_fields'])}"
        split_note = ""
        split_review = stub.get("split_review_suggestion", {})
        split_recommendation = str(split_review.get("recommendation", "") or "").strip()
        if split_recommendation:
            split_note = f", split_review={split_recommendation}"
        semantic_note = ""
        semantic_review = stub.get("semantic_review_suggestion", {})
        supported_decisions = normalize_string_list(semantic_review.get("auto_apply_supported_decisions", []))
        if supported_decisions:
            semantic_note = f", semantic_review={','.join(supported_decisions)}"
        related_note = ""
        related_cards = normalize_string_list(stub.get("related_card_suggestion", {}).get("suggested_related_cards", []))
        if related_cards:
            related_note = f", related_cards={','.join(related_cards)}"
        cross_index_note = ""
        cross_index_routes = normalize_string_list(stub.get("cross_index_suggestion", {}).get("suggested_cross_index", []))
        if cross_index_routes:
            cross_index_note = f", cross_index={','.join(cross_index_routes)}"
        lines.append(
            (
                f"- {stub['action_key']} [{stub['action_type']}] "
                f"target={_target_label(stub.get('target', {}))} "
                f"priority={float(stub.get('priority_score', 0.0) or 0.0):.2f} "
                f"events={int(stub.get('event_count', 0) or 0)}"
                f"{split_note}{related_note}{cross_index_note}{invalid_note}"
                f"{semantic_note}"
            )
        )
    return "\n".join(lines)
