from __future__ import annotations

from pathlib import Path
from typing import Any

from local_kb.common import normalize_string_list, normalize_text, parse_route_segments, safe_float
from local_kb.consolidate_events import load_history_events
from local_kb.i18n import DEFAULT_LANGUAGE, localized_entry, localized_route_label, normalize_language
from local_kb.adoption import blocked_organization_download_hashes, card_exchange_hash, dedupe_local_entries_by_exchange_hash
from local_kb.search import get_guidance, get_predicted_result, search_entries, search_multi_source_entries
from local_kb.skill_sharing import (
    annotate_dependencies_with_registry_status,
    extract_skill_dependencies,
    load_organization_skill_registry,
)
from local_kb.source_labels import card_source_summary
from local_kb.store import load_entries, load_organization_entries
from local_kb.taxonomy import build_taxonomy_gap_report, build_taxonomy_view


def _entry_id(entry: Any) -> str:
    return str(entry.data.get("id") or entry.path.stem)


def _route_label(route: list[str], language: str = DEFAULT_LANGUAGE, repo_root: Path | None = None) -> str:
    return localized_route_label(route, language, empty_label="root", repo_root=repo_root)


def _matches_prefix(route: list[str], prefix: list[str]) -> bool:
    return not prefix or route[: len(prefix)] == prefix


def _status_rank(status: str) -> int:
    ranks = {"trusted": 0, "candidate": 1, "deprecated": 2}
    return ranks.get(status.lower(), 3)


def _entry_sort_key(item: dict[str, Any]) -> tuple[int, float, str]:
    return (
        _status_rank(str(item.get("status") or "")),
        -safe_float(item.get("confidence"), 0.0),
        normalize_text(item.get("title") or ""),
    )


def _entry_display_path(entry: Any, repo_root: Path) -> str:
    source = getattr(entry, "source", {}) if hasattr(entry, "source") else {}
    source_path = str(source.get("path") or "").strip() if isinstance(source, dict) else ""
    if source_path and source.get("kind") == "organization":
        return source_path
    try:
        return entry.path.relative_to(repo_root).as_posix()
    except ValueError:
        return str(entry.path)


def summarize_entry(
    entry: Any,
    repo_root: Path,
    *,
    route_reason: str = "primary",
    match_route: list[str] | None = None,
    language: str = DEFAULT_LANGUAGE,
) -> dict[str, Any]:
    data = localized_entry(entry.data, normalize_language(language))
    skill_dependencies = extract_skill_dependencies(entry.data)
    domain_path = parse_route_segments(data.get("domain_path", []))
    cross_index = normalize_string_list(data.get("cross_index", []))
    summary = {
        "id": _entry_id(entry),
        "title": data.get("title") or _entry_id(entry),
        "type": data.get("type") or "",
        "scope": data.get("scope") or "",
        "status": data.get("status") or "",
        "confidence": data.get("confidence"),
        "domain_path": domain_path,
        "domain_label": _route_label(domain_path, language, repo_root),
        "cross_index": cross_index,
        "related_cards": normalize_string_list(data.get("related_cards", [])),
        "tags": data.get("tags", []),
        "trigger_keywords": data.get("trigger_keywords", []),
        "skill_dependency_count": len(skill_dependencies),
        "predicted_result": get_predicted_result(data),
        "guidance": get_guidance(data),
        "path": _entry_display_path(entry, repo_root),
        "source_info": getattr(entry, "source", {}),
        **card_source_summary(data, getattr(entry, "source", {})),
        "route_reason": route_reason,
        "match_route": match_route or domain_path,
    }
    if hasattr(entry, "score"):
        summary["score"] = round(safe_float(getattr(entry, "score", 0.0), 0.0), 3)
    return summary


