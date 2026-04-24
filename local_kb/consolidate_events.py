from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from local_kb.common import csv_to_list, normalize_string_list, parse_route_segments, slugify
from local_kb.maintenance import DECISION_EVENT_TYPES
from local_kb.store import history_events_path, load_entries


SCHEMA_VERSION = 1

CONSOLIDATION_NOTES = [
    "This scaffold only groups likely maintenance actions from stored history.",
    "AI consolidation should inspect these grouped actions before changing cards or taxonomy.",
]

APPLY_MODE_NONE = "none"

APPLY_MODE_NEW_CANDIDATES = "new-candidates"

APPLY_MODE_RELATED_CARDS = "related-cards"

APPLY_MODE_CROSS_INDEX = "cross-index"

APPLY_MODE_I18N_ZH_CN = "i18n-zh-CN"

APPLY_MODE_SEMANTIC_REVIEW = "semantic-review"

AUTO_CANDIDATE_SCOPE = "private"

RELATED_CARD_MAX_COUNT = 3

RELATED_CARD_MIN_SUPPORT_COUNT = 2

RELATED_CARD_MIN_USAGE_RATIO = 0.34

CROSS_INDEX_MAX_COUNT = 5

CROSS_INDEX_MIN_SUPPORT_COUNT = 2

CROSS_INDEX_MIN_USAGE_RATIO = 0.34

CROSS_INDEX_MIN_REMOVAL_USAGE_COUNT = 4

TIMELINE_MAX_EPISODES = 3

TIMELINE_MAX_STEPS_PER_EPISODE = 4

TIMELINE_MAX_SEQUENCE_EXAMPLES = 3

ACTION_BASE_SCORES = {
    "review-candidate": 3,
    "review-code-change": 3,
    "review-confidence": 4,
    "review-cross-index": 3,
    "review-entry-update": 4,
    "review-related-cards": 3,
    "review-i18n": 2,
    "review-route-i18n": 2,
    "semantic-review": 4,
    "review-observation-evidence": 2,
    "consider-new-candidate": 3,
    "review-taxonomy": 3,
    "investigate-gap": 2,
}

HIT_QUALITY_SCORES = {
    "weak": 1,
    "miss": 2,
    "misleading": 3,
}


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sanitize_run_id(value: str | None) -> str:
    if not value:
        return utc_now_compact()
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip())
    return cleaned.strip("-") or utc_now_compact()


def normalize_apply_mode(value: str | None) -> str:
    mode = str(value or APPLY_MODE_NONE).strip().lower() or APPLY_MODE_NONE
    if mode in {
        APPLY_MODE_NONE,
        APPLY_MODE_NEW_CANDIDATES,
        APPLY_MODE_RELATED_CARDS,
        APPLY_MODE_CROSS_INDEX,
        APPLY_MODE_I18N_ZH_CN.lower(),
        APPLY_MODE_SEMANTIC_REVIEW,
    }:
        return APPLY_MODE_I18N_ZH_CN if mode == APPLY_MODE_I18N_ZH_CN.lower() else mode
    raise ValueError(f"Unsupported consolidation apply mode: {value}")


