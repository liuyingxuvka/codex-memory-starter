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
from local_kb.maintenance_lanes import acquire_lane_lock, build_lane_guard, release_lane_lock, write_lane_status
from local_kb.search import render_search_payload, search_entries, search_loaded_entries
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
SANDBOX_DIRNAME = "sandbox"
SANDBOX_MODE_RETRIEVAL_AB = "retrieval-ab"
SANDBOX_MODE_SCENARIO_REPLAY = "scenario-replay"
SANDBOX_EXPERIMENT_MODE = SANDBOX_MODE_RETRIEVAL_AB
DREAM_SANDBOX_EXPERIMENT_MODES = {SANDBOX_MODE_RETRIEVAL_AB, SANDBOX_MODE_SCENARIO_REPLAY}
DREAM_SLEEP_HANDOFF_CLASSIFICATIONS = {"validated", "adjacent-support", "candidate-backlog"}
DREAM_SLEEP_HANDOFF_EVIDENCE_GRADES = {"strong", "moderate"}

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

DREAM_MIN_VALUABLE_OPPORTUNITY_SCORE = 18
DREAM_MIN_VALUABLE_EXECUTABILITY_SCORE = 3
DREAM_MAX_SELECTED_EXPERIMENTS = 4


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def dream_run_dir(repo_root: Path, run_id: str) -> Path:
    return repo_root / "kb" / "history" / "dream" / run_id


def dream_sandbox_dir(repo_root: Path, run_id: str) -> Path:
    return dream_run_dir(repo_root, run_id) / SANDBOX_DIRNAME


def _load_prior_successful_sandbox_keys(repo_root: Path, *, current_run_id: str) -> dict[str, dict[str, Any]]:
    dream_root = repo_root / "kb" / "history" / "dream"
    if not dream_root.exists():
        return {}

    prior: dict[str, dict[str, Any]] = {}
    for report_path in sorted(dream_root.glob(f"*/{REPORT_FILENAME}")):
        run_id = report_path.parent.name
        if run_id == current_run_id:
            continue
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for experiment in payload.get("experiments", []):
            if not isinstance(experiment, dict):
                continue
            sandbox_mode = str(experiment.get("sandbox_mode", "") or "")
            if sandbox_mode not in DREAM_SANDBOX_EXPERIMENT_MODES:
                continue
            validation = experiment.get("validation_result", {})
            status = str(validation.get("status", "") or "") if isinstance(validation, dict) else ""
            grade = str(experiment.get("evidence_grade", "") or "")
            if status != "passed" or grade not in {"strong", "moderate"}:
                continue
            key = _opportunity_batch_key(experiment)
            prior[key] = {
                "run_id": run_id,
                "route_ref": str(experiment.get("route_ref", "") or ""),
                "kind": str(experiment.get("kind", "") or ""),
                "sandbox_mode": sandbox_mode,
                "evidence_grade": grade,
                "validation_status": status,
                "sandbox_path": str(experiment.get("sandbox_path", "") or ""),
            }
    return prior


def build_dream_guard(repo_root: Path) -> dict[str, Any]:
    return build_lane_guard(repo_root, "kb-dream")


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


def _sibling_route_status_counts(entries: list[Any], route: list[str]) -> dict[str, int]:
    if not route:
        return {}
    parent = route[:-1]
    counts: dict[str, int] = {}
    for entry in entries:
        entry_route = _entry_route(entry)
        if len(entry_route) != len(route):
            continue
        if entry_route == route:
            continue
        if entry_route[:-1] != parent:
            continue
        status = str(entry.data.get("status", "") or "").strip().lower() or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


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
            return 3
        if mode == "sleep-eligible":
            return 1
        if mode == "candidate-backlog":
            return 1
    if opportunity.get("kind") == "entry-validation":
        return 4
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


def _block_text(value: Any, preferred_keys: tuple[str, ...] = ()) -> str:
    if isinstance(value, dict):
        parts: list[str] = []
        keys = preferred_keys or tuple(value.keys())
        for key in keys:
            item = value.get(key, "")
            if isinstance(item, (dict, list)):
                item_text = _block_text(item)
            else:
                item_text = str(item or "").strip()
            if item_text:
                parts.append(item_text)
        return " ".join(parts).strip()
    if isinstance(value, list):
        return " ".join(_block_text(item) for item in value if _block_text(item)).strip()
    return str(value or "").strip()


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
        sibling_status_counts = _sibling_route_status_counts(entries, route)
        sibling_candidate_count = int(sibling_status_counts.get("candidate", 0) or 0)
        sibling_trusted_count = int(sibling_status_counts.get("trusted", 0) or 0)
        predictive_preview = _predictive_preview_available(action)
        event_count = int(action.get("event_count", 0) or 0)
        task_summaries = list(action.get("task_summaries", []))
        apply_eligibility = action.get("apply_eligibility", {})
        if not isinstance(apply_eligibility, dict):
            apply_eligibility = {}

        candidate_creation_mode = ""
        if exact_route_entry_count == 0 and len(route) >= 3:
            if predictive_preview and sibling_candidate_count > 0 and sibling_trusted_count == 0:
                candidate_creation_mode = "candidate-backlog"
            elif apply_eligibility.get("eligible", False):
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
                "sibling_status_counts": sibling_status_counts,
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
                "source_entry_title": str(data.get("title", "") or "").strip(),
                "source_entry_scenario": _block_text(data.get("if", {}), ("notes", "scenario", "conditions")),
                "source_entry_action": _block_text(data.get("action", {}), ("description", "action")),
                "source_entry_predicted_result": _block_text(data.get("predict", {}), ("expected_result", "result")),
                "source_entry_guidance": _block_text(data.get("use", {}), ("guidance", "notes")),
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
    elif kind == "route-candidate" and mode == "candidate-backlog":
        safety_tier = "read-only"
        experiment_design = "Confirm that adjacent candidate backlog already represents the route family, then leave a Sleep handoff instead of creating another candidate."
        validation_plan = "Search the target route, inspect adjacent candidate hits, and classify the result as candidate-backlog when route coverage is missing but nearby candidate scaffolds already exist."
        rollback_plan = "No rollback needed because the experiment writes no files beyond append-only history."
        permitted_write_back = "history-only"
    elif kind == "route-candidate" and mode == "sleep-eligible":
        safety_tier = "read-only"
        experiment_design = "Confirm that this route is already owned by sleep maintenance rather than duplicating candidate creation."
        validation_plan = "Inspect consolidation ownership and route-local search output, then write only a history note."
        rollback_plan = "No rollback needed because the experiment writes no files beyond append-only history."
        permitted_write_back = "history-only"
    elif kind == "entry-validation":
        safety_tier = "read-only"
        experiment_design = "Replay a historical or card-derived task scenario with and without the tested candidate or low-confidence card in local search."
        validation_plan = "Compare the no-tested-card baseline against candidate-augmented retrieval, then decide whether the card improves task choice or is ready for Sleep semantic review."
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
                "experiment-selection",
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