def navigation_children(payload: dict[str, Any]) -> list[dict[str, Any]]:
    by_segment: dict[str, dict[str, Any]] = {}
    taxonomy = payload.get("taxonomy", {}) if isinstance(payload.get("taxonomy"), dict) else {}
    declared = taxonomy.get("children", []) if isinstance(taxonomy.get("children"), list) else []
    coverage = taxonomy.get("coverage", {}) if isinstance(taxonomy.get("coverage"), dict) else {}
    observed = coverage.get("undeclared_children", []) if isinstance(coverage.get("undeclared_children"), list) else []

    for item in [*declared, *observed]:
        if not isinstance(item, dict):
            continue
        segment = str(item.get("segment") or "").strip()
        if not segment:
            continue
        existing = by_segment.get(segment, {})
        by_segment[segment] = {**existing, **item}

    return sorted(by_segment.values(), key=lambda item: str(item.get("segment") or ""))


def navigation_card_count(item: dict[str, Any]) -> int:
    observed_count = int(item.get("observed_subtree_count") or 0)
    if observed_count:
        return observed_count
    return int(item.get("primary_subtree_count") or 0)


def _cross_route_match(data: dict[str, Any], prefix: list[str]) -> list[str] | None:
    if not prefix:
        return None
    for route_text in normalize_string_list(data.get("cross_index", [])):
        route = parse_route_segments(route_text)
        if _matches_prefix(route, prefix):
            return route
    return None


def _load_organization_entries_from_sources(
    organization_sources: list[dict[str, Any]] | None,
) -> list[Any]:
    organization_entries: list[Any] = []
    for source in organization_sources or []:
        org_root = Path(str(source.get("path") or source.get("local_path") or ""))
        organization_id = str(source.get("organization_id") or source.get("id") or "").strip()
        if not org_root.exists() or not organization_id:
            continue
        organization_entries.extend(
            load_organization_entries(
                org_root,
                organization_id,
                source_repo=str(source.get("source_repo") or source.get("repo_url") or ""),
                source_commit=str(source.get("source_commit") or ""),
            )
        )
    return organization_entries


def _load_entries_for_views(repo_root: Path, organization_sources: list[dict[str, Any]] | None = None) -> list[Any]:
    local_entries = dedupe_local_entries_by_exchange_hash(load_entries(repo_root))
    if not organization_sources:
        return local_entries
    blocked_hashes = blocked_organization_download_hashes(repo_root)
    organization_entries = [
        entry
        for entry in _load_organization_entries_from_sources(organization_sources)
        if card_exchange_hash(entry.data) not in blocked_hashes
    ]
    return [*local_entries, *organization_entries]


