from __future__ import annotations

from pathlib import Path
from typing import Any

from local_kb.common import normalize_string_list, parse_route_segments
from local_kb.consolidate_events import ACTION_BASE_SCORES, APPLY_MODE_I18N_ZH_CN
from local_kb.i18n import ZH_CN, has_route_segment_label, missing_i18n_fields, normalize_language
from local_kb.store import load_entries, load_yaml_file


def _entry_route_refs(data: dict[str, Any]) -> list[str]:
    routes: list[str] = []
    domain_segments = parse_route_segments(data.get("domain_path", []))
    if domain_segments:
        routes.append("/".join(domain_segments))
    for raw_route in normalize_string_list(data.get("cross_index", [])):
        cross_segments = parse_route_segments(raw_route)
        if cross_segments:
            routes.append("/".join(cross_segments))
    return list(dict.fromkeys(routes))


def collect_route_segment_label_gaps(repo_root: Path, language: str = ZH_CN) -> list[dict[str, Any]]:
    normalized_language = normalize_language(language)
    if normalized_language != ZH_CN:
        return []

    gaps: dict[str, dict[str, set[str]]] = {}
    for entry in load_entries(repo_root):
        data = entry.data
        entry_id = str(data.get("id") or entry.path.stem).strip()
        route_refs = _entry_route_refs(data)
        for route_ref in route_refs:
            for segment in parse_route_segments(route_ref):
                if has_route_segment_label(segment, normalized_language, repo_root=repo_root):
                    continue
                gap = gaps.setdefault(segment, {"entry_ids": set(), "example_routes": set()})
                if entry_id:
                    gap["entry_ids"].add(entry_id)
                gap["example_routes"].add(route_ref)

    return [
        {
            "segment": segment,
            "entry_ids": sorted(values["entry_ids"]),
            "example_routes": sorted(values["example_routes"]),
        }
        for segment, values in sorted(gaps.items())
    ]


def build_route_segment_i18n_actions(repo_root: Path, language: str = ZH_CN) -> list[dict[str, Any]]:
    normalized_language = normalize_language(language)
    missing_segments = collect_route_segment_label_gaps(repo_root, normalized_language)
    if not missing_segments:
        return []

    entry_ids = sorted(
        {
            entry_id
            for item in missing_segments
            for entry_id in item.get("entry_ids", [])
            if str(entry_id).strip()
        }
    )
    routes = sorted(
        {
            route
            for item in missing_segments
            for route in item.get("example_routes", [])
            if str(route).strip()
        }
    )
    return [
        {
            "action_key": f"review-route-i18n::route-segments::{normalized_language}",
            "action_type": "review-route-i18n",
            "target": {"kind": "route-segment-labels", "ref": normalized_language},
            "priority_score": ACTION_BASE_SCORES["review-route-i18n"] + len(missing_segments),
            "event_count": 0,
            "event_ids": [],
            "entry_ids": entry_ids,
            "routes": routes,
            "signals": {
                "missing_route_segment_labels": missing_segments,
                "language": normalized_language,
            },
            "reasons": ["route-display-label-missing"],
            "first_event_at": "",
            "latest_event_at": "",
            "ai_decision_required": True,
            "i18n_suggestion": {
                "language": normalized_language,
                "missing_route_segment_labels": missing_segments,
                "required_artifact": "AI-authored i18n translation plan YAML with route_segment_labels",
                "apply_supported_mode": APPLY_MODE_I18N_ZH_CN,
                "canonical_route_policy": (
                    "Do not rename domain_path, cross_index, taxonomy routes, or search paths; "
                    "only add missing display labels to the AI-maintained display layer."
                ),
            },
        }
    ]


def build_i18n_actions(repo_root: Path, language: str = ZH_CN) -> list[dict[str, Any]]:
    normalized_language = normalize_language(language)
    if normalized_language != ZH_CN:
        return []

    actions: list[dict[str, Any]] = []
    for entry in load_entries(repo_root):
        data = entry.data
        entry_id = str(data.get("id") or entry.path.stem).strip()
        if not entry_id:
            continue
        missing_fields = missing_i18n_fields(data, normalized_language)
        if not missing_fields:
            continue
        route = "/".join(parse_route_segments(data.get("domain_path", [])))
        actions.append(
            {
                "action_key": f"review-i18n::entry::{entry_id}::{normalized_language}",
                "action_type": "review-i18n",
                "target": {"kind": "entry", "ref": entry_id},
                "priority_score": ACTION_BASE_SCORES["review-i18n"] + len(missing_fields),
                "event_count": 0,
                "event_ids": [],
                "entry_ids": [entry_id],
                "routes": [route] if route else [],
                "signals": {
                    "missing_i18n_fields": missing_fields,
                    "language": normalized_language,
                },
                "reasons": ["display-language-missing"],
                "first_event_at": "",
                "latest_event_at": "",
                "ai_decision_required": True,
                "i18n_suggestion": {
                    "language": normalized_language,
                    "missing_fields": missing_fields,
                    "apply_supported_mode": APPLY_MODE_I18N_ZH_CN,
                    "required_artifact": "AI-authored i18n translation plan YAML",
                },
            }
        )
    actions.extend(build_route_segment_i18n_actions(repo_root, normalized_language))

    return sorted(
        actions,
        key=lambda item: (
            -int(item.get("priority_score", 0) or 0),
            str(item.get("target", {}).get("ref", "") or ""),
        ),
    )


def load_i18n_plan(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"language": ZH_CN, "translations": {}, "route_segment_labels": {}}
    payload = load_yaml_file(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid i18n plan: {path}")
    language = normalize_language(payload.get("language"))
    translations = payload.get("translations", {})
    if not isinstance(translations, dict):
        raise ValueError(f"i18n plan translations must be a mapping: {path}")
    route_segment_labels = payload.get("route_segment_labels", {})
    if not isinstance(route_segment_labels, dict):
        raise ValueError(f"i18n plan route_segment_labels must be a mapping: {path}")
    return {
        "language": language,
        "translations": translations,
        "route_segment_labels": route_segment_labels,
    }


def translation_for_entry(plan: dict[str, Any], entry_id: str) -> dict[str, Any]:
    translations = plan.get("translations", {})
    if not isinstance(translations, dict):
        return {}
    payload = translations.get(entry_id, {})
    return payload if isinstance(payload, dict) else {}