def normalize_entry_ids(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = csv_to_list(value)
    else:
        raw_items = normalize_string_list(value)
    return sorted({str(item).strip() for item in raw_items if str(item).strip()})


def normalize_text_list(value: Any) -> list[str]:
    return sorted({str(item).strip() for item in normalize_string_list(value) if str(item).strip()})


def normalize_contrastive_evidence(value: Any) -> dict[str, str]:
    contrastive = value if isinstance(value, dict) else {}
    return {
        "previous_action": str(contrastive.get("previous_action", "") or "").strip(),
        "previous_result": str(contrastive.get("previous_result", "") or "").strip(),
        "revised_action": str(contrastive.get("revised_action", "") or "").strip(),
        "revised_result": str(contrastive.get("revised_result", "") or "").strip(),
    }


def normalize_event(raw: dict[str, Any], source_line: int) -> dict[str, Any]:
    event = dict(raw)
    source = event.get("source", {}) if isinstance(event.get("source"), dict) else {}
    target = event.get("target", {}) if isinstance(event.get("target"), dict) else {}
    context = event.get("context", {}) if isinstance(event.get("context"), dict) else {}

    route_hint = parse_route_segments(
        target.get("route_hint")
        or target.get("domain_path")
        or event.get("route_hint")
        or event.get("domain_path")
        or []
    )
    entry_ids = normalize_entry_ids(target.get("entry_ids") or event.get("entry_ids"))
    entry_id = str(target.get("entry_id") or event.get("entry_id", "") or "").strip()
    if entry_id:
        entry_ids = sorted(set(entry_ids + [entry_id]))
    event_id = str(event.get("event_id", "") or f"history-line-{source_line:06d}")

    event["event_id"] = event_id
    event["event_type"] = str(event.get("event_type", "") or "").strip().lower()
    event["created_at"] = str(event.get("created_at", "") or "").strip()
    event["source"] = source
    event["target"] = target
    event["context"] = context
    event["entry_id"] = entry_id
    event["entry_ids"] = entry_ids
    event["route_hint"] = route_hint
    event["task_summary"] = str(target.get("task_summary") or event.get("task_summary", "") or "").strip()
    event["suggested_action"] = str(
        context.get("suggested_action") or event.get("suggested_action", "none") or "none"
    ).strip().lower()
    event["hit_quality"] = str(
        context.get("hit_quality") or event.get("hit_quality", "none") or "none"
    ).strip().lower()
    event["exposed_gap"] = bool(context.get("exposed_gap", event.get("exposed_gap", False)))
    predictive_observation = context.get("predictive_observation", {})
    if not isinstance(predictive_observation, dict):
        predictive_observation = {}
    contrastive_evidence = normalize_contrastive_evidence(predictive_observation.get("contrastive_evidence", {}))
    event["predictive_observation"] = {
        "scenario": str(predictive_observation.get("scenario", "") or "").strip(),
        "action_taken": str(predictive_observation.get("action_taken", "") or "").strip(),
        "observed_result": str(predictive_observation.get("observed_result", "") or "").strip(),
        "contrastive_evidence": contrastive_evidence,
        "operational_use": str(predictive_observation.get("operational_use", "") or "").strip(),
        "reuse_judgment": str(predictive_observation.get("reuse_judgment", "") or "").strip(),
    }
    event["source_agent"] = str(source.get("agent", "") or "").strip()
    event["thread_ref"] = str(source.get("thread_ref", "") or "").strip()
    event["project_ref"] = str(source.get("project_ref", "") or "").strip()
    event["workspace_root"] = str(source.get("workspace_root", "") or "").strip()
    event["resolved_action_key"] = str(
        context.get("resolved_action_key") or target.get("action_key") or event.get("resolved_action_key", "") or ""
    ).strip()
    event["resolved_event_ids"] = normalize_text_list(
        context.get("resolved_event_ids") or target.get("event_ids") or event.get("resolved_event_ids") or []
    )
    event["source_line"] = source_line
    return event


def has_predictive_evidence(event: dict[str, Any]) -> bool:
    predictive = event.get("predictive_observation", {})
    if not isinstance(predictive, dict):
        return False
    return all(
        str(predictive.get(field, "") or "").strip()
        for field in ("scenario", "action_taken", "observed_result")
    )


def has_contrastive_evidence(event: dict[str, Any]) -> bool:
    predictive = event.get("predictive_observation", {})
    if not isinstance(predictive, dict):
        return False
    contrastive = predictive.get("contrastive_evidence", {})
    if not isinstance(contrastive, dict):
        return False
    previous_pair_complete = all(
        str(contrastive.get(field, "") or "").strip()
        for field in ("previous_action", "previous_result")
    )
    revised_pair_complete = all(
        str(contrastive.get(field, "") or "").strip()
        for field in ("revised_action", "revised_result")
    )
    return previous_pair_complete or revised_pair_complete


def load_history_events(repo_root: Path, max_events: int | None = None) -> list[dict[str, Any]]:
    path = history_events_path(repo_root)
    if not path.exists():
        return []

    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for source_line, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:  # pragma: no cover - malformed user data
                raise ValueError(f"Invalid JSON in {path} at line {source_line}") from exc
            if not isinstance(payload, dict):  # pragma: no cover - malformed user data
                raise ValueError(f"History event at line {source_line} is not an object")
            events.append(normalize_event(payload, source_line))

    if max_events is not None and max_events > 0:
        events = events[-max_events:]

    return sorted(
        events,
        key=lambda item: (
            item.get("created_at") or "",
            item.get("source_line") or 0,
            item.get("event_id") or "",
        ),
    )


def route_label(route_hint: list[str]) -> str:
    return "/".join(route_hint)


def relative_repo_path(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def route_or_task_target(event: dict[str, Any]) -> tuple[str, str]:
    route_hint = event.get("route_hint", [])
    if route_hint:
        return "route", route_label(route_hint)
    task_summary = str(event.get("task_summary", "") or "").strip()
    if task_summary:
        return "task", slugify(task_summary)[:48]
    return "event", str(event["event_id"])


def build_action_seeds(event: dict[str, Any]) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    event_type = event.get("event_type", "")
    route_hint = event.get("route_hint", [])
    route_ref = route_label(route_hint)

    if event_type == "candidate-created":
        entry_id = event.get("entry_id") or event["event_id"]
        seeds.append(
            {
                "action_type": "review-candidate",
                "target_kind": "entry",
                "target_ref": str(entry_id),
                "route_ref": route_ref,
                "reason": "candidate-created",
            }
        )
        return seeds

    suggested_action = event.get("suggested_action", "none")
    hit_quality = str(event.get("hit_quality", "none") or "none")
    predictive_evidence_complete = has_predictive_evidence(event)
    if suggested_action == "update-card":
        entry_ids = event.get("entry_ids", [])
        if entry_ids:
            for entry_id in entry_ids:
                seeds.append(
                    {
                        "action_type": "review-entry-update",
                        "target_kind": "entry",
                        "target_ref": str(entry_id),
                        "route_ref": route_ref,
                        "reason": "suggested-action:update-card",
                    }
                )
                if hit_quality in HIT_QUALITY_SCORES or event.get("exposed_gap"):
                    seeds.append(
                        {
                            "action_type": "review-confidence",
                            "target_kind": "entry",
                            "target_ref": str(entry_id),
                            "route_ref": route_ref,
                            "reason": f"confidence-signal:{hit_quality or 'gap'}",
                        }
                    )
        else:
            target_kind, target_ref = route_or_task_target(event)
            seeds.append(
                {
                    "action_type": "review-entry-update",
                    "target_kind": target_kind,
                    "target_ref": target_ref,
                    "route_ref": route_ref,
                    "reason": "suggested-action:update-card",
                }
            )
        if not predictive_evidence_complete:
            target_kind, target_ref = route_or_task_target(event)
            seeds.append(
                {
                    "action_type": "review-observation-evidence",
                    "target_kind": target_kind,
                    "target_ref": target_ref,
                    "route_ref": route_ref,
                    "reason": "predictive-evidence:missing",
                }
            )
        return seeds

    if suggested_action == "new-candidate":
        target_kind, target_ref = route_or_task_target(event)
        seeds.append(
            {
                "action_type": "consider-new-candidate",
                "target_kind": target_kind,
                "target_ref": target_ref,
                "route_ref": route_ref,
                "reason": "suggested-action:new-candidate",
            }
        )
        if not predictive_evidence_complete:
            seeds.append(
                {
                    "action_type": "review-observation-evidence",
                    "target_kind": target_kind,
                    "target_ref": target_ref,
                    "route_ref": route_ref,
                    "reason": "predictive-evidence:missing",
                }
            )
        return seeds

    if suggested_action == "taxonomy-change":
        target_kind, target_ref = route_or_task_target(event)
        seeds.append(
            {
                "action_type": "review-taxonomy",
                "target_kind": target_kind,
                "target_ref": target_ref,
                "route_ref": route_ref,
                "reason": "suggested-action:taxonomy-change",
            }
        )
        if not predictive_evidence_complete:
            seeds.append(
                {
                    "action_type": "review-observation-evidence",
                    "target_kind": target_kind,
                    "target_ref": target_ref,
                    "route_ref": route_ref,
                    "reason": "predictive-evidence:missing",
                }
            )
        return seeds

    if suggested_action == "code-change":
        target_kind, target_ref = route_or_task_target(event)
        seeds.append(
            {
                "action_type": "review-code-change",
                "target_kind": target_kind,
                "target_ref": target_ref,
                "route_ref": route_ref,
                "reason": "suggested-action:code-change",
            }
        )
        if not predictive_evidence_complete:
            seeds.append(
                {
                    "action_type": "review-observation-evidence",
                    "target_kind": target_kind,
                    "target_ref": target_ref,
                    "route_ref": route_ref,
                    "reason": "predictive-evidence:missing",
                }
            )
        return seeds

    if event.get("entry_ids") and (hit_quality in HIT_QUALITY_SCORES or event.get("exposed_gap")):
        for entry_id in event.get("entry_ids", []):
            seeds.append(
                {
                    "action_type": "review-confidence",
                    "target_kind": "entry",
                    "target_ref": str(entry_id),
                    "route_ref": route_ref,
                    "reason": f"confidence-signal:{hit_quality or 'gap'}",
                }
            )

    if event.get("exposed_gap") or event.get("hit_quality") in HIT_QUALITY_SCORES:
        target_kind, target_ref = route_or_task_target(event)
        seeds.append(
            {
                "action_type": "investigate-gap",
                "target_kind": target_kind,
                "target_ref": target_ref,
                "route_ref": route_ref,
                "reason": f"hit-quality:{event.get('hit_quality', 'none')}",
            }
        )
    return seeds


def sort_counter(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def score_action(action_type: str, event_count: int, hit_quality: Counter[str], exposed_gap_count: int) -> int:
    score = ACTION_BASE_SCORES.get(action_type, 1)
    score += event_count
    score += sum(HIT_QUALITY_SCORES.get(key, 0) * count for key, count in hit_quality.items())
    if exposed_gap_count:
        score += 2
    return score


def group_candidate_actions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    for event in events:
        for seed in build_action_seeds(event):
            action_key = f"{seed['action_type']}::{seed['target_kind']}::{seed['target_ref']}"
            group = grouped.setdefault(
                action_key,
                {
                    "action_key": action_key,
                    "action_type": seed["action_type"],
                    "target": {
                        "kind": seed["target_kind"],
                        "ref": seed["target_ref"],
                    },
                    "_event_ids": set(),
                    "_entry_ids": set(),
                    "_routes": set(),
                    "_reasons": set(),
                    "_event_types": Counter(),
                    "_suggested_actions": Counter(),
                    "_hit_quality": Counter(),
                    "_exposed_gap_count": 0,
                    "_first_event_at": "",
                    "_latest_event_at": "",
                },
            )

            event_id = str(event["event_id"])
            group["_event_ids"].add(event_id)
            group["_entry_ids"].update(event.get("entry_ids", []))
            if seed.get("route_ref"):
                group["_routes"].add(seed["route_ref"])
            elif event.get("route_hint"):
                group["_routes"].add(route_label(event["route_hint"]))
            group["_reasons"].add(seed["reason"])

            event_type = str(event.get("event_type", "") or "")
            if event_type:
                group["_event_types"][event_type] += 1
            suggested_action = str(event.get("suggested_action", "none") or "none")
            if suggested_action != "none":
                group["_suggested_actions"][suggested_action] += 1
            hit_quality = str(event.get("hit_quality", "none") or "none")
            if hit_quality != "none":
                group["_hit_quality"][hit_quality] += 1
            if event.get("exposed_gap"):
                group["_exposed_gap_count"] += 1

            created_at = str(event.get("created_at", "") or "")
            if created_at and (not group["_first_event_at"] or created_at < group["_first_event_at"]):
                group["_first_event_at"] = created_at
            if created_at and (not group["_latest_event_at"] or created_at > group["_latest_event_at"]):
                group["_latest_event_at"] = created_at

    actions: list[dict[str, Any]] = []
    for action_key, group in grouped.items():
        event_ids = sorted(group["_event_ids"])
        entry_ids = sorted(group["_entry_ids"])
        routes = sorted(route for route in group["_routes"] if route)
        hit_quality = group["_hit_quality"]
        action = {
            "action_key": action_key,
            "action_type": group["action_type"],
            "target": group["target"],
            "priority_score": score_action(
                action_type=group["action_type"],
                event_count=len(event_ids),
                hit_quality=hit_quality,
                exposed_gap_count=group["_exposed_gap_count"],
            ),
            "event_count": len(event_ids),
            "event_ids": event_ids,
            "entry_ids": entry_ids,
            "routes": routes,
            "signals": {
                "event_types": sort_counter(group["_event_types"]),
                "suggested_actions": sort_counter(group["_suggested_actions"]),
                "hit_quality": sort_counter(hit_quality),
                "exposed_gap_count": group["_exposed_gap_count"],
            },
            "reasons": sorted(group["_reasons"]),
            "first_event_at": group["_first_event_at"],
            "latest_event_at": group["_latest_event_at"],
            "ai_decision_required": True,
        }
        actions.append(action)

    return sorted(
        actions,
        key=lambda item: (
            -int(item["priority_score"]),
            item["action_type"],
            str(item["target"]["kind"]),
            str(item["target"]["ref"]),
        ),
    )


def events_by_id(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(event["event_id"]): event for event in events}


def collect_resolution_state(events: list[dict[str, Any]]) -> tuple[dict[str, set[str]], set[str]]:
    resolved_event_ids_by_action: dict[str, set[str]] = {}
    permanently_resolved_actions: set[str] = set()
    for event in events:
        event_type = str(event.get("event_type", "") or "").strip().lower()
        if event_type not in DECISION_EVENT_TYPES:
            continue
        action_key = str(event.get("resolved_action_key", "") or "").strip()
        if not action_key:
            continue
        resolved_event_ids = {
            str(event_id).strip()
            for event_id in event.get("resolved_event_ids", [])
            if str(event_id).strip()
        }
        if resolved_event_ids:
            resolved_event_ids_by_action.setdefault(action_key, set()).update(resolved_event_ids)
            continue
        permanently_resolved_actions.add(action_key)
    return resolved_event_ids_by_action, permanently_resolved_actions


def suppress_resolved_actions(
    actions: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolved_event_ids_by_action, permanently_resolved_actions = collect_resolution_state(events)
    kept_actions: list[dict[str, Any]] = []
    suppressed_actions: list[dict[str, Any]] = []

    for action in actions:
        action_key = str(action.get("action_key", "") or "")
        event_ids = {str(event_id).strip() for event_id in action.get("event_ids", []) if str(event_id).strip()}
        suppressed_reason = ""
        if action_key in permanently_resolved_actions:
            suppressed_reason = "resolved-action-without-event-ids"
        elif action_key in resolved_event_ids_by_action and event_ids and event_ids.issubset(
            resolved_event_ids_by_action[action_key]
        ):
            suppressed_reason = "all-supporting-event-ids-already-resolved"

        if suppressed_reason:
            suppressed_actions.append(
                {
                    "action_key": action_key,
                    "action_type": str(action.get("action_type", "") or ""),
                    "target": dict(action.get("target", {})),
                    "event_count": int(action.get("event_count", 0) or 0),
                    "event_ids": sorted(event_ids),
                    "reason": suppressed_reason,
                }
            )
            continue

        kept_actions.append(action)

    return kept_actions, suppressed_actions


def supporting_events_for_action(
    action: dict[str, Any],
    indexed_events: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    supporting: list[dict[str, Any]] = []
    for event_id in action.get("event_ids", []):
        event = indexed_events.get(str(event_id))
        if event is not None:
            supporting.append(event)
    return supporting


def collect_task_summaries(events: list[dict[str, Any]]) -> list[str]:
    summaries: list[str] = []
    seen: set[str] = set()
    for event in events:
        summary = str(event.get("task_summary", "") or "").strip()
        if not summary or summary in seen:
            continue
        seen.add(summary)
        summaries.append(summary)
    return summaries


def summarize_provenance(events: list[dict[str, Any]]) -> dict[str, list[str]]:
    def unique(values: list[str]) -> list[str]:
        return sorted({value for value in values if value})

    return {
        "agents": unique([str(event.get("source_agent", "") or "") for event in events]),
        "thread_refs": unique([str(event.get("thread_ref", "") or "") for event in events]),
        "project_refs": unique([str(event.get("project_ref", "") or "") for event in events]),
        "workspace_roots": unique([str(event.get("workspace_root", "") or "") for event in events]),
    }


def _timeline_scope_identity(event: dict[str, Any]) -> tuple[str, str, str]:
    project_ref = str(event.get("project_ref", "") or "").strip()
    workspace_root = str(event.get("workspace_root", "") or "").strip()
    thread_ref = str(event.get("thread_ref", "") or "").strip()
    return project_ref, workspace_root, thread_ref


def _timeline_scope_key(event: dict[str, Any]) -> str:
    project_ref, workspace_root, thread_ref = _timeline_scope_identity(event)
    if project_ref or workspace_root:
        return f"project::{project_ref}::{workspace_root}"
    if thread_ref:
        return f"thread::{thread_ref}"
    source_agent = str(event.get("source_agent", "") or "").strip()
    if source_agent:
        return f"agent::{source_agent}"
    return "unscoped"


def _timeline_scope_label(project_ref: str, workspace_root: str, thread_refs: list[str]) -> str:
    if project_ref:
        return f"project {project_ref}"
    if workspace_root:
        return f"workspace {workspace_root}"
    if thread_refs:
        return f"thread {thread_refs[0]}"
    return "unscoped observation stream"


def _timeline_step(event: dict[str, Any]) -> dict[str, Any]:
    predictive = event.get("predictive_observation", {})
    if not isinstance(predictive, dict):
        predictive = {}
    contrastive = normalize_contrastive_evidence(predictive.get("contrastive_evidence", {}))
    step = {
        "created_at": str(event.get("created_at", "") or "").strip(),
        "event_id": str(event.get("event_id", "") or "").strip(),
        "task_summary": str(event.get("task_summary", "") or "").strip(),
        "route": route_label(event.get("route_hint", [])),
        "scenario": str(predictive.get("scenario", "") or "").strip(),
        "action_taken": str(predictive.get("action_taken", "") or "").strip(),
        "observed_result": str(predictive.get("observed_result", "") or "").strip(),
        "operational_use": str(predictive.get("operational_use", "") or "").strip(),
        "reuse_judgment": str(predictive.get("reuse_judgment", "") or "").strip(),
        "suggested_action": str(event.get("suggested_action", "none") or "none").strip(),
        "hit_quality": str(event.get("hit_quality", "none") or "none").strip(),
    }
    if any(contrastive.values()):
        step["contrastive_evidence"] = contrastive
    return step


def _build_timeline_sequence_example(episode: dict[str, Any]) -> str:
    label = str(episode.get("scope_label", "") or "this episode").strip()
    steps = list(episode.get("steps_full", []))
    for step in steps:
        contrastive = step.get("contrastive_evidence", {})
        if not isinstance(contrastive, dict):
            continue
        previous_action = str(contrastive.get("previous_action", "") or "").strip()
        previous_result = str(contrastive.get("previous_result", "") or "").strip()
        revised_action = str(contrastive.get("revised_action", "") or "").strip()
        revised_result = str(contrastive.get("revised_result", "") or "").strip()
        if previous_action and previous_result and revised_action and revised_result:
            return (
                f"In {label}, the earlier path '{previous_action}' led to '{previous_result}', "
                f"then the revised path '{revised_action}' led to '{revised_result}'."
            )

    predictive_steps = [
        step
        for step in steps
        if str(step.get("action_taken", "") or "").strip() or str(step.get("observed_result", "") or "").strip()
    ]
    if len(predictive_steps) < 2:
        return ""

    first_step = predictive_steps[0]
    last_step = predictive_steps[-1]
    first_action = str(first_step.get("action_taken", "") or first_step.get("task_summary", "") or "").strip()
    first_result = str(first_step.get("observed_result", "") or "").strip()
    last_action = str(last_step.get("action_taken", "") or last_step.get("task_summary", "") or "").strip()
    last_result = str(last_step.get("observed_result", "") or "").strip()
    if not first_action or not last_action:
        return ""
    if first_action == last_action and first_result == last_result:
        return ""
    return (
        f"In {label}, the work moved from '{first_action}'"
        f"{f' -> {first_result}' if first_result else ''} to '{last_action}'"
        f"{f' -> {last_result}' if last_result else ''}."
    )


def summarize_observation_timeline(events: list[dict[str, Any]]) -> dict[str, Any]:
    ordered_events = sorted(
        events,
        key=lambda item: (
            item.get("created_at") or "",
            item.get("source_line") or 0,
            item.get("event_id") or "",
        ),
    )
    grouped: dict[str, dict[str, Any]] = {}
    for event in ordered_events:
        scope_key = _timeline_scope_key(event)
        project_ref, workspace_root, thread_ref = _timeline_scope_identity(event)
        group = grouped.setdefault(
            scope_key,
            {
                "scope_key": scope_key,
                "project_ref": project_ref,
                "workspace_root": workspace_root,
                "_thread_refs": [],
                "first_event_at": "",
                "latest_event_at": "",
                "steps_full": [],
            },
        )
        if thread_ref and thread_ref not in group["_thread_refs"]:
            group["_thread_refs"].append(thread_ref)
        created_at = str(event.get("created_at", "") or "").strip()
        if created_at and (not group["first_event_at"] or created_at < group["first_event_at"]):
            group["first_event_at"] = created_at
        if created_at and (not group["latest_event_at"] or created_at > group["latest_event_at"]):
            group["latest_event_at"] = created_at
        group["steps_full"].append(_timeline_step(event))

    episodes: list[dict[str, Any]] = []
    for group in grouped.values():
        steps_full = list(group.get("steps_full", []))
        thread_refs = list(group.get("_thread_refs", []))
        episode = {
            "scope_key": str(group.get("scope_key", "") or "").strip(),
            "scope_label": _timeline_scope_label(
                str(group.get("project_ref", "") or "").strip(),
                str(group.get("workspace_root", "") or "").strip(),
                thread_refs,
            ),
            "project_ref": str(group.get("project_ref", "") or "").strip(),
            "workspace_root": str(group.get("workspace_root", "") or "").strip(),
            "thread_refs": thread_refs,
            "event_count": len(steps_full),
            "first_event_at": str(group.get("first_event_at", "") or "").strip(),
            "latest_event_at": str(group.get("latest_event_at", "") or "").strip(),
            "steps": steps_full[:TIMELINE_MAX_STEPS_PER_EPISODE],
            "step_count": len(steps_full),
            "truncated": len(steps_full) > TIMELINE_MAX_STEPS_PER_EPISODE,
            "steps_full": steps_full,
        }
        episodes.append(episode)

    sequence_examples: list[str] = []
    for episode in episodes:
        example = _build_timeline_sequence_example(episode)
        if example:
            sequence_examples.append(example)
        if len(sequence_examples) >= TIMELINE_MAX_SEQUENCE_EXAMPLES:
            break

    visible_episodes = episodes[:TIMELINE_MAX_EPISODES]
    for episode in visible_episodes:
        episode.pop("steps_full", None)

    first_event_at = episodes[0]["first_event_at"] if episodes else ""
    latest_event_at = episodes[-1]["latest_event_at"] if episodes else ""
    return {
        "episode_count": len(episodes),
        "sequence_example_count": len(sequence_examples),
        "sequence_examples": sequence_examples,
        "first_event_at": first_event_at,
        "latest_event_at": latest_event_at,
        "episodes": visible_episodes,
    }


def summarize_predictive_evidence(events: list[dict[str, Any]]) -> dict[str, Any]:
    examples: list[dict[str, Any]] = []
    complete_event_count = 0
    incomplete_event_count = 0
    contrastive_event_count = 0
    for event in events:
        predictive = event.get("predictive_observation", {})
        if not isinstance(predictive, dict):
            predictive = {}
        contrastive = normalize_contrastive_evidence(predictive.get("contrastive_evidence", {}))
        complete = has_predictive_evidence(event)
        if complete:
            complete_event_count += 1
        else:
            incomplete_event_count += 1
        if has_contrastive_evidence(event):
            contrastive_event_count += 1
        if len(examples) >= 3:
            continue
        example = {
            "event_id": str(event.get("event_id", "") or ""),
            "task_summary": str(event.get("task_summary", "") or ""),
            "scenario": str(predictive.get("scenario", "") or ""),
            "action_taken": str(predictive.get("action_taken", "") or ""),
            "observed_result": str(predictive.get("observed_result", "") or ""),
            "operational_use": str(predictive.get("operational_use", "") or ""),
            "reuse_judgment": str(predictive.get("reuse_judgment", "") or ""),
        }
        if any(contrastive.values()):
            example["contrastive_evidence"] = contrastive
        if any(value for key, value in example.items() if key != "event_id"):
            examples.append(example)
    return {
        "complete_event_count": complete_event_count,
        "incomplete_event_count": incomplete_event_count,
        "contrastive_event_count": contrastive_event_count,
        "contrastive_example_count": sum(1 for example in examples if example.get("contrastive_evidence")),
        "example_count": len(examples),
        "examples": examples,
    }


def build_entry_lookup(repo_root: Path) -> dict[str, dict[str, Any]]:
    entries = load_entries(repo_root)
    lookup: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entry_id = str(entry.data.get("id", "") or "").strip()
        if entry_id:
            lookup[entry_id] = entry.data
    return lookup


def build_entry_path_lookup(repo_root: Path) -> dict[str, Path]:
    entries = load_entries(repo_root)
    lookup: dict[str, Path] = {}
    for entry in entries:
        entry_id = str(entry.data.get("id", "") or "").strip()
        if entry_id:
            lookup[entry_id] = entry.path
    return lookup