def build_route_view_payload(
    repo_root: Path,
    route: str = "",
    language: str = DEFAULT_LANGUAGE,
    organization_sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    entries = _load_entries_for_views(repo_root, organization_sources)
    prefix = parse_route_segments(route)
    taxonomy_view = build_taxonomy_view(repo_root, route="/".join(prefix))
    normalized_language = normalize_language(language)

    primary: list[dict[str, Any]] = []
    cross: list[dict[str, Any]] = []
    primary_ids: set[str] = set()

    for entry in entries:
        data = entry.data
        domain_path = parse_route_segments(data.get("domain_path", []))
        if _matches_prefix(domain_path, prefix):
            primary_ids.add(_entry_id(entry))
            primary.append(
                summarize_entry(
                    entry,
                    repo_root,
                    route_reason="primary",
                    match_route=domain_path,
                    language=normalized_language,
                )
            )

    for entry in entries:
        entry_id = _entry_id(entry)
        if entry_id in primary_ids:
            continue
        cross_match = _cross_route_match(entry.data, prefix)
        if cross_match is None:
            continue
        cross.append(
            summarize_entry(
                entry,
                repo_root,
                route_reason="cross",
                match_route=cross_match,
                language=normalized_language,
            )
        )

    primary = sorted(primary, key=_entry_sort_key)
    cross = sorted(cross, key=_entry_sort_key)

    return {
        "route": prefix,
        "route_label": _route_label(prefix, normalized_language, repo_root),
        "taxonomy": taxonomy_view,
        "cards": {
            "primary": primary,
            "cross": cross,
        },
        "deck": primary + cross,
    }


def build_source_view_payload(
    repo_root: Path,
    source_kind: str,
    language: str = DEFAULT_LANGUAGE,
    organization_sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source_kind = str(source_kind or "").strip().lower()
    normalized_language = normalize_language(language)
    deck = [
        summarize_entry(
            entry,
            repo_root,
            route_reason="source",
            match_route=parse_route_segments(entry.data.get("domain_path", [])),
            language=normalized_language,
        )
        for entry in _load_entries_for_views(repo_root, organization_sources)
        if str((getattr(entry, "source", {}) or {}).get("kind") or "local").lower() == source_kind
    ]
    return {
        "source_kind": source_kind,
        "deck": sorted(deck, key=_entry_sort_key),
    }


def _entry_history(repo_root: Path, entry_id: str, max_events: int = 8) -> list[dict[str, Any]]:
    events = load_history_events(repo_root, max_events=400)
    matched: list[dict[str, Any]] = []
    for event in reversed(events):
        entry_ids = [str(item) for item in event.get("entry_ids", [])]
        target = event.get("target", {}) if isinstance(event.get("target"), dict) else {}
        target_entry_id = str(target.get("entry_id", "") or "").strip()
        if entry_id not in entry_ids and entry_id != target_entry_id:
            continue
        matched.append(
            {
                "event_id": event.get("event_id"),
                "event_type": event.get("event_type"),
                "created_at": event.get("created_at"),
                "task_summary": event.get("task_summary"),
                "hit_quality": event.get("hit_quality"),
                "suggested_action": event.get("suggested_action"),
                "project_ref": event.get("project_ref"),
                "rationale": event.get("rationale"),
            }
        )
        if len(matched) >= max_events:
            break
    return matched


def _load_entries_for_detail(
    repo_root: Path,
    organization_sources: list[dict[str, Any]] | None = None,
    *,
    prefer_source_info: dict[str, Any] | None = None,
) -> list[Any]:
    local_entries = load_entries(repo_root)
    organization_entries = _load_organization_entries_from_sources(organization_sources)
    if (prefer_source_info or {}).get("kind") == "organization":
        return [*organization_entries, *local_entries]
    return [*local_entries, *organization_entries]


def _entry_matches_source_info(entry: Any, source_info: dict[str, Any] | None) -> bool:
    if not source_info:
        return True
    entry_source = getattr(entry, "source", {}) if hasattr(entry, "source") else {}
    if not isinstance(entry_source, dict):
        return False
    for key in ("kind", "organization_id", "path"):
        expected = str(source_info.get(key) or "").strip()
        if expected and str(entry_source.get(key) or "").strip() != expected:
            return False
    return True


def _merged_skill_registry(organization_sources: list[dict[str, Any]] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {"ok": True, "errors": [], "skills": [], "by_id": {}, "by_bundle_id": {}}
    for source in organization_sources or []:
        org_root = Path(str(source.get("path") or source.get("local_path") or ""))
        if not org_root.exists():
            continue
        registry = load_organization_skill_registry(org_root)
        if not registry.get("ok"):
            merged["ok"] = False
            merged["errors"].extend(registry.get("errors") or [])
        merged["skills"].extend(registry.get("skills") or [])
        for skill_id, item in (registry.get("by_id") or {}).items():
            merged["by_id"][skill_id] = item
        for bundle_id, item in (registry.get("by_bundle_id") or {}).items():
            merged["by_bundle_id"][bundle_id] = item
    return merged


def build_skill_registry_payload(
    organization_sources: list[dict[str, Any]] | None,
    *,
    local_policy_allows_auto_install: bool = False,
) -> dict[str, Any]:
    registry = _merged_skill_registry(organization_sources)
    skills = []
    for skill in registry.get("skills") or []:
        annotated = {
            **skill,
            "auto_install": annotate_dependencies_with_registry_status(
                [{"id": skill.get("id"), "requirement": "optional"}],
                registry,
                local_policy_allows_auto_install=local_policy_allows_auto_install,
            )[0]["auto_install"],
        }
        skills.append(annotated)
    return {
        "ok": registry.get("ok"),
        "errors": registry.get("errors") or [],
        "skills": skills,
        "counts": {
            "candidate": sum(1 for item in skills if item.get("status") == "candidate"),
            "approved": sum(1 for item in skills if item.get("status") == "approved"),
            "rejected": sum(1 for item in skills if item.get("status") == "rejected"),
        },
    }


def build_card_detail_payload(
    repo_root: Path,
    entry_id: str,
    language: str = DEFAULT_LANGUAGE,
    organization_sources: list[dict[str, Any]] | None = None,
    source_info: dict[str, Any] | None = None,
    local_policy_allows_skill_auto_install: bool = False,
) -> dict[str, Any] | None:
    normalized_language = normalize_language(language)
    for entry in _load_entries_for_detail(repo_root, organization_sources, prefer_source_info=source_info):
        if _entry_id(entry) != entry_id:
            continue
        if not _entry_matches_source_info(entry, source_info):
            continue
        raw_data = entry.data
        data = localized_entry(entry.data, normalized_language)
        summary = summarize_entry(entry, repo_root, language=normalized_language)
        is_local_entry = summary.get("source_info", {}).get("kind") != "organization"
        dependencies = extract_skill_dependencies(raw_data)
        registry = _merged_skill_registry(organization_sources)
        return {
            **summary,
            "if": data.get("if"),
            "action": data.get("action"),
            "predict": data.get("predict"),
            "use": data.get("use"),
            "source": data.get("source"),
            "updated_at": data.get("updated_at"),
            "raw": raw_data,
            "skill_dependencies": annotate_dependencies_with_registry_status(
                dependencies,
                registry,
                local_policy_allows_auto_install=local_policy_allows_skill_auto_install,
            ),
            "recent_history": _entry_history(repo_root, entry_id) if is_local_entry else [],
        }
    return None


def build_overview_payload(repo_root: Path) -> dict[str, Any]:
    entries = load_entries(repo_root)
    status_counts: dict[str, int] = {}
    scope_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    for entry in entries:
        data = entry.data
        status = str(data.get("status") or "unknown")
        scope = str(data.get("scope") or "unknown")
        entry_type = str(data.get("type") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        scope_counts[scope] = scope_counts.get(scope, 0) + 1
        type_counts[entry_type] = type_counts.get(entry_type, 0) + 1

    events = load_history_events(repo_root, max_events=50)
    gaps = build_taxonomy_gap_report(repo_root)

    return {
        "entry_count": len(entries),
        "status_counts": status_counts,
        "scope_counts": scope_counts,
        "type_counts": type_counts,
        "recent_event_count": len(events),
        "latest_events": list(reversed(events[-5:])),
        "taxonomy_gap_count": gaps.get("route_count", 0),
        "taxonomy_gaps": gaps.get("gaps", [])[:5],
    }


def build_search_payload(
    repo_root: Path,
    query: str,
    route_hint: str = "",
    top_k: int = 12,
    language: str = DEFAULT_LANGUAGE,
    organization_sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    results = [
        summarize_entry(
            entry,
            repo_root,
            route_reason="search",
            match_route=parse_route_segments(entry.data.get("domain_path", [])),
            language=language,
        )
        for entry in search_multi_source_entries(
            repo_root,
            query=query,
            path_hint=route_hint,
            top_k=top_k,
            organization_sources=organization_sources,
        )
    ]
    return {
        "query": query,
        "route_hint": parse_route_segments(route_hint),
        "results": results,
    }
