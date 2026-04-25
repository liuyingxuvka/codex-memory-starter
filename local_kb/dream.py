from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from local_kb.adoption import card_exchange_hash, find_local_entry_by_exchange_hash
from local_kb.common import parse_route_segments, utc_now_iso
from local_kb.consolidate import APPLY_MODE_NONE, consolidate_history, sanitize_run_id
from local_kb.consolidate_apply import build_auto_candidate_entry
from local_kb.consolidate_events import (
    load_history_events,
    relative_repo_path,
    supporting_events_for_action,
)
from local_kb.feedback import build_observation, record_observation
from local_kb.history import build_history_event, record_history_event
from local_kb.maintenance_lanes import build_lane_guard, write_lane_status
from local_kb.search import render_search_payload, search_entries
from local_kb.store import candidate_dir, history_events_path, load_entries, write_yaml_file
from local_kb.taxonomy import build_taxonomy_gap_report


DREAM_SCHEMA_VERSION = 1
DREAM_REPORT_KIND = "local-kb-dream-report"
PLAN_FILENAME = "plan.json"
PREFLIGHT_FILENAME = "preflight.json"
OPPORTUNITIES_FILENAME = "opportunities.json"
EXPERIMENTS_FILENAME = "experiments.json"
EXECUTION_PLAN_FILENAME = "execution_plan.json"
REPORT_FILENAME = "report.json"

DREAM_PREFLIGHT_SEARCHES = (
    {
        "route_ref": "predictive-kb/agent-lifecycle/exploration",
        "query": (
            "Dream mode bounded exploration history-only candidate-only "
            "run-level observation prior dream process guidance"
        ),
    },
    {
        "route_ref": "kb/dream/verification",
        "query": "Dream runner verification tests bounded local experiment write-back",
    },
)


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def dream_run_dir(repo_root: Path, run_id: str) -> Path:
    return repo_root / "kb" / "history" / "dream" / run_id