def _is_valuable_experiment(opportunity: dict[str, Any]) -> bool:
    if not opportunity.get("is_executable", False):
        return False
    kind = str(opportunity.get("kind", "") or "")
    if kind == "taxonomy-gap" and opportunity.get("exact_route_entry_count", 0):
        return True

    opportunity_score = int(opportunity.get("opportunity_score", 0) or 0)
    executability_score = int(opportunity.get("executability_score", 0) or 0)
    if opportunity_score < DREAM_MIN_VALUABLE_OPPORTUNITY_SCORE:
        return False
    if executability_score < DREAM_MIN_VALUABLE_EXECUTABILITY_SCORE:
        return False

    if kind == "route-candidate":
        mode = str(opportunity.get("candidate_creation_mode", "") or "")
        return mode in {"dream-adjacent", "candidate-backlog"}
    return kind in {"entry-validation", "taxonomy-gap"}


def _sandbox_mode_for_opportunity(opportunity: dict[str, Any]) -> str:
    explicit_mode = str(opportunity.get("sandbox_mode", "") or "").strip()
    if explicit_mode in DREAM_SANDBOX_EXPERIMENT_MODES:
        return explicit_mode
    if str(opportunity.get("kind", "") or "") == "entry-validation":
        return SANDBOX_MODE_SCENARIO_REPLAY
    return SANDBOX_MODE_RETRIEVAL_AB


def _opportunity_batch_key(opportunity: dict[str, Any]) -> str:
    kind = str(opportunity.get("kind", "") or "")
    route_ref = str(opportunity.get("route_ref", "") or "")
    sandbox_mode = _sandbox_mode_for_opportunity(opportunity)
    if kind == "entry-validation":
        return f"{kind}:{sandbox_mode}:{route_ref}"
    if kind == "route-candidate":
        mode = str(opportunity.get("candidate_creation_mode", "") or "")
        return f"{kind}:{sandbox_mode}:{mode}:{route_ref}"
    return f"{kind}:{sandbox_mode}:{route_ref}"


