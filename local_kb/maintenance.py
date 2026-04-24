from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from local_kb.common import csv_to_list, normalize_string_list, parse_route_segments
from local_kb.history import build_history_event, record_history_event


DECISION_EVENT_TYPES = {
    "observation-ignored",
    "candidate-rejected",
    "confidence-reviewed",
    "semantic-reviewed",
    "split-reviewed",
}


def _normalize_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        value = text
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _normalize_resolved_event_ids(value: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(value, str):
        return normalize_string_list(csv_to_list(value))
    return normalize_string_list(value)


def build_maintenance_decision(
    *,
    decision_type: str,
    action_key: str,
    resolved_event_ids: str | list[str] | tuple[str, ...],
    reason: str,
    source_kind: str = "maintenance",
    agent_name: str = "kb-maintenance",
    thread_ref: str = "",
    project_ref: str = "",
    workspace_root: str = "",
    entry_id: str = "",
    route_ref: str = "",
    decision_summary: str = "",
    review_state: str = "",
    previous_confidence: float | str | None = None,
    new_confidence: float | str | None = None,
    extra_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_type = str(decision_type or "").strip().lower()
    if normalized_type not in DECISION_EVENT_TYPES:
        raise ValueError(f"Unsupported maintenance decision type: {decision_type}")

    normalized_action_key = str(action_key or "").strip()
    if not normalized_action_key:
        raise ValueError("Maintenance decisions require a non-empty action_key")

    event_ids = _normalize_resolved_event_ids(resolved_event_ids)
    if normalized_type == "split-reviewed" and not event_ids:
        raise ValueError("split-reviewed decisions require non-empty resolved_event_ids")
    previous_value = _normalize_optional_float(previous_confidence)
    new_value = _normalize_optional_float(new_confidence)

    target: dict[str, Any] = {
        "kind": "maintenance-action",
        "action_key": normalized_action_key,
    }
    if entry_id:
        target["entry_id"] = str(entry_id).strip()
    route_segments = parse_route_segments(route_ref)
    if route_segments:
        target["route_hint"] = route_segments

    context: dict[str, Any] = {
        "resolved_action_key": normalized_action_key,
        "resolved_event_ids": event_ids,
    }
    if decision_summary:
        context["decision_summary"] = str(decision_summary).strip()
    if review_state:
        context["review_state"] = str(review_state).strip()
    if previous_value is not None:
        context["previous_confidence"] = previous_value
    if new_value is not None:
        context["new_confidence"] = new_value
    if extra_context:
        context.update(dict(extra_context))

    return build_history_event(
        normalized_type,
        source={
            "kind": source_kind,
            "agent": agent_name,
            "thread_ref": thread_ref,
            "project_ref": project_ref,
            "workspace_root": workspace_root,
        },
        target=target,
        rationale=reason,
        context=context,
    )


def record_maintenance_decision(repo_root: Path, event: dict[str, Any]) -> Path:
    return record_history_event(repo_root, event)