def build_sleep_guard(
    repo_root: Path,
    *,
    cooldown_minutes: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    reference_time = now or datetime.now(timezone.utc)
    consolidation_root = repo_root / "kb" / "history" / "consolidation"
    lane_guard = build_lane_guard(repo_root, "kb-dream")
    latest_run_dir: Path | None = None
    latest_mtime: float | None = None

    if consolidation_root.exists():
        for path in consolidation_root.iterdir():
            if not path.is_dir() or not path.name.startswith("kb-sleep"):
                continue
            stat = path.stat()
            if latest_mtime is None or stat.st_mtime > latest_mtime:
                latest_mtime = stat.st_mtime
                latest_run_dir = path

    minutes_since_latest: float | None = None
    if latest_mtime is not None:
        minutes_since_latest = max(0.0, (reference_time.timestamp() - latest_mtime) / 60.0)

    cooldown_blocked = (
        cooldown_minutes > 0
        and minutes_since_latest is not None
        and minutes_since_latest < cooldown_minutes
    )
    blocked = bool(lane_guard["blocked"] or cooldown_blocked)
    return {
        "blocked": blocked,
        "lane_guard": lane_guard,
        "cooldown_minutes": cooldown_minutes,
        "cooldown_blocked": cooldown_blocked,
        "latest_sleep_run_dir": relative_repo_path(repo_root, latest_run_dir) if latest_run_dir else "",
        "minutes_since_latest_sleep_run": round(minutes_since_latest, 2)
        if minutes_since_latest is not None
        else None,
    }


def _entry_route(entry: Any) -> list[str]:
    return parse_route_segments(entry.data.get("domain_path", []))


def _exact_route_entries(entries: list[Any], route: list[str]) -> list[Any]:
    return [entry for entry in entries if _entry_route(entry) == route]


def _sibling_route_labels(entries: list[Any], route: list[str]) -> list[str]:
    if not route:
        return []
    parent = route[:-1]
    labels: set[str] = set()
    for entry in entries:
        entry_route = _entry_route(entry)
        if len(entry_route) != len(route):
            continue
        if entry_route == route:
            continue
        if entry_route[:-1] != parent:
            continue
        labels.add("/".join(entry_route))
    return sorted(labels)


def _route_title(route: list[str]) -> str:
    return " / ".join(route) if route else "root"


def _score_opportunity(
    *,
    repeated_signal: int,
    boundedness: int,
    validation_readiness: int,
    reuse_potential: int,
    execution_risk: int,
) -> int:
    return (
        (4 * repeated_signal)
        + (3 * boundedness)
        + (3 * validation_readiness)
        + (2 * reuse_potential)
        - (4 * execution_risk)
    )


def _selection_priority(opportunity: dict[str, Any]) -> int:
    if opportunity.get("kind") == "route-candidate":
        mode = str(opportunity.get("candidate_creation_mode", "") or "")
        if mode == "dream-adjacent":
            return 4
        if mode == "sleep-eligible":
            return 1
    if opportunity.get("kind") == "entry-validation":
        return 3
    if opportunity.get("kind") == "taxonomy-gap":
        return 2
    return 0


def _safe_confidence(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.5


def _entry_validation_query(entry: Any) -> str:
    data = entry.data
    predict_block = data.get("predict", {})
    use_block = data.get("use", {})
    if not isinstance(predict_block, dict):
        predict_block = {}
    if not isinstance(use_block, dict):
        use_block = {}
    parts = [
        str(data.get("title", "") or "").strip(),
        str(predict_block.get("expected_result", "") or "").strip(),
        str(use_block.get("guidance", "") or "").strip(),
    ]
    return " ".join(part for part in parts if part) or _route_title(_entry_route(entry))


def _predictive_preview_available(action: dict[str, Any]) -> bool:
    preview = action.get("candidate_scaffold_preview", {})
    if not isinstance(preview, dict):
        return False
    if_block = preview.get("if", {})
    action_block = preview.get("action", {})
    predict_block = preview.get("predict", {})
    if not isinstance(if_block, dict):
        if_block = {}
    if not isinstance(action_block, dict):
        action_block = {}
    if not isinstance(predict_block, dict):
        predict_block = {}
    return any(
        str(value or "").strip()
        for value in (
            preview.get("title"),
            if_block.get("notes"),
            action_block.get("description"),
            predict_block.get("expected_result"),
        )
    )


def build_route_candidate_opportunities(
    actions: list[dict[str, Any]],
    entries: list[Any],
) -> list[dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []
    for action in actions:
        if action.get("action_type") != "consider-new-candidate":
            continue
        target = action.get("target", {})
        if not isinstance(target, dict) or target.get("kind") != "route":
            continue
        route_ref = str(target.get("ref", "") or "").strip()
        route = parse_route_segments(route_ref)
        if not route:
            continue

        exact_route_entry_count = len(_exact_route_entries(entries, route))
        sibling_routes = _sibling_route_labels(entries, route)
        predictive_preview = _predictive_preview_available(action)
        event_count = int(action.get("event_count", 0) or 0)
        task_summaries = list(action.get("task_summaries", []))
        apply_eligibility = action.get("apply_eligibility", {})
        if not isinstance(apply_eligibility, dict):
            apply_eligibility = {}

        candidate_creation_mode = ""
        if exact_route_entry_count == 0 and len(route) >= 3:
            if apply_eligibility.get("eligible", False):
                candidate_creation_mode = "sleep-eligible"
            elif predictive_preview and sibling_routes:
                candidate_creation_mode = "dream-adjacent"

        repeated_signal = min(3, max(1, event_count))
        boundedness = min(3, len(route))
        validation_readiness = 3 if predictive_preview else (2 if task_summaries else 1)
        reuse_potential = min(3, min(len(sibling_routes), 2) + (1 if event_count >= 2 else 0))
        execution_risk = 0 if len(route) >= 3 and exact_route_entry_count == 0 else 1
        opportunity_score = _score_opportunity(
            repeated_signal=repeated_signal,
            boundedness=boundedness,
            validation_readiness=validation_readiness,
            reuse_potential=reuse_potential,
            execution_risk=execution_risk,
        )

        opportunities.append(
            {
                "kind": "route-candidate",
                "route": route,
                "route_ref": route_ref,
                "route_title": _route_title(route),
                "source_action": action,
                "task_summaries": task_summaries,
                "exact_route_entry_count": exact_route_entry_count,
                "sibling_routes": sibling_routes,
                "sibling_route_count": len(sibling_routes),
                "candidate_creation_mode": candidate_creation_mode,
                "hypothesis": (
                    f"A bounded predictive candidate for {_route_title(route)} may be missing, and adjacent "
                    "route evidence is strong enough to justify one dream-mode validation pass."
                ),
                "allowed_action_surface": (
                    "Inspect local search results and supporting observations, then write only to history or "
                    "kb/candidates when the route is still uncovered."
                ),
                "score_components": {
                    "repeated_signal": repeated_signal,
                    "boundedness": boundedness,
                    "validation_readiness": validation_readiness,
                    "reuse_potential": reuse_potential,
                    "execution_risk": execution_risk,
                },
                "opportunity_score": opportunity_score,
            }
        )

    return opportunities


def build_taxonomy_gap_opportunities(
    repo_root: Path,
    entries: list[Any],
) -> list[dict[str, Any]]:
    report = build_taxonomy_gap_report(repo_root)
    opportunities: list[dict[str, Any]] = []
    for gap in report.get("gaps", []):
        if not isinstance(gap, dict):
            continue
        route = parse_route_segments(gap.get("route", []))
        if not route:
            continue
        exact_route_entry_count = len(_exact_route_entries(entries, route))
        sibling_routes = _sibling_route_labels(entries, route)
        observed_subtree_count = int(gap.get("observed_subtree_count", 0) or 0)
        example_routes = list(gap.get("example_observed_routes", []))

        repeated_signal = min(3, max(1, observed_subtree_count))
        boundedness = min(3, len(route))
        validation_readiness = 2 if example_routes else 1
        reuse_potential = min(3, min(len(sibling_routes), 2) + (1 if observed_subtree_count >= 2 else 0))
        execution_risk = 1 if len(route) >= 3 else 2
        opportunity_score = _score_opportunity(
            repeated_signal=repeated_signal,
            boundedness=boundedness,
            validation_readiness=validation_readiness,
            reuse_potential=reuse_potential,
            execution_risk=execution_risk,
        )

        opportunities.append(
            {
                "kind": "taxonomy-gap",
                "route": route,
                "route_ref": "/".join(route),
                "route_title": _route_title(route),
                "task_summaries": example_routes,
                "exact_route_entry_count": exact_route_entry_count,
                "sibling_routes": sibling_routes,
                "sibling_route_count": len(sibling_routes),
                "candidate_creation_mode": "",
                "hypothesis": (
                    f"The undeclared route {_route_title(route)} may deserve a bounded candidate or taxonomy review, "
                    "but dream mode should validate it without touching trusted memory."
                ),
                "allowed_action_surface": (
                    "Inspect route-local search output and leave a history note for taxonomy or candidate review; "
                    "do not rewrite trusted cards."
                ),
                "score_components": {
                    "repeated_signal": repeated_signal,
                    "boundedness": boundedness,
                    "validation_readiness": validation_readiness,
                    "reuse_potential": reuse_potential,
                    "execution_risk": execution_risk,
                },
                "opportunity_score": opportunity_score,
            }
        )

    return opportunities


def build_entry_validation_opportunities(repo_root: Path, entries: list[Any]) -> list[dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []
    for entry in entries:
        data = entry.data
        route = _entry_route(entry)
        if not route:
            continue
        status = str(data.get("status", "candidate") or "candidate").lower()
        confidence = _safe_confidence(data.get("confidence", 0.5))
        if status != "candidate" and confidence >= 0.75:
            continue

        query = _entry_validation_query(entry)
        repeated_signal = 2 if status == "candidate" else 1
        boundedness = min(3, len(route))
        validation_readiness = 3 if query else 1
        reuse_potential = 3 if status == "candidate" else 2
        execution_risk = 0
        opportunity_score = _score_opportunity(
            repeated_signal=repeated_signal,
            boundedness=boundedness,
            validation_readiness=validation_readiness,
            reuse_potential=reuse_potential,
            execution_risk=execution_risk,
        )

        opportunities.append(
            {
                "kind": "entry-validation",
                "route": route,
                "route_ref": "/".join(route),
                "route_title": _route_title(route),
                "source_entry_id": str(data.get("id", "") or ""),
                "source_entry_path": relative_repo_path(repo_root, entry.path),
                "entry_status": status,
                "entry_confidence": confidence,
                "validation_query": query,
                "task_summaries": [query],
                "exact_route_entry_count": len(_exact_route_entries(entries, route)),
                "sibling_routes": _sibling_route_labels(entries, route),
                "sibling_route_count": len(_sibling_route_labels(entries, route)),
                "candidate_creation_mode": "",
                "hypothesis": (
                    f"The existing {status} card {data.get('id', 'unknown')} under {_route_title(route)} "
                    "may deserve one direct Dream validation pass before stronger reliance."
                ),
                "allowed_action_surface": (
                    "Run read-only retrieval checks against the local KB and write the result only to history."
                ),
                "score_components": {
                    "repeated_signal": repeated_signal,
                    "boundedness": boundedness,
                    "validation_readiness": validation_readiness,
                    "reuse_potential": reuse_potential,
                    "execution_risk": execution_risk,
                },
                "opportunity_score": opportunity_score,
            }
        )
    return opportunities


def _execution_contract(opportunity: dict[str, Any]) -> dict[str, Any]:
    kind = str(opportunity.get("kind", "") or "")
    mode = str(opportunity.get("candidate_creation_mode", "") or "")
    if kind == "route-candidate" and mode == "dream-adjacent":
        safety_tier = "workspace-only"
        experiment_design = "Validate missing route coverage with local search and adjacent route support, then create a candidate scaffold only if coverage remains absent."
        validation_plan = "Search the target route, require no exact route hit and at least one sibling route hit before candidate creation."
        rollback_plan = "Candidate creation is the only workspace mutation; keep append-only history provenance and leave any candidate for later sleep review or manual removal."
        permitted_write_back = "history-only or candidate-only"
    elif kind == "route-candidate" and mode == "sleep-eligible":
        safety_tier = "read-only"
        experiment_design = "Confirm that this route is already owned by sleep maintenance rather than duplicating candidate creation."
        validation_plan = "Inspect consolidation ownership and route-local search output, then write only a history note."
        rollback_plan = "No rollback needed because the experiment writes no files beyond append-only history."
        permitted_write_back = "history-only"
    elif kind == "entry-validation":
        safety_tier = "read-only"
        experiment_design = "Validate an existing low-confidence or candidate card against route-local retrieval evidence."
        validation_plan = "Search with the card route and validation query, then classify the result from exact or adjacent local evidence."
        rollback_plan = "No rollback needed because the experiment writes no files beyond append-only history."
        permitted_write_back = "history-only"
    elif kind == "taxonomy-gap":
        safety_tier = "read-only"
        experiment_design = "Inspect an observed taxonomy gap with route-local retrieval evidence before proposing taxonomy work."
        validation_plan = "Search the undeclared route and sibling routes, then record whether the gap remains useful for later taxonomy review."
        rollback_plan = "No rollback needed because the experiment writes no files beyond append-only history."
        permitted_write_back = "history-only"
    else:
        safety_tier = "read-only"
        experiment_design = "Inspect the opportunity with route-local retrieval evidence."
        validation_plan = "Search the route and record a bounded history result."
        rollback_plan = "No rollback needed because the experiment writes no files beyond append-only history."
        permitted_write_back = "history-only"

    safety_allowed = safety_tier in {"read-only", "workspace-only"}
    score_components = opportunity.get("score_components", {})
    if not isinstance(score_components, dict):
        score_components = {}
    validation_readiness = int(score_components.get("validation_readiness", 0) or 0)
    execution_risk = int(score_components.get("execution_risk", 0) or 0)
    is_executable = bool(experiment_design and validation_plan and safety_allowed and validation_readiness > 0)
    blocked_reason = "" if is_executable else "No executable validation plan could be constructed inside the allowed safety tiers."

    enriched = dict(opportunity)
    enriched.update(
        {
            "experiment_design": experiment_design,
            "validation_plan": validation_plan,
            "success_criteria": "The validation produces exact or adjacent local evidence, or safely creates a bounded candidate scaffold when explicitly allowed.",
            "failure_criteria": "The validation finds no grounded support, discovers existing exact coverage, or identifies ownership by sleep maintenance.",
            "safety_tier": safety_tier,
            "rollback_plan": rollback_plan,
            "permitted_write_back": permitted_write_back,
            "is_executable": is_executable,
            "blocked_reason": blocked_reason,
            "executability_score": (3 * validation_readiness) - (2 * execution_risk),
            "execution_checkpoints": [
                "preflight",
                "opportunity-scan",
                "single-experiment-selection",
                "experiment-record",
                "validation",
                "experiment-observation",
                "run-observation",
                "report",
            ],
        }
    )
    return enriched


def _prepare_opportunities(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_execution_contract(opportunity) for opportunity in opportunities]


def _validation_query(opportunity: dict[str, Any]) -> str:
    validation_query = str(opportunity.get("validation_query", "") or "").strip()
    if validation_query:
        return validation_query
    task_summaries = [str(item or "").strip() for item in opportunity.get("task_summaries", []) if str(item or "").strip()]
    if task_summaries:
        return " ".join(task_summaries[:2])
    return opportunity.get("route_title", "route exploration")


def _search_context(repo_root: Path, route_ref: str, query: str) -> dict[str, Any]:
    search_results = render_search_payload(
        search_entries(repo_root, query=query, path_hint=route_ref, top_k=5),
        repo_root,
    )
    route = parse_route_segments(route_ref)
    parent = route[:-1]
    exact_route_hits = 0
    sibling_route_hits = 0
    for item in search_results:
        item_route = parse_route_segments(item.get("domain_path", []))
        if item_route == route:
            exact_route_hits += 1
        elif parent and len(item_route) == len(route) and item_route[:-1] == parent:
            sibling_route_hits += 1

    return {
        "query": query,
        "path_hint": route_ref,
        "result_count": len(search_results),
        "exact_route_hit_count": exact_route_hits,
        "sibling_route_hit_count": sibling_route_hits,
        "results": search_results,
    }


def _unique_entry_ids(searches: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    entry_ids: list[str] = []
    for search in searches:
        for result in search.get("results", []):
            entry_id = str(result.get("id", "") or "").strip()
            if not entry_id or entry_id in seen:
                continue
            seen.add(entry_id)
            entry_ids.append(entry_id)
    return entry_ids


def _build_dream_preflight(repo_root: Path, *, run_id: str, generated_at: str) -> dict[str, Any]:
    searches: list[dict[str, Any]] = []
    for spec in DREAM_PREFLIGHT_SEARCHES:
        route_ref = str(spec["route_ref"])
        query = str(spec["query"])
        results = render_search_payload(
            search_entries(repo_root, query=query, path_hint=route_ref, top_k=5),
            repo_root,
        )
        searches.append(
            {
                "route_ref": route_ref,
                "query": query,
                "result_count": len(results),
                "results": results,
            }
        )

    matched_entry_ids = _unique_entry_ids(searches)
    return {
        "schema_version": DREAM_SCHEMA_VERSION,
        "kind": "local-kb-dream-preflight",
        "run_id": run_id,
        "generated_at": generated_at,
        "purpose": "Recall prior Dream-process guidance before selecting bounded experiments.",
        "searches": searches,
        "matched_entry_ids": matched_entry_ids,
        "matched_entry_count": len(matched_entry_ids),
    }


def _create_dream_candidate(
    repo_root: Path,
    *,
    action: dict[str, Any],
    run_id: str,
    generated_at: str,
    creation_mode: str,
    indexed_events: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    supporting_events = supporting_events_for_action(action, indexed_events)
    entry = build_auto_candidate_entry(
        repo_root,
        action=action,
        supporting_events=supporting_events,
        run_id=run_id,
        generated_at=generated_at,
    )
    entry["tags"] = sorted(set(list(entry.get("tags", [])) + ["dream-generated"]))
    use_block = entry.get("use", {})
    if not isinstance(use_block, dict):
        use_block = {}
        entry["use"] = use_block
    guidance = str(use_block.get("guidance", "") or "").strip()
    extra_guidance = (
        "Dream-generated from a bounded exploration pass; require live-task confirmation before any promotion."
    )
    use_block["guidance"] = f"{guidance} {extra_guidance}".strip()
    sources = entry.get("source", [])
    if not isinstance(sources, list):
        sources = []
        entry["source"] = sources
    if sources and isinstance(sources[0], dict):
        sources[0]["origin"] = "dream exploration"
        sources[0]["dream_mode"] = creation_mode

    existing_same_hash = find_local_entry_by_exchange_hash(repo_root, card_exchange_hash(entry))
    if existing_same_hash is not None:
        return None, f"Candidate content hash already exists: {relative_repo_path(repo_root, existing_same_hash.path)}"

    target_path = candidate_dir(repo_root) / f"{entry['id']}.yaml"
    relative_target_path = relative_repo_path(repo_root, target_path)
    if target_path.exists():
        return None, f"Candidate file already exists: {relative_target_path}"

    write_yaml_file(target_path, entry)
    history_event = build_history_event(
        "candidate-created",
        source={
            "kind": "dream-apply",
            "agent": "kb-dreamer",
            "run_id": run_id,
        },
        target={
            "kind": "candidate-entry",
            "entry_id": entry["id"],
            "entry_path": relative_target_path,
            "scope": entry["scope"],
            "domain_path": entry["domain_path"],
        },
        rationale=f"Dream experiment created a bounded candidate scaffold via {creation_mode}.",
        context={
            "action_key": action["action_key"],
            "event_count": action["event_count"],
            "event_ids": list(action.get("event_ids", [])),
            "dream_mode": creation_mode,
            "title": entry["title"],
            "entry_type": entry["type"],
        },
    )
    record_history_event(repo_root, history_event)
    return (
        {
            "entry_id": entry["id"],
            "entry_path": relative_target_path,
            "title": entry["title"],
            "source_action_key": action["action_key"],
        },
        "",
    )


def _record_dream_observation(
    repo_root: Path,
    *,
    run_id: str,
    opportunity: dict[str, Any],
    experiment: dict[str, Any],
    created_candidate: dict[str, Any] | None,
) -> str:
    suggested_action = "none"
    if created_candidate is not None:
        suggested_action = "new-candidate"
    elif opportunity["kind"] == "taxonomy-gap":
        suggested_action = "taxonomy-change"

    route_ref = str(opportunity.get("route_ref", "") or "")
    entry_ids = created_candidate["entry_id"] if created_candidate else ""
    outcome = str(experiment.get("outcome", "") or "")
    comment = str(experiment.get("comment", "") or "")
    scenario = str(opportunity.get("hypothesis", "") or "")
    action_taken = str(experiment.get("action_taken", "") or "")
    observed_result = str(experiment.get("observed_result", "") or "")
    operational_use = str(experiment.get("operational_use", "") or "")
    reuse_judgment = str(experiment.get("reuse_judgment", "") or "")
    observation = build_observation(
        task_summary=f"Dream experiment for {opportunity['route_title']}",
        route_hint=route_ref,
        entry_ids=entry_ids,
        hit_quality="weak" if experiment["search_context"]["exact_route_hit_count"] == 0 else "hit",
        outcome=outcome,
        comment=comment,
        suggested_action=suggested_action,
        exposed_gap=opportunity["kind"] == "taxonomy-gap" or created_candidate is not None,
        scenario=scenario,
        action_taken=action_taken,
        observed_result=observed_result,
        operational_use=operational_use,
        reuse_judgment=reuse_judgment,
        source_kind="dream-maintenance",
        agent_name="kb-dreamer",
        thread_ref=f"dream-run::{run_id}",
        project_ref=repo_root.name,
        workspace_root=str(repo_root),
    )
    record_observation(repo_root, observation)
    return str(observation["event_id"])


def _record_dream_run_observation(
    repo_root: Path,
    *,
    run_id: str,
    preflight: dict[str, Any],
    opportunity_count: int,
    selected: list[dict[str, Any]],
    experiment_results: list[dict[str, Any]],
    created_candidates: list[dict[str, Any]],
) -> str:
    entry_ids = [str(item) for item in preflight.get("matched_entry_ids", []) if str(item).strip()]
    classifications = sorted(
        {
            str(experiment.get("classification", "") or "unknown")
            for experiment in experiment_results
        }
    )
    selected_routes = [
        str(opportunity.get("route_ref", "") or "")
        for opportunity in selected
        if str(opportunity.get("route_ref", "") or "").strip()
    ]
    classification_text = ", ".join(classifications) if classifications else "none"
    route_text = ", ".join(selected_routes) if selected_routes else "none"
    outcome = (
        f"Dream run completed with {opportunity_count} opportunities, {len(selected)} selected experiments, "
        f"{len(created_candidates)} candidates, and classifications: {classification_text}."
    )
    observation = build_observation(
        task_summary=f"Dream run-level postflight for {run_id}",
        route_hint="predictive-kb/agent-lifecycle/exploration",
        entry_ids=",".join(entry_ids),
        hit_quality="hit" if entry_ids else "weak",
        outcome=outcome,
        comment=(
            "Recorded the Dream-process preflight, selected routes, result classifications, "
            "and write-back boundary for this whole run."
        ),
        suggested_action="none",
        exposed_gap=False,
        scenario="When a recurring Dream maintenance pass runs bounded KB exploration.",
        action_taken=(
            "Retrieved prior Dream-process guidance, selected bounded opportunities, "
            "validated them with local search, and kept write-back history-only or candidate-only."
        ),
        observed_result=(
            f"Preflight matched {len(entry_ids)} entries; selected routes: {route_text}; "
            f"created candidates: {len(created_candidates)}; classifications: {classification_text}."
        ),
        operational_use=(
            "Use this run-level note to improve Dream process behavior separately from "
            "route-specific experiment outcomes."
        ),
        reuse_judgment=(
            "Reusable because Dream is a recurring maintenance lane and process-level behavior "
            "should accumulate without changing trusted memory directly."
        ),
        source_kind="dream-maintenance",
        agent_name="kb-dreamer",
        thread_ref=f"dream-run::{run_id}",
        project_ref=repo_root.name,
        workspace_root=str(repo_root),
    )
    record_observation(repo_root, observation)
    return str(observation["event_id"])


def _checkpoint(checkpoint_id: str, label: str, status: str, details: str = "") -> dict[str, Any]:
    return {
        "id": checkpoint_id,
        "label": label,
        "status": status,
        "details": details,
    }


def _build_execution_plan(
    repo_root: Path,
    *,
    run_id: str,
    generated_at: str,
    opportunity_count: int,
    executable_opportunity_count: int,
    selected: list[dict[str, Any]],
) -> dict[str, Any]:
    selected_experiment = None
    if selected:
        item = selected[0]
        selected_experiment = {
            "route_ref": item["route_ref"],
            "kind": item["kind"],
            "hypothesis": item["hypothesis"],
            "experiment_design": item["experiment_design"],
            "validation_plan": item["validation_plan"],
            "success_criteria": item["success_criteria"],
            "failure_criteria": item["failure_criteria"],
            "safety_tier": item["safety_tier"],
            "rollback_plan": item["rollback_plan"],
            "permitted_write_back": item["permitted_write_back"],
            "executability_score": item["executability_score"],
        }

    selection_status = "completed" if selected else "blocked"
    selection_details = (
        "Selected exactly one executable experiment."
        if selected
        else "No executable experiment was available inside the allowed safety tiers."
    )
    return {
        "schema_version": DREAM_SCHEMA_VERSION,
        "kind": "local-kb-dream-execution-plan",
        "run_id": run_id,
        "generated_at": generated_at,
        "status": "running",
        "policy": {
            "selection_rule": "Select exactly one executable experiment when any executable opportunity exists.",
            "allowed_safety_tiers": ["read-only", "workspace-only"],
        },
        "opportunity_count": opportunity_count,
        "executable_opportunity_count": executable_opportunity_count,
        "selected_experiment_count": len(selected),
        "selected_experiment": selected_experiment,
        "checkpoints": [
            _checkpoint("preflight", "Prior Dream-process guidance retrieved", "completed"),
            _checkpoint("opportunity-scan", "Opportunities gathered and executable contracts attached", "completed"),
            _checkpoint("single-experiment-selection", "Exactly one executable experiment selected", selection_status, selection_details),
            _checkpoint("experiment-record", "Experiment record written before action", "completed" if selected else "skipped", selection_details),
            _checkpoint("validation", "Selected experiment validated", "pending" if selected else "skipped", selection_details),
            _checkpoint("experiment-observation", "Route-specific experiment observation written", "pending" if selected else "skipped", selection_details),
            _checkpoint("run-observation", "Run-level Dream-process observation written", "pending"),
            _checkpoint("report", "Dream report written", "pending"),
        ],
        "artifact_paths": {
            "run_dir": relative_repo_path(repo_root, dream_run_dir(repo_root, run_id)),
        },
    }


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


def _write_skip_event(repo_root: Path, run_id: str, sleep_guard: dict[str, Any]) -> str:
    event = build_history_event(
        "dream-skipped",
        source={
            "kind": "dream-maintenance",
            "agent": "kb-dreamer",
            "run_id": run_id,
            "project_ref": repo_root.name,
            "workspace_root": str(repo_root),
        },
        target={
            "kind": "maintenance-run",
            "run_id": run_id,
        },
        rationale="Skipped dream mode because another core maintenance lane is still running or a legacy cooldown guard is active.",
        context={"sleep_guard": sleep_guard},
    )
    record_history_event(repo_root, event)
    return str(event["event_id"])


def run_dream_maintenance(
    repo_root: Path,
    *,
    run_id: str | None = None,
    max_events: int | None = None,
    sleep_cooldown_minutes: int = 0,
) -> dict[str, Any]:
    generated_at = utc_now_iso()
    resolved_run_id = sanitize_run_id(run_id or f"kb-dream-{utc_now_compact()}")
    run_dir = dream_run_dir(repo_root, resolved_run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    write_lane_status(repo_root, "kb-dream", "running", run_id=resolved_run_id)

    sleep_guard = build_sleep_guard(repo_root, cooldown_minutes=sleep_cooldown_minutes)
    plan_payload = {
        "schema_version": DREAM_SCHEMA_VERSION,
        "kind": "local-kb-dream-plan",
        "run_id": resolved_run_id,
        "generated_at": generated_at,
        "sleep_guard": sleep_guard,
    }
    write_json_file(run_dir / PLAN_FILENAME, plan_payload)

    if sleep_guard["blocked"]:
        skipped_event_id = _write_skip_event(repo_root, resolved_run_id, sleep_guard)
        write_lane_status(repo_root, "kb-dream", "skipped", run_id=resolved_run_id)
        result = {
            "schema_version": DREAM_SCHEMA_VERSION,
            "kind": DREAM_REPORT_KIND,
            "run_id": resolved_run_id,
            "generated_at": generated_at,
            "status": "skipped",
            "reason": "maintenance-lane-active" if sleep_guard["lane_guard"]["blocked"] else "recent-sleep-run",
            "sleep_guard": sleep_guard,
            "history_event_ids": [skipped_event_id],
            "artifact_paths": {
                "run_dir": relative_repo_path(repo_root, run_dir),
                "plan_path": relative_repo_path(repo_root, run_dir / PLAN_FILENAME),
                "report_path": relative_repo_path(repo_root, run_dir / REPORT_FILENAME),
            },
        }
        write_json_file(run_dir / REPORT_FILENAME, result)
        return result

    preflight = _build_dream_preflight(repo_root, run_id=resolved_run_id, generated_at=generated_at)
    write_json_file(run_dir / PREFLIGHT_FILENAME, preflight)
    plan_payload["preflight_path"] = relative_repo_path(repo_root, run_dir / PREFLIGHT_FILENAME)
    plan_payload["preflight_matched_entry_ids"] = list(preflight["matched_entry_ids"])
    plan_payload["preflight_matched_entry_count"] = int(preflight["matched_entry_count"])
    write_json_file(run_dir / PLAN_FILENAME, plan_payload)

    entries = load_entries(repo_root)
    history_events = load_history_events(repo_root, max_events=max_events)
    indexed_events = {event["event_id"]: event for event in history_events}
    consolidation = consolidate_history(
        repo_root=repo_root,
        run_id=f"{resolved_run_id}-source",
        max_events=max_events,
        apply_mode=APPLY_MODE_NONE,
    )
    opportunities = build_route_candidate_opportunities(consolidation["actions"], entries)
    opportunities.extend(build_taxonomy_gap_opportunities(repo_root, entries))
    opportunities.extend(build_entry_validation_opportunities(repo_root, entries))
    opportunities = _prepare_opportunities(opportunities)
    opportunities = sorted(
        opportunities,
        key=lambda item: (
            -int(bool(item.get("is_executable", False))),
            -_selection_priority(item),
            -int(item.get("executability_score", 0) or 0),
            -int(item["opportunity_score"]),
            item["kind"],
            item["route_ref"],
        ),
    )
    write_json_file(
        run_dir / OPPORTUNITIES_FILENAME,
        {
            "schema_version": DREAM_SCHEMA_VERSION,
            "kind": "local-kb-dream-opportunities",
            "run_id": resolved_run_id,
            "generated_at": generated_at,
            "opportunity_count": len(opportunities),
            "opportunities": opportunities,
        },
    )

    executable_opportunities = [item for item in opportunities if item.get("is_executable", False)]
    selected = executable_opportunities[:1]
    planned_experiments = [
        {
            "route_ref": item["route_ref"],
            "kind": item["kind"],
            "hypothesis": item["hypothesis"],
            "allowed_action_surface": item["allowed_action_surface"],
            "experiment_design": item["experiment_design"],
            "validation_plan": item["validation_plan"],
            "success_criteria": item["success_criteria"],
            "failure_criteria": item["failure_criteria"],
            "safety_tier": item["safety_tier"],
            "rollback_plan": item["rollback_plan"],
            "permitted_write_back": item["permitted_write_back"],
            "is_executable": item["is_executable"],
            "executability_score": item["executability_score"],
            "status": "planned",
        }
        for item in selected
    ]
    write_json_file(
        run_dir / EXPERIMENTS_FILENAME,
        {
            "schema_version": DREAM_SCHEMA_VERSION,
            "kind": "local-kb-dream-experiments",
            "run_id": resolved_run_id,
            "generated_at": generated_at,
            "experiment_count": len(planned_experiments),
            "experiments": planned_experiments,
        },
    )
    execution_plan = _build_execution_plan(
        repo_root,
        run_id=resolved_run_id,
        generated_at=generated_at,
        opportunity_count=len(opportunities),
        executable_opportunity_count=len(executable_opportunities),
        selected=selected,
    )
    write_json_file(run_dir / EXECUTION_PLAN_FILENAME, execution_plan)
    plan_payload["execution_plan_path"] = relative_repo_path(repo_root, run_dir / EXECUTION_PLAN_FILENAME)
    plan_payload["executable_opportunity_count"] = len(executable_opportunities)
    write_json_file(run_dir / PLAN_FILENAME, plan_payload)

    experiment_results: list[dict[str, Any]] = []
    created_candidates: list[dict[str, Any]] = []
    history_event_ids: list[str] = []

    for opportunity in selected:
        search_context = _search_context(
            repo_root,
            route_ref=opportunity["route_ref"],
            query=_validation_query(opportunity),
        )
        exact_coverage_exists = (
            opportunity["exact_route_entry_count"] > 0
            or search_context["exact_route_hit_count"] > 0
        )
        created_candidate: dict[str, Any] | None = None
        classification = "history-only"
        outcome = ""
        comment = ""

        if opportunity["kind"] == "route-candidate" and exact_coverage_exists:
            classification = "already-covered"
            outcome = f"Route {opportunity['route_title']} already has exact local coverage; no dream candidate was created."
            comment = "Dream validation found an exact route match, so this remained a history-only note."
        elif opportunity["kind"] == "route-candidate" and opportunity["candidate_creation_mode"] == "sleep-eligible":
            classification = "sleep-owned"
            outcome = (
                f"Route {opportunity['route_title']} is already eligible for sleep new-candidate apply; "
                "dream mode left candidate creation to sleep maintenance."
            )
            comment = "Dream mode did not duplicate a sleep-owned candidate action."
        elif opportunity["kind"] == "route-candidate" and opportunity["candidate_creation_mode"] == "dream-adjacent":
            if search_context["sibling_route_hit_count"] == 0:
                classification = "inconclusive"
                outcome = (
                    f"Route {opportunity['route_title']} still lacks exact coverage, but the dream validation "
                    "did not find enough adjacent search support for a scaffold."
                )
                comment = "Kept this run history-only because adjacent route support was weaker than expected."
            else:
                created_candidate, creation_reason = _create_dream_candidate(
                    repo_root,
                    action=opportunity["source_action"],
                    run_id=resolved_run_id,
                    generated_at=generated_at,
                    creation_mode=opportunity["candidate_creation_mode"],
                    indexed_events=indexed_events,
                )
                if created_candidate is not None:
                    classification = "candidate-created"
                    outcome = (
                        f"Created a bounded candidate scaffold for {opportunity['route_title']} via "
                        f"{opportunity['candidate_creation_mode']} validation."
                    )
                    comment = "Dream mode validated the route with local search and adjacent evidence before writing only to candidates."
                    created_candidates.append(created_candidate)
                else:
                    classification = "already-exists"
                    outcome = creation_reason
                    comment = "Dream mode skipped duplicate candidate creation and left a history note instead."
        elif opportunity["kind"] == "entry-validation":
            source_entry_id = str(opportunity.get("source_entry_id", "") or "unknown")
            if search_context["exact_route_hit_count"] > 0:
                classification = "validated"
                outcome = (
                    f"Validated existing card {source_entry_id} for {opportunity['route_title']} "
                    "with exact route-local retrieval evidence."
                )
                comment = "Dream mode treated this as read-only evidence for later sleep review."
            elif search_context["sibling_route_hit_count"] > 0:
                classification = "adjacent-support"
                outcome = (
                    f"Found adjacent support for existing card {source_entry_id}, but no exact route-local hit."
                )
                comment = "Kept this as history-only evidence because support was adjacent rather than exact."
            else:
                classification = "inconclusive"
                outcome = (
                    f"Validated existing card {source_entry_id}, but the local search did not find grounded support."
                )
                comment = "The experiment was executable, but its result should not strengthen the card."
        else:
            classification = "history-only"
            outcome = (
                f"Inspected {opportunity['route_title']} as a dream-mode opportunity and left the result in history only."
            )
            comment = "The route stayed provisional because dream mode did not have enough grounded evidence for a candidate scaffold."

        action_taken = (
            f"Ran a bounded dream validation for {opportunity['route_title']}: local search with path hint "
            f"{opportunity['route_ref']} and query '{search_context['query']}'."
        )
        observed_result = outcome
        if classification == "candidate-created":
            operational_use = (
                "Treat the dream-generated card as a candidate-only scaffold and wait for live-task confirmation "
                "before any promotion."
            )
        elif opportunity["kind"] == "taxonomy-gap":
            operational_use = "Use this result to drive later taxonomy review without changing trusted memory during dream mode."
        else:
            operational_use = "Keep this result in history and revisit the route during a later live task or sleep pass."
        reuse_judgment = (
            "Reusable when the same route keeps appearing without exact card coverage but nearby sibling routes suggest the gap is meaningful."
        )

        experiment = {
            "kind": opportunity["kind"],
            "route_ref": opportunity["route_ref"],
            "route_title": opportunity["route_title"],
            "hypothesis": opportunity["hypothesis"],
            "allowed_action_surface": opportunity["allowed_action_surface"],
            "experiment_design": opportunity["experiment_design"],
            "validation_plan": opportunity["validation_plan"],
            "success_criteria": opportunity["success_criteria"],
            "failure_criteria": opportunity["failure_criteria"],
            "safety_tier": opportunity["safety_tier"],
            "rollback_plan": opportunity["rollback_plan"],
            "permitted_write_back": opportunity["permitted_write_back"],
            "is_executable": opportunity["is_executable"],
            "executability_score": opportunity["executability_score"],
            "classification": classification,
            "search_context": search_context,
            "outcome": outcome,
            "comment": comment,
            "action_taken": action_taken,
            "observed_result": observed_result,
            "operational_use": operational_use,
            "reuse_judgment": reuse_judgment,
            "created_candidate": created_candidate,
        }
        observation_event_id = _record_dream_observation(
            repo_root,
            run_id=resolved_run_id,
            opportunity=opportunity,
            experiment=experiment,
            created_candidate=created_candidate,
        )
        experiment["history_event_id"] = observation_event_id
        history_event_ids.append(observation_event_id)
        experiment_results.append(experiment)

    if selected and experiment_results:
        classifications = ", ".join(sorted({item["classification"] for item in experiment_results}))
        _set_checkpoint_status(
            execution_plan,
            "validation",
            "completed",
            f"Validation completed with classifications: {classifications}.",
        )
        _set_checkpoint_status(
            execution_plan,
            "experiment-observation",
            "completed",
            f"Wrote {len(experiment_results)} route-specific experiment observation(s).",
        )

    run_observation_event_id = _record_dream_run_observation(
        repo_root,
        run_id=resolved_run_id,
        preflight=preflight,
        opportunity_count=len(opportunities),
        selected=selected,
        experiment_results=experiment_results,
        created_candidates=created_candidates,
    )
    history_event_ids.append(run_observation_event_id)
    _set_checkpoint_status(
        execution_plan,
        "run-observation",
        "completed",
        f"Wrote run-level Dream-process observation {run_observation_event_id}.",
    )
    _set_checkpoint_status(execution_plan, "report", "completed", "Report payload prepared.")
    execution_plan["status"] = "completed"
    execution_plan["completed_at"] = utc_now_iso()
    write_json_file(run_dir / EXECUTION_PLAN_FILENAME, execution_plan)

    write_json_file(
        run_dir / EXPERIMENTS_FILENAME,
        {
            "schema_version": DREAM_SCHEMA_VERSION,
            "kind": "local-kb-dream-experiments",
            "run_id": resolved_run_id,
            "generated_at": generated_at,
            "experiment_count": len(experiment_results),
            "experiments": experiment_results,
        },
    )

    result = {
        "schema_version": DREAM_SCHEMA_VERSION,
        "kind": DREAM_REPORT_KIND,
        "run_id": resolved_run_id,
        "generated_at": generated_at,
        "status": "completed",
        "sleep_guard": sleep_guard,
        "history_path": relative_repo_path(repo_root, history_events_path(repo_root)),
        "preflight": preflight,
        "execution_plan": execution_plan,
        "opportunity_count": len(opportunities),
        "executable_opportunity_count": len(executable_opportunities),
        "selected_experiment_count": len(selected),
        "created_candidate_count": len(created_candidates),
        "created_candidates": created_candidates,
        "history_event_ids": history_event_ids,
        "run_observation_event_id": run_observation_event_id,
        "experiments": experiment_results,
        "artifact_paths": {
            "run_dir": relative_repo_path(repo_root, run_dir),
            "plan_path": relative_repo_path(repo_root, run_dir / PLAN_FILENAME),
            "preflight_path": relative_repo_path(repo_root, run_dir / PREFLIGHT_FILENAME),
            "opportunities_path": relative_repo_path(repo_root, run_dir / OPPORTUNITIES_FILENAME),
            "experiments_path": relative_repo_path(repo_root, run_dir / EXPERIMENTS_FILENAME),
            "execution_plan_path": relative_repo_path(repo_root, run_dir / EXECUTION_PLAN_FILENAME),
            "report_path": relative_repo_path(repo_root, run_dir / REPORT_FILENAME),
        },
    }
    write_json_file(run_dir / REPORT_FILENAME, result)
    write_lane_status(repo_root, "kb-dream", "completed", run_id=resolved_run_id)
    return result