def _select_valuable_experiments(
    opportunities: list[dict[str, Any]],
    *,
    prior_successful_sandbox_keys: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    prior_successful_sandbox_keys = prior_successful_sandbox_keys or {}
    selected: list[dict[str, Any]] = []
    seen_batch_keys: set[str] = set()
    for opportunity in opportunities:
        if not opportunity.get("is_executable", False):
            continue
        if not _is_valuable_experiment(opportunity):
            continue
        batch_key = _opportunity_batch_key(opportunity)
        if batch_key in seen_batch_keys:
            continue
        if batch_key in prior_successful_sandbox_keys:
            opportunity["selection_status"] = "skipped-prior-sandbox-success"
            opportunity["prior_sandbox_success"] = prior_successful_sandbox_keys[batch_key]
            continue
        seen_batch_keys.add(batch_key)
        selected.append(opportunity)
        if len(selected) >= DREAM_MAX_SELECTED_EXPERIMENTS:
            break
    return selected


def _selected_experiment_plan(item: dict[str, Any], sequence_index: int) -> dict[str, Any]:
    sandbox_mode = _sandbox_mode_for_opportunity(item)
    return {
        "sequence_index": sequence_index,
        "route_ref": item["route_ref"],
        "kind": item["kind"],
        "candidate_creation_mode": str(item.get("candidate_creation_mode", "") or ""),
        "hypothesis": item["hypothesis"],
        "experiment_design": item["experiment_design"],
        "validation_plan": item["validation_plan"],
        "success_criteria": item["success_criteria"],
        "failure_criteria": item["failure_criteria"],
        "safety_tier": item["safety_tier"],
        "rollback_plan": item["rollback_plan"],
        "permitted_write_back": item["permitted_write_back"],
        "sandbox_mode": sandbox_mode,
        "opportunity_score": item["opportunity_score"],
        "executability_score": item["executability_score"],
    }


def _validation_query(opportunity: dict[str, Any]) -> str:
    validation_query = str(opportunity.get("validation_query", "") or "").strip()
    if validation_query:
        return validation_query
    task_summaries = [str(item or "").strip() for item in opportunity.get("task_summaries", []) if str(item or "").strip()]
    if task_summaries:
        return " ".join(task_summaries[:2])
    return opportunity.get("route_title", "route exploration")


def _search_context_from_results(route_ref: str, query: str, search_results: list[dict[str, Any]]) -> dict[str, Any]:
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


def _search_context_from_entries(repo_root: Path, entries: list[Any], route_ref: str, query: str) -> dict[str, Any]:
    search_results = render_search_payload(
        search_loaded_entries(entries, query=query, path_hint=route_ref, top_k=5),
        repo_root,
    )
    return _search_context_from_results(route_ref, query, search_results)


def _search_context(repo_root: Path, route_ref: str, query: str) -> dict[str, Any]:
    search_results = render_search_payload(
        search_entries(repo_root, query=query, path_hint=route_ref, top_k=5),
        repo_root,
    )
    return _search_context_from_results(route_ref, query, search_results)


def _sandbox_allowed_writes(repo_root: Path, run_id: str) -> list[str]:
    return [f"{relative_repo_path(repo_root, dream_sandbox_dir(repo_root, run_id))}/"]


def _sandbox_evidence_grade(search_context: dict[str, Any], comparison_context: dict[str, Any]) -> str:
    exact_hits = int(search_context.get("exact_route_hit_count", 0) or 0)
    sibling_hits = int(search_context.get("sibling_route_hit_count", 0) or 0)
    comparison_exact_hits = int(comparison_context.get("exact_route_hit_count", 0) or 0)
    comparison_sibling_hits = int(comparison_context.get("sibling_route_hit_count", 0) or 0)
    result_count = int(search_context.get("result_count", 0) or 0)
    comparison_result_count = int(comparison_context.get("result_count", 0) or 0)

    if exact_hits or comparison_exact_hits:
        return "strong"
    if sibling_hits or comparison_sibling_hits:
        return "moderate"
    if result_count or comparison_result_count:
        return "weak"
    return "none"


def _sandbox_validation_status(evidence_grade: str) -> str:
    if evidence_grade in {"strong", "moderate"}:
        return "passed"
    if evidence_grade == "weak":
        return "inconclusive"
    return "failed"


def _sandbox_handoff(opportunity: dict[str, Any], classification: str, evidence_grade: str) -> dict[str, str]:
    kind = str(opportunity.get("kind", "") or "")
    route_title = str(opportunity.get("route_title", "") or "the route")
    if classification == "candidate-created":
        sleep = f"Sleep should review the dream-created candidate for {route_title} only after later live-task evidence confirms it."
    elif classification == "candidate-backlog":
        sleep = f"Sleep should use this sandbox evidence to merge, reject, narrow, or keep watching nearby candidates for {route_title}."
    elif classification in {"validated", "adjacent-support"}:
        sleep = f"Sleep should use this {evidence_grade} sandbox evidence when deciding whether the existing candidate for {route_title} should stay watched or be strengthened."
    elif kind == "taxonomy-gap":
        sleep = f"Sleep should keep the taxonomy-gap evidence for {route_title} history-only unless the same gap repeats."
    else:
        sleep = f"Sleep should keep {route_title} history-only unless later task evidence repeats the signal."

    architect = (
        "No Architect action from this sandbox result unless repeated evidence points to a prompt, "
        "automation, installer, rollback, or tooling mechanism issue."
    )
    return {
        "sleep": sleep,
        "architect": architect,
    }


def _summarize_search_variant(name: str, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "query": context["query"],
        "path_hint": context["path_hint"],
        "result_count": context["result_count"],
        "exact_route_hit_count": context["exact_route_hit_count"],
        "sibling_route_hit_count": context["sibling_route_hit_count"],
        "result_ids": [
            str(item.get("id", "") or "")
            for item in context.get("results", [])
            if str(item.get("id", "") or "").strip()
        ],
    }


def _search_result_rank(context: dict[str, Any], entry_id: str) -> int:
    if not entry_id:
        return 0
    for index, item in enumerate(context.get("results", []), start=1):
        if str(item.get("id", "") or "") == entry_id:
            return index
    return 0


def _top_choice_summary(context: dict[str, Any]) -> str:
    results = context.get("results", [])
    if not results:
        return "No local KB choice was returned."
    top = results[0]
    entry_id = str(top.get("id", "") or "unknown")
    route = "/".join(parse_route_segments(top.get("domain_path", []))) or "unrouted"
    status = str(top.get("status", "") or "unknown")
    return f"Top choice was {entry_id} on {route} with status {status}."


def _candidate_card_snapshot(opportunity: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_id": str(opportunity.get("source_entry_id", "") or ""),
        "title": str(opportunity.get("source_entry_title", "") or ""),
        "entry_status": str(opportunity.get("entry_status", "") or ""),
        "entry_confidence": opportunity.get("entry_confidence", ""),
        "entry_path": str(opportunity.get("source_entry_path", "") or ""),
        "route_ref": str(opportunity.get("route_ref", "") or ""),
        "scenario": str(opportunity.get("source_entry_scenario", "") or ""),
        "action": str(opportunity.get("source_entry_action", "") or ""),
        "predicted_result": str(opportunity.get("source_entry_predicted_result", "") or ""),
        "guidance": str(opportunity.get("source_entry_guidance", "") or ""),
    }


def _event_route_ref(event: dict[str, Any]) -> str:
    target = event.get("target", {}) if isinstance(event.get("target"), dict) else {}
    route = parse_route_segments(target.get("route_hint", []))
    return "/".join(route)


def _matching_history_scenarios(
    history_events: list[dict[str, Any]],
    *,
    route_ref: str,
    source_entry_id: str,
    limit: int = 3,
) -> list[dict[str, str]]:
    route = parse_route_segments(route_ref)
    matched: list[dict[str, str]] = []
    for event in reversed(history_events):
        if not isinstance(event, dict):
            continue
        target = event.get("target", {}) if isinstance(event.get("target"), dict) else {}
        event_route = parse_route_segments(target.get("route_hint", []))
        entry_ids = [str(item) for item in target.get("entry_ids", [])] if isinstance(target.get("entry_ids", []), list) else []
        if source_entry_id not in entry_ids and event_route != route:
            continue
        context = event.get("context", {}) if isinstance(event.get("context"), dict) else {}
        predictive = context.get("predictive_observation", {}) if isinstance(context.get("predictive_observation"), dict) else {}
        matched.append(
            {
                "event_id": str(event.get("event_id", "") or ""),
                "route_ref": _event_route_ref(event),
                "task_summary": str(target.get("task_summary", "") or ""),
                "scenario": str(predictive.get("scenario", "") or ""),
                "action_taken": str(predictive.get("action_taken", "") or ""),
                "observed_result": str(predictive.get("observed_result", "") or ""),
                "suggested_action": str(context.get("suggested_action", "") or ""),
            }
        )
        if len(matched) >= limit:
            break
    return list(reversed(matched))


def _scenario_replay_query(opportunity: dict[str, Any], history_scenarios: list[dict[str, str]]) -> str:
    candidate = _candidate_card_snapshot(opportunity)
    history_text = " ".join(
        part
        for scenario in history_scenarios[:2]
        for part in (
            scenario.get("task_summary", ""),
            scenario.get("scenario", ""),
            scenario.get("action_taken", ""),
        )
        if str(part or "").strip()
    )
    candidate_text = " ".join(
        str(candidate.get(key, "") or "").strip()
        for key in ("title", "scenario", "action", "predicted_result", "guidance")
        if str(candidate.get(key, "") or "").strip()
    )
    return history_text or candidate_text or _validation_query(opportunity)


def _scenario_replay_decision(
    *,
    opportunity: dict[str, Any],
    baseline_context: dict[str, Any],
    candidate_context: dict[str, Any],
    history_scenarios: list[dict[str, str]],
) -> dict[str, Any]:
    source_entry_id = str(opportunity.get("source_entry_id", "") or "")
    candidate_rank = _search_result_rank(candidate_context, source_entry_id)
    baseline_exact_hits = int(baseline_context.get("exact_route_hit_count", 0) or 0)
    candidate_exact_hits = int(candidate_context.get("exact_route_hit_count", 0) or 0)
    scenario_count = len(history_scenarios)
    candidate_snapshot = _candidate_card_snapshot(opportunity)
    if any(str(candidate_snapshot.get(key, "") or "").strip() for key in ("scenario", "action", "predicted_result")):
        scenario_count += 1

    candidate_improves_choice = bool(candidate_rank and baseline_exact_hits == 0)
    candidate_competes_for_choice = bool(candidate_rank and candidate_rank <= 3)
    if candidate_improves_choice and candidate_rank == 1 and scenario_count:
        evidence_grade = "strong"
    elif candidate_improves_choice or candidate_competes_for_choice:
        evidence_grade = "moderate"
    elif candidate_rank:
        evidence_grade = "weak"
    else:
        evidence_grade = "none"
    validation_status = _sandbox_validation_status(evidence_grade)

    if candidate_improves_choice:
        next_step = (
            "semantic-review the tested candidate for strengthening, narrowing, or promotion only if later "
            "real-task evidence agrees; the replay shows it fills a task-choice gap."
        )
    elif candidate_competes_for_choice:
        next_step = (
            "semantic-review the tested candidate against the existing top choice and decide whether Sleep "
            "should merge, narrow, rewrite, or keep watching it."
        )
    elif candidate_rank:
        next_step = "keep watching the tested candidate; it appeared in replay but did not materially change the task choice."
    else:
        next_step = "do not strengthen the tested candidate from this replay; consider rewrite or rejection if later evidence stays weak."

    baseline_summary = _top_choice_summary(baseline_context)
    candidate_summary = (
        f"Tested candidate {source_entry_id or 'unknown'} ranked #{candidate_rank}."
        if candidate_rank
        else f"Tested candidate {source_entry_id or 'unknown'} did not appear in the top replay results."
    )
    reason = (
        f"Scenario replay graded {evidence_grade}: baseline exact route hits={baseline_exact_hits}, "
        f"candidate-augmented exact route hits={candidate_exact_hits}, candidate rank={candidate_rank or 'not ranked'}."
    )
    return {
        "candidate_entry_id": source_entry_id,
        "candidate_rank": candidate_rank,
        "baseline_exact_route_hit_count": baseline_exact_hits,
        "candidate_augmented_exact_route_hit_count": candidate_exact_hits,
        "candidate_improves_task_choice": candidate_improves_choice,
        "candidate_competes_for_task_choice": candidate_competes_for_choice,
        "sleep_review_ready": validation_status == "passed",
        "evidence_grade": evidence_grade,
        "validation_status": validation_status,
        "baseline_summary": baseline_summary,
        "candidate_summary": candidate_summary,
        "reason": reason,
        "sleep_next_step": next_step,
    }


def _scenario_replay_handoff(opportunity: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    route_title = str(opportunity.get("route_title", "") or "the route")
    source_entry_id = str(opportunity.get("source_entry_id", "") or "the tested card")
    rank_value = decision.get("candidate_rank") or 0
    rank_text = f"#{rank_value}" if rank_value else "not ranked"
    sleep = (
        f"Sleep should inspect scenario-replay for {source_entry_id} on {route_title}: candidate rank {rank_text}, "
        f"baseline exact hits={decision.get('baseline_exact_route_hit_count', 0)}, "
        f"candidate exact hits={decision.get('candidate_augmented_exact_route_hit_count', 0)}. "
        f"Next step: {decision.get('sleep_next_step', '')}"
    )
    architect = (
        "No Architect action from this scenario replay unless repeated replays show Dream selection, search scoring, "
        "or sandbox reporting needs a mechanism change."
    )
    return {
        "sleep": sleep,
        "architect": architect,
        "detail": {
            "candidate_entry_id": source_entry_id,
            "route_ref": str(opportunity.get("route_ref", "") or ""),
            "candidate_rank": decision.get("candidate_rank", 0),
            "candidate_improves_task_choice": bool(decision.get("candidate_improves_task_choice", False)),
            "candidate_competes_for_task_choice": bool(decision.get("candidate_competes_for_task_choice", False)),
            "sleep_review_ready": bool(decision.get("sleep_review_ready", False)),
            "sleep_next_step": str(decision.get("sleep_next_step", "") or ""),
            "baseline_summary": str(decision.get("baseline_summary", "") or ""),
            "candidate_summary": str(decision.get("candidate_summary", "") or ""),
        },
    }


def _run_retrieval_ab_sandbox(
    repo_root: Path,
    *,
    run_id: str,
    generated_at: str,
    sequence_index: int,
    opportunity: dict[str, Any],
    search_context: dict[str, Any],
    classification: str,
) -> dict[str, Any]:
    route = parse_route_segments(opportunity.get("route_ref", ""))
    comparison_route_ref = "/".join(route[:-1]) if len(route) > 1 else str(opportunity.get("route_ref", "") or "")
    comparison_context = _search_context(
        repo_root,
        route_ref=comparison_route_ref,
        query=str(search_context.get("query", "") or _validation_query(opportunity)),
    )
    evidence_grade = _sandbox_evidence_grade(search_context, comparison_context)
    validation_status = _sandbox_validation_status(evidence_grade)
    handoff = _sandbox_handoff(opportunity, classification, evidence_grade)
    sandbox_dir = dream_sandbox_dir(repo_root, run_id)
    sandbox_path = sandbox_dir / f"experiment-{sequence_index:03d}-{SANDBOX_EXPERIMENT_MODE}.json"
    relative_sandbox_path = relative_repo_path(repo_root, sandbox_path)
    validation_result = {
        "status": validation_status,
        "classification": classification,
        "summary": (
            f"Retrieval A/B evidence for {opportunity['route_title']} was graded {evidence_grade} "
            f"from target-route and comparison-route local search variants."
        ),
    }
    payload = {
        "schema_version": DREAM_SCHEMA_VERSION,
        "kind": "local-kb-dream-sandbox-experiment",
        "run_id": run_id,
        "generated_at": generated_at,
        "sequence_index": sequence_index,
        "sandbox_mode": SANDBOX_EXPERIMENT_MODE,
        "route_ref": opportunity["route_ref"],
        "source_entry_id": str(opportunity.get("source_entry_id", "") or ""),
        "hypothesis": opportunity["hypothesis"],
        "allowed_writes": _sandbox_allowed_writes(repo_root, run_id),
        "trusted_card_mutation": False,
        "variants": [
            _summarize_search_variant("target-route", search_context),
            _summarize_search_variant("comparison-route", comparison_context),
        ],
        "evidence_grade": evidence_grade,
        "validation_result": validation_result,
        "sleep_handoff": handoff["sleep"],
        "architect_handoff": handoff["architect"],
        "sandbox_path": relative_sandbox_path,
    }
    write_json_file(sandbox_path, payload)
    return {
        "sandbox_mode": SANDBOX_EXPERIMENT_MODE,
        "sandbox_path": relative_sandbox_path,
        "source_entry_id": payload["source_entry_id"],
        "allowed_writes": payload["allowed_writes"],
        "evidence_grade": evidence_grade,
        "validation_result": validation_result,
        "sleep_handoff": handoff["sleep"],
        "architect_handoff": handoff["architect"],
    }


def _run_scenario_replay_sandbox(
    repo_root: Path,
    *,
    run_id: str,
    generated_at: str,
    sequence_index: int,
    opportunity: dict[str, Any],
    classification: str,
    history_events: list[dict[str, Any]],
) -> dict[str, Any]:
    source_entry_id = str(opportunity.get("source_entry_id", "") or "")
    route_ref = str(opportunity.get("route_ref", "") or "")
    history_scenarios = _matching_history_scenarios(
        history_events,
        route_ref=route_ref,
        source_entry_id=source_entry_id,
    )
    replay_query = _scenario_replay_query(opportunity, history_scenarios)
    all_entries = load_entries(repo_root)
    baseline_entries = [
        entry
        for entry in all_entries
        if str(entry.data.get("id", "") or "").strip() != source_entry_id
    ]
    baseline_context = _search_context_from_entries(
        repo_root,
        baseline_entries,
        route_ref=route_ref,
        query=replay_query,
    )
    candidate_context = _search_context_from_entries(
        repo_root,
        all_entries,
        route_ref=route_ref,
        query=replay_query,
    )
    decision = _scenario_replay_decision(
        opportunity=opportunity,
        baseline_context=baseline_context,
        candidate_context=candidate_context,
        history_scenarios=history_scenarios,
    )
    evidence_grade = str(decision["evidence_grade"])
    validation_status = str(decision["validation_status"])
    handoff = _scenario_replay_handoff(opportunity, decision)
    sandbox_dir = dream_sandbox_dir(repo_root, run_id)
    sandbox_mode = SANDBOX_MODE_SCENARIO_REPLAY
    sandbox_path = sandbox_dir / f"experiment-{sequence_index:03d}-{sandbox_mode}.json"
    relative_sandbox_path = relative_repo_path(repo_root, sandbox_path)
    validation_result = {
        "status": validation_status,
        "classification": classification,
        "summary": (
            f"Scenario replay for {opportunity['route_title']} was graded {evidence_grade}: "
            f"{decision['reason']}"
        ),
    }
    scenario_replay = {
        "replay_query": replay_query,
        "candidate_card": _candidate_card_snapshot(opportunity),
        "historical_scenarios": history_scenarios,
        "baseline_without_tested_card": _summarize_search_variant("without-tested-card", baseline_context),
        "with_tested_card": _summarize_search_variant("with-tested-card", candidate_context),
        "decision_delta": decision,
    }
    payload = {
        "schema_version": DREAM_SCHEMA_VERSION,
        "kind": "local-kb-dream-sandbox-experiment",
        "run_id": run_id,
        "generated_at": generated_at,
        "sequence_index": sequence_index,
        "sandbox_mode": sandbox_mode,
        "route_ref": route_ref,
        "source_entry_id": source_entry_id,
        "hypothesis": opportunity["hypothesis"],
        "allowed_writes": _sandbox_allowed_writes(repo_root, run_id),
        "trusted_card_mutation": False,
        "variants": [
            scenario_replay["baseline_without_tested_card"],
            scenario_replay["with_tested_card"],
        ],
        "scenario_replay": scenario_replay,
        "evidence_grade": evidence_grade,
        "validation_result": validation_result,
        "sleep_handoff": handoff["sleep"],
        "sleep_handoff_detail": handoff["detail"],
        "architect_handoff": handoff["architect"],
        "sandbox_path": relative_sandbox_path,
    }
    write_json_file(sandbox_path, payload)
    return {
        "sandbox_mode": sandbox_mode,
        "sandbox_path": relative_sandbox_path,
        "source_entry_id": source_entry_id,
        "allowed_writes": payload["allowed_writes"],
        "evidence_grade": evidence_grade,
        "validation_result": validation_result,
        "sleep_handoff": handoff["sleep"],
        "sleep_handoff_detail": handoff["detail"],
        "architect_handoff": handoff["architect"],
        "scenario_replay": scenario_replay,
        "previous_action": "Replay the task scenario without the tested card available in local search.",
        "previous_result": decision["baseline_summary"],
        "revised_action": "Replay the same scenario with the tested card available in local search.",
        "revised_result": decision["candidate_summary"],
    }


def _run_dream_sandbox(
    repo_root: Path,
    *,
    run_id: str,
    generated_at: str,
    sequence_index: int,
    opportunity: dict[str, Any],
    search_context: dict[str, Any],
    classification: str,
    history_events: list[dict[str, Any]],
) -> dict[str, Any]:
    if _sandbox_mode_for_opportunity(opportunity) == SANDBOX_MODE_SCENARIO_REPLAY:
        return _run_scenario_replay_sandbox(
            repo_root,
            run_id=run_id,
            generated_at=generated_at,
            sequence_index=sequence_index,
            opportunity=opportunity,
            classification=classification,
            history_events=history_events,
        )
    return _run_retrieval_ab_sandbox(
        repo_root,
        run_id=run_id,
        generated_at=generated_at,
        sequence_index=sequence_index,
        opportunity=opportunity,
        search_context=search_context,
        classification=classification,
    )


def _entry_ids_from_search_results(search_context: dict[str, Any]) -> list[str]:
    entry_ids: list[str] = []
    seen: set[str] = set()
    for result in search_context.get("results", []):
        if not isinstance(result, dict):
            continue
        entry_id = str(result.get("id", "") or "").strip()
        if not entry_id or entry_id in seen:
            continue
        seen.add(entry_id)
        entry_ids.append(entry_id)
    return entry_ids


def _dream_handoff_entry_ids(
    opportunity: dict[str, Any],
    experiment: dict[str, Any],
    created_candidate: dict[str, Any] | None,
) -> list[str]:
    if created_candidate is not None:
        return [str(created_candidate["entry_id"])]

    if opportunity.get("kind") == "entry-validation":
        source_entry_id = str(opportunity.get("source_entry_id", "") or "").strip()
        return [source_entry_id] if source_entry_id else []

    if experiment.get("classification") == "candidate-backlog":
        search_context = experiment.get("search_context", {})
        if isinstance(search_context, dict):
            return _entry_ids_from_search_results(search_context)

    return []


def _dream_suggested_action(
    opportunity: dict[str, Any],
    experiment: dict[str, Any],
    created_candidate: dict[str, Any] | None,
    entry_ids: list[str],
) -> str:
    if created_candidate is not None:
        return "new-candidate"
    if opportunity["kind"] == "taxonomy-gap":
        return "taxonomy-change"

    classification = str(experiment.get("classification", "") or "")
    evidence_grade = str(experiment.get("evidence_grade", "") or "")
    validation_result = experiment.get("validation_result", {})
    if not isinstance(validation_result, dict):
        validation_result = {}
    validation_status = str(validation_result.get("status", "") or "")
    if (
        classification in DREAM_SLEEP_HANDOFF_CLASSIFICATIONS
        and evidence_grade in DREAM_SLEEP_HANDOFF_EVIDENCE_GRADES
        and validation_status == "passed"
        and entry_ids
    ):
        return "update-card"
    return "none"


def _dream_validation_context(
    *,
    run_id: str,
    opportunity: dict[str, Any],
    experiment: dict[str, Any],
    entry_ids: list[str],
    suggested_action: str,
) -> dict[str, Any]:
    validation_result = experiment.get("validation_result", {})
    if not isinstance(validation_result, dict):
        validation_result = {}
    context = {
        "run_id": run_id,
        "opportunity_kind": str(opportunity.get("kind", "") or ""),
        "classification": str(experiment.get("classification", "") or ""),
        "evidence_grade": str(experiment.get("evidence_grade", "") or ""),
        "validation_status": str(validation_result.get("status", "") or ""),
        "sandbox_mode": str(experiment.get("sandbox_mode", "") or ""),
        "sandbox_path": str(experiment.get("sandbox_path", "") or ""),
        "source_entry_id": str(opportunity.get("source_entry_id", "") or ""),
        "entry_status": str(opportunity.get("entry_status", "") or ""),
        "entry_confidence": opportunity.get("entry_confidence", ""),
        "entry_ids": entry_ids,
        "trusted_card_mutation": False,
        "sleep_handoff": str(experiment.get("sleep_handoff", "") or ""),
        "architect_handoff": str(experiment.get("architect_handoff", "") or ""),
        "handoff_action": suggested_action,
    }
    sleep_handoff_detail = experiment.get("sleep_handoff_detail", {})
    if isinstance(sleep_handoff_detail, dict) and sleep_handoff_detail:
        context["sleep_handoff_detail"] = sleep_handoff_detail
    scenario_replay = experiment.get("scenario_replay", {})
    if isinstance(scenario_replay, dict) and scenario_replay:
        context["scenario_replay"] = {
            "replay_query": str(scenario_replay.get("replay_query", "") or ""),
            "decision_delta": scenario_replay.get("decision_delta", {}),
        }
    return context


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
    handoff_entry_ids = _dream_handoff_entry_ids(
        opportunity=opportunity,
        experiment=experiment,
        created_candidate=created_candidate,
    )
    suggested_action = _dream_suggested_action(
        opportunity=opportunity,
        experiment=experiment,
        created_candidate=created_candidate,
        entry_ids=handoff_entry_ids,
    )
    route_ref = str(opportunity.get("route_ref", "") or "")
    entry_ids = ",".join(handoff_entry_ids)
    outcome = str(experiment.get("outcome", "") or "")
    comment = str(experiment.get("comment", "") or "")
    scenario = str(opportunity.get("hypothesis", "") or "")
    action_taken = str(experiment.get("action_taken", "") or "")
    observed_result = str(experiment.get("observed_result", "") or "")
    previous_action = str(experiment.get("previous_action", "") or "")
    previous_result = str(experiment.get("previous_result", "") or "")
    revised_action = str(experiment.get("revised_action", "") or "")
    revised_result = str(experiment.get("revised_result", "") or "")
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
        previous_action=previous_action,
        previous_result=previous_result,
        revised_action=revised_action,
        revised_result=revised_result,
        operational_use=operational_use,
        reuse_judgment=reuse_judgment,
        source_kind="dream-maintenance",
        agent_name="kb-dreamer",
        thread_ref=f"dream-run::{run_id}",
        project_ref=repo_root.name,
        workspace_root=str(repo_root),
    )
    observation["context"]["dream_validation"] = _dream_validation_context(
        run_id=run_id,
        opportunity=opportunity,
        experiment=experiment,
        entry_ids=handoff_entry_ids,
        suggested_action=suggested_action,
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
    skipped_prior_sandbox_success_count: int = 0,
) -> dict[str, Any]:
    selected_experiments = [
        _selected_experiment_plan(item, sequence_index)
        for sequence_index, item in enumerate(selected, start=1)
    ]
    selected_experiment = selected_experiments[0] if selected_experiments else None

    selection_status = "completed"
    selection_details = (
        f"Selected {len(selected)} valuable executable experiment(s) for sequential validation."
        if selected
        else "No valuable executable experiment was selected; no-op is a valid Dream outcome."
    )
    return {
        "schema_version": DREAM_SCHEMA_VERSION,
        "kind": "local-kb-dream-execution-plan",
        "run_id": run_id,
        "generated_at": generated_at,
        "status": "running",
        "policy": {
            "selection_rule": "Select a bounded batch of valuable executable experiments for sequential validation; report a no-op when no opportunity clears the value gate.",
            "allowed_safety_tiers": ["read-only", "workspace-only"],
            "minimum_opportunity_score": DREAM_MIN_VALUABLE_OPPORTUNITY_SCORE,
            "minimum_executability_score": DREAM_MIN_VALUABLE_EXECUTABILITY_SCORE,
            "max_selected_experiments": DREAM_MAX_SELECTED_EXPERIMENTS,
            "dedupe_rule": "At most one selected experiment per route-and-mode batch key.",
            "prior_sandbox_success_rule": (
                "Skip route-and-mode experiments already passed with strong or moderate sandbox evidence "
                "in a prior Dream report."
            ),
            "route_candidate_modes": ["dream-adjacent", "candidate-backlog"],
            "candidate_backlog_write_back": "history-only Sleep handoff",
            "sandbox_experiment_mode": SANDBOX_EXPERIMENT_MODE,
            "sandbox_experiment_modes": [SANDBOX_MODE_RETRIEVAL_AB, SANDBOX_MODE_SCENARIO_REPLAY],
            "sandbox_allowed_writes": _sandbox_allowed_writes(repo_root, run_id),
        },
        "opportunity_count": opportunity_count,
        "executable_opportunity_count": executable_opportunity_count,
        "skipped_prior_sandbox_success_count": skipped_prior_sandbox_success_count,
        "selected_experiment_count": len(selected),
        "selected_experiments": selected_experiments,
        "selected_experiment": selected_experiment,
        "checkpoints": [
            _checkpoint("preflight", "Prior Dream-process guidance retrieved", "completed"),
            _checkpoint("opportunity-scan", "Opportunities gathered and executable contracts attached", "completed"),
            _checkpoint("experiment-selection", "Valuable executable experiments selected", selection_status, selection_details),
            _checkpoint("experiment-record", "Experiment records written before action", "completed" if selected else "skipped", selection_details),
            _checkpoint("validation", "Selected experiments validated sequentially", "pending" if selected else "skipped", selection_details),
            _checkpoint("experiment-observation", "Route-specific experiment observations written", "pending" if selected else "skipped", selection_details),
            _checkpoint("run-observation", "Run-level Dream-process observation written", "pending"),
            _checkpoint("report", "Dream report written", "pending"),
        ],
        "artifact_paths": {
            "run_dir": relative_repo_path(repo_root, dream_run_dir(repo_root, run_id)),
            "sandbox_dir": relative_repo_path(repo_root, dream_sandbox_dir(repo_root, run_id)),
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


def _write_skip_event(repo_root: Path, run_id: str, lane_guard: dict[str, Any]) -> str:
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
        rationale="Skipped dream mode because another core maintenance lane is still running.",
        context={"lane_guard": lane_guard},
    )
    record_history_event(repo_root, event)
    return str(event["event_id"])


def run_dream_maintenance(
    repo_root: Path,
    *,
    run_id: str | None = None,
    max_events: int | None = None,
) -> dict[str, Any]:
    generated_at = utc_now_iso()
    resolved_run_id = sanitize_run_id(run_id or f"kb-dream-{utc_now_compact()}")
    run_dir = dream_run_dir(repo_root, resolved_run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    lane_lock = acquire_lane_lock(repo_root, "kb-dream", run_id=resolved_run_id)
    lock_released = False
    try:
        write_lane_status(repo_root, "kb-dream", "running", run_id=resolved_run_id)

        lane_guard = build_dream_guard(repo_root)
        plan_payload = {
            "schema_version": DREAM_SCHEMA_VERSION,
            "kind": "local-kb-dream-plan",
            "run_id": resolved_run_id,
            "generated_at": generated_at,
            "lane_guard": lane_guard,
        }
        write_json_file(run_dir / PLAN_FILENAME, plan_payload)

        if lane_guard["blocked"]:
            skipped_event_id = _write_skip_event(repo_root, resolved_run_id, lane_guard)
            write_lane_status(repo_root, "kb-dream", "skipped", run_id=resolved_run_id)
            result = {
                "schema_version": DREAM_SCHEMA_VERSION,
                "kind": DREAM_REPORT_KIND,
                "run_id": resolved_run_id,
                "generated_at": generated_at,
                "status": "skipped",
                "reason": "maintenance-lane-active",
                "lane_guard": lane_guard,
                "history_event_ids": [skipped_event_id],
                "artifact_paths": {
                    "run_dir": relative_repo_path(repo_root, run_dir),
                    "plan_path": relative_repo_path(repo_root, run_dir / PLAN_FILENAME),
                    "report_path": relative_repo_path(repo_root, run_dir / REPORT_FILENAME),
                },
            }
            result["lane_lock"] = lane_lock
            result["lock_release"] = release_lane_lock(repo_root, "kb-dream", run_id=resolved_run_id)
            lock_released = True
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
        prior_successful_sandbox_keys = _load_prior_successful_sandbox_keys(
            repo_root,
            current_run_id=resolved_run_id,
        )
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
        selected = _select_valuable_experiments(
            opportunities,
            prior_successful_sandbox_keys=prior_successful_sandbox_keys,
        )
        skipped_prior_success_count = sum(
            1
            for item in opportunities
            if item.get("selection_status") == "skipped-prior-sandbox-success"
        )
        write_json_file(
            run_dir / OPPORTUNITIES_FILENAME,
            {
                "schema_version": DREAM_SCHEMA_VERSION,
                "kind": "local-kb-dream-opportunities",
                "run_id": resolved_run_id,
                "generated_at": generated_at,
                "opportunity_count": len(opportunities),
                "prior_sandbox_success_count": len(prior_successful_sandbox_keys),
                "skipped_prior_sandbox_success_count": skipped_prior_success_count,
                "opportunities": opportunities,
            },
        )
        planned_experiments = [
            {
                "sequence_index": sequence_index,
                "route_ref": item["route_ref"],
                "kind": item["kind"],
                "candidate_creation_mode": str(item.get("candidate_creation_mode", "") or ""),
                "hypothesis": item["hypothesis"],
                "allowed_action_surface": item["allowed_action_surface"],
                "experiment_design": item["experiment_design"],
                "validation_plan": item["validation_plan"],
                "success_criteria": item["success_criteria"],
                "failure_criteria": item["failure_criteria"],
                "safety_tier": item["safety_tier"],
                "rollback_plan": item["rollback_plan"],
                "permitted_write_back": item["permitted_write_back"],
                "sandbox_mode": _sandbox_mode_for_opportunity(item),
                "allowed_writes": _sandbox_allowed_writes(repo_root, resolved_run_id),
                "is_executable": item["is_executable"],
                "executability_score": item["executability_score"],
                "status": "planned",
            }
            for sequence_index, item in enumerate(selected, start=1)
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
            skipped_prior_sandbox_success_count=skipped_prior_success_count,
        )
        write_json_file(run_dir / EXECUTION_PLAN_FILENAME, execution_plan)
        plan_payload["execution_plan_path"] = relative_repo_path(repo_root, run_dir / EXECUTION_PLAN_FILENAME)
        plan_payload["executable_opportunity_count"] = len(executable_opportunities)
        plan_payload["valuable_opportunity_count"] = len(selected)
        plan_payload["skipped_prior_sandbox_success_count"] = skipped_prior_success_count
        write_json_file(run_dir / PLAN_FILENAME, plan_payload)

        experiment_results: list[dict[str, Any]] = []
        created_candidates: list[dict[str, Any]] = []
        history_event_ids: list[str] = []

        for sequence_index, opportunity in enumerate(selected, start=1):
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
            elif opportunity["kind"] == "route-candidate" and opportunity["candidate_creation_mode"] == "candidate-backlog":
                classification = "candidate-backlog"
                sibling_counts = opportunity.get("sibling_status_counts", {})
                if not isinstance(sibling_counts, dict):
                    sibling_counts = {}
                outcome = (
                    f"Route {opportunity['route_title']} lacks exact local coverage, but adjacent candidate backlog "
                    f"already exists in the same route family: {sibling_counts}."
                )
                comment = (
                    "Dream mode kept this history-only and left the route family for Sleep to merge, reject, "
                    "narrow, or consolidate instead of creating another candidate."
                )
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
                "sequence_index": sequence_index,
                "kind": opportunity["kind"],
                "route_ref": opportunity["route_ref"],
                "route_title": opportunity["route_title"],
                "candidate_creation_mode": str(opportunity.get("candidate_creation_mode", "") or ""),
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
            sandbox_result = _run_dream_sandbox(
                repo_root,
                run_id=resolved_run_id,
                generated_at=generated_at,
                sequence_index=sequence_index,
                opportunity=opportunity,
                search_context=search_context,
                classification=classification,
                history_events=history_events,
            )
            experiment.update(sandbox_result)
            if experiment.get("sandbox_mode") == SANDBOX_MODE_SCENARIO_REPLAY:
                replay = experiment.get("scenario_replay", {})
                decision = replay.get("decision_delta", {}) if isinstance(replay, dict) else {}
                action_taken = (
                    f"Ran a scenario-replay Dream sandbox for {opportunity['route_title']}: compared local search "
                    "without the tested card against search with the tested card using a historical or card-derived task scenario."
                )
                observed_result = str(decision.get("reason", "") or observed_result)
                operational_use = (
                    "Use the scenario-replay delta as Sleep review input for the tested candidate; do not treat it "
                    "as trusted-card promotion evidence without later live-task confirmation."
                )
                experiment["action_taken"] = action_taken
                experiment["observed_result"] = observed_result
                experiment["operational_use"] = operational_use
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
            "lane_guard": lane_guard,
            "history_path": relative_repo_path(repo_root, history_events_path(repo_root)),
            "preflight": preflight,
            "execution_plan": execution_plan,
            "opportunity_count": len(opportunities),
            "executable_opportunity_count": len(executable_opportunities),
            "valuable_opportunity_count": len(selected),
            "skipped_prior_sandbox_success_count": skipped_prior_success_count,
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
                "sandbox_dir": relative_repo_path(repo_root, dream_sandbox_dir(repo_root, resolved_run_id)),
                "report_path": relative_repo_path(repo_root, run_dir / REPORT_FILENAME),
            },
        }
        write_json_file(run_dir / REPORT_FILENAME, result)
        write_lane_status(repo_root, "kb-dream", "completed", run_id=resolved_run_id)
        result["lock_release"] = release_lane_lock(repo_root, "kb-dream", run_id=resolved_run_id)
        lock_released = True
        write_json_file(run_dir / REPORT_FILENAME, result)
        return result
    except Exception as exc:
        write_lane_status(repo_root, "kb-dream", "failed", run_id=resolved_run_id, note=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if not lock_released:
            release_lane_lock(repo_root, "kb-dream", run_id=resolved_run_id)
