from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from local_kb.common import parse_route_segments
from local_kb.consolidate_events import (
    ACTION_BASE_SCORES,
    APPLY_MODE_CROSS_INDEX,
    APPLY_MODE_I18N_ZH_CN,
    APPLY_MODE_NEW_CANDIDATES,
    APPLY_MODE_RELATED_CARDS,
    CROSS_INDEX_MAX_COUNT,
    CROSS_INDEX_MIN_REMOVAL_USAGE_COUNT,
    CROSS_INDEX_MIN_SUPPORT_COUNT,
    CROSS_INDEX_MIN_USAGE_RATIO,
    HIT_QUALITY_SCORES,
    RELATED_CARD_MAX_COUNT,
    RELATED_CARD_MIN_SUPPORT_COUNT,
    RELATED_CARD_MIN_USAGE_RATIO,
    build_entry_lookup,
    collect_task_summaries,
    events_by_id,
    has_contrastive_evidence,
    has_predictive_evidence,
    has_predictive_utility,
    normalize_entry_ids,
    normalize_text_list,
    route_label,
    route_or_task_target,
    score_action,
    sort_counter,
    summarize_observation_timeline,
    summarize_predictive_evidence,
    summarize_provenance,
    supporting_events_for_action,
)
from local_kb.semantic_review import (
    APPLY_MODE_SEMANTIC_REVIEW,
    build_semantic_review_suggestion,
    is_semantic_review_action,
)

NEW_CANDIDATE_ALTERNATIVE_LIMIT = 3


def build_next_step(action_type: str, target_kind: str, target_ref: str, routes: list[str]) -> str:
    if action_type == "review-route-i18n":
        return (
            "Inspect missing route segment display labels and patch the zh-CN display map; "
            "do not rename canonical routes or search paths."
        )
    if target_kind == "entry":
        if action_type == "review-candidate":
            return (
                f"Inspect candidate entry {target_ref} during AI semantic review and decide whether it "
                "should stay a candidate, be rewritten, or be promoted."
            )
        if action_type == "review-confidence":
            return (
                f"Inspect weakening or contradictory evidence for entry {target_ref} and decide whether "
                "semantic review should keep it, adjust confidence, narrow scope, or deprecate it."
            )
        if action_type == "review-entry-update":
            return (
                f"Inspect timeline evidence for entry {target_ref} and decide whether the current card "
                "needs an AI-authored semantic-review decision such as keep, rewrite, split, merge, "
                "promote, demote, or deprecate."
            )
        if action_type == "review-related-cards":
            return (
                f"Inspect co-used entry evidence for {target_ref} and decide whether its "
                "top direct related-card links should change."
            )
        if action_type == "review-cross-index":
            return (
                f"Inspect route evidence for {target_ref} and decide whether its "
                "stable alternate cross-index routes should change."
            )
        if action_type == "review-i18n":
            return (
                f"Inspect entry {target_ref} and provide an AI-authored zh-CN translation plan "
                "for missing display-language fields before applying i18n maintenance."
            )
    if action_type == "review-code-change":
        if target_kind == "route" and target_ref:
            return f"Inspect route {target_ref} and decide whether KB tooling, prompts, or maintenance code need a code change."
        if target_kind == "task" and target_ref:
            return f"Inspect task group {target_ref} and decide whether KB tooling, prompts, or maintenance code need a code change."
    if target_kind == "route" and target_ref:
        if action_type == "consider-new-candidate":
            return f"Inspect route {target_ref} and decide whether a new candidate card should be captured."
        if action_type == "review-observation-evidence":
            return f"Inspect route {target_ref} and decide whether the supporting observations should be rewritten into predictive form or ignored as weak evidence."
        if action_type == "review-taxonomy":
            return f"Inspect route {target_ref} for a possible taxonomy adjustment."
        return f"Inspect route {target_ref} for repeated misses or weak hits before changing any cards."
    if routes:
        return f"Inspect supporting history for route {routes[0]} before deciding on any KB edits."
    return "Inspect the grouped history events and choose the next AI consolidation action."


def suggested_artifact_kind(action_type: str, target_kind: str) -> str:
    if action_type == "review-confidence":
        return "confidence-review-proposal"
    if action_type == "review-code-change":
        return "code-change-proposal"
    if action_type == "review-related-cards":
        return "related-card-update-proposal"
    if action_type == "review-cross-index":
        return "cross-index-update-proposal"
    if action_type == "review-i18n":
        return "i18n-translation-plan"
    if action_type == "review-route-i18n":
        return "route-i18n-label-patch"
    if action_type == "review-entry-update":
        return "entry-update-proposal"
    if action_type == "review-observation-evidence":
        return "observation-evidence-review"
    if action_type == "review-taxonomy":
        return "taxonomy-change-proposal"
    if action_type == "consider-new-candidate":
        return "candidate-entry-proposal"
    if action_type == "review-candidate":
        return "candidate-review-summary"
    if action_type == "investigate-gap":
        if target_kind == "route":
            return "route-gap-summary"
        return "gap-investigation-summary"
    return "maintenance-note"


def _ordered_unique_text(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _summarize_text_examples(values: list[str], limit: int = 3) -> str:
    examples = _ordered_unique_text(values)
    if not examples:
        return ""
    clipped = examples[:limit]
    suffix = " ..." if len(examples) > limit else ""
    return "; ".join(clipped) + suffix


def _normalize_predictive_observation(event: dict[str, Any]) -> dict[str, Any]:
    predictive = event.get("predictive_observation", {})
    if not isinstance(predictive, dict):
        predictive = {}
    contrastive = predictive.get("contrastive_evidence", {})
    if not isinstance(contrastive, dict):
        contrastive = {}
    return {
        "scenario": str(predictive.get("scenario", "") or "").strip(),
        "action_taken": str(predictive.get("action_taken", "") or "").strip(),
        "observed_result": str(predictive.get("observed_result", "") or "").strip(),
        "operational_use": str(predictive.get("operational_use", "") or "").strip(),
        "reuse_judgment": str(predictive.get("reuse_judgment", "") or "").strip(),
        "contrastive_evidence": {
            "previous_action": str(contrastive.get("previous_action", "") or "").strip(),
            "previous_result": str(contrastive.get("previous_result", "") or "").strip(),
            "revised_action": str(contrastive.get("revised_action", "") or "").strip(),
            "revised_result": str(contrastive.get("revised_result", "") or "").strip(),
        },
    }


def _build_contrastive_alternatives(
    supporting_events: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], int]:
    alternatives: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    contrastive_event_count = 0

    for event in supporting_events:
        predictive = _normalize_predictive_observation(event)
        contrastive = predictive["contrastive_evidence"]
        previous_action = str(contrastive.get("previous_action", "") or "").strip()
        previous_result = str(contrastive.get("previous_result", "") or "").strip()
        revised_action = str(contrastive.get("revised_action", "") or "").strip()
        revised_result = str(contrastive.get("revised_result", "") or "").strip()
        if previous_action and previous_result and revised_action and revised_result:
            contrastive_event_count += 1
        if not previous_action or not previous_result:
            continue
        scenario = str(predictive.get("scenario", "") or "").strip()
        when_text = f"If Codex repeats the earlier weaker path: {previous_action}"
        if scenario:
            when_text = f"{scenario.rstrip('.')} {when_text}"
        key = (when_text, previous_result)
        if key in seen:
            continue
        seen.add(key)
        alternatives.append({"when": when_text, "result": previous_result})
        if len(alternatives) >= NEW_CANDIDATE_ALTERNATIVE_LIMIT:
            break

    return alternatives, contrastive_event_count


def suggest_new_candidate_scaffold(
    action: dict[str, Any],
    supporting_events: list[dict[str, Any]],
    timeline_summary: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if action.get("action_type") != "consider-new-candidate":
        return None
    if str(action.get("target", {}).get("kind", "") or "") != "route":
        return None

    route_ref = str(action.get("target", {}).get("ref", "") or "").strip()
    route_segments = parse_route_segments(route_ref)
    route_title = " / ".join(route_segments) if route_segments else route_ref
    task_summaries = collect_task_summaries(supporting_events)
    timeline_summary = timeline_summary if isinstance(timeline_summary, dict) else summarize_observation_timeline(supporting_events)
    sequence_examples = _ordered_unique_text(
        [str(item).strip() for item in timeline_summary.get("sequence_examples", [])]
    )

    predictive_rows = [_normalize_predictive_observation(event) for event in supporting_events]
    scenarios = _ordered_unique_text([row["scenario"] for row in predictive_rows])
    action_taken_examples = _ordered_unique_text([row["action_taken"] for row in predictive_rows])
    observed_results = _ordered_unique_text([row["observed_result"] for row in predictive_rows])
    operational_uses = _ordered_unique_text([row["operational_use"] for row in predictive_rows])
    reuse_judgments = _ordered_unique_text([row["reuse_judgment"] for row in predictive_rows])
    revised_actions = _ordered_unique_text(
        [row["contrastive_evidence"]["revised_action"] for row in predictive_rows]
    )
    revised_results = _ordered_unique_text(
        [row["contrastive_evidence"]["revised_result"] for row in predictive_rows]
    )
    alternatives, contrastive_event_count = _build_contrastive_alternatives(supporting_events)

    event_count = int(action.get("event_count", 0) or 0)
    future_utility_count = sum(1 for event in supporting_events if has_predictive_utility(event))
    seed_candidate = event_count == 1 and future_utility_count >= 1
    if seed_candidate:
        if_notes_parts = [
            "Auto-created from 1 complete, future-useful predictive observation as a low-confidence seed candidate."
        ]
    else:
        if_notes_parts = [f"Auto-created from {event_count} grouped new-candidate observations."]
        if future_utility_count:
            if_notes_parts.append(f"{future_utility_count} supporting observations include concrete future utility.")
    if task_summaries:
        if_notes_parts.append(f"Example task summaries: {_summarize_text_examples(task_summaries)}.")
    if scenarios:
        if_notes_parts.append(f"Repeated scenarios: {_summarize_text_examples(scenarios, limit=2)}.")
    if sequence_examples:
        if_notes_parts.append(f"Observed chronology: {sequence_examples[0]}")
    if contrastive_event_count:
        if_notes_parts.append(
            f"{contrastive_event_count} supporting observations explicitly captured both a weaker earlier path and a stronger revised path."
        )

    if revised_actions:
        action_description = f"Tasks routed through {route_title} where Codex follows this stronger revised path: {revised_actions[0]}"
    elif action_taken_examples:
        action_description = f"Tasks routed through {route_title} where Codex follows this observed path: {action_taken_examples[0]}"
    else:
        action_description = f"Handle tasks routed through {route_title} without a consolidated KB card."

    if revised_results:
        expected_result = revised_results[0]
    elif observed_results:
        expected_result = observed_results[0]
    else:
        expected_result = (
            f"Grouped observations suggest Codex will keep missing reusable guidance for {route_title} "
            "until a route-specific card is authored."
        )

    guidance_parts = [
        "Review the cited observations and replace this auto-created scaffold with a specific predictive card before any promotion."
    ]
    if seed_candidate:
        guidance_parts.append(
            "Treat this as a retrieval seed, not a trusted rule; require later evidence before promotion or high-confidence reliance."
        )
    if operational_uses:
        guidance_parts.append(_summarize_text_examples(operational_uses, limit=2))
    elif reuse_judgments:
        guidance_parts.append(_summarize_text_examples(reuse_judgments, limit=1))
    if contrastive_event_count or any(has_contrastive_evidence(event) for event in supporting_events):
        guidance_parts.append(
            "Preserve weaker-path evidence in predict.alternatives instead of collapsing the lesson into a single success summary."
        )
    if sequence_examples:
        guidance_parts.append(
            "Use same-project or same-thread chronology when rewriting this scaffold so the final card preserves what was tried earlier, what changed later, and why the better path won."
        )

    return {
        "title": (
            f"Contrastive route lesson in {route_title}"
            if alternatives
            else f"{'Seed' if seed_candidate else 'Repeated'} route gap in {route_title}"
        ),
        "if": {"notes": " ".join(if_notes_parts).strip()},
        "action": {"description": action_description},
        "predict": {
            "expected_result": expected_result,
            "alternatives": alternatives,
        },
        "use": {
            "guidance": " ".join(part for part in guidance_parts if part).strip()
        },
        "contrastive_event_count": contrastive_event_count,
    }


def _collect_related_card_observation_stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "usage_event_ids": {},
        "routes_by_entry": {},
        "first_event_at": {},
        "latest_event_at": {},
        "event_types_by_entry": {},
        "suggested_actions_by_entry": {},
        "hit_quality_by_entry": {},
        "exposed_gap_by_entry": {},
        "partner_support_by_entry": {},
    }

    for event in events:
        if str(event.get("event_type", "") or "") != "observation":
            continue
        entry_ids = normalize_entry_ids(event.get("entry_ids", []))
        if not entry_ids:
            continue

        event_id = str(event.get("event_id", "") or "")
        route_ref = route_label(event.get("route_hint", []))
        created_at = str(event.get("created_at", "") or "")
        event_type = str(event.get("event_type", "") or "")
        suggested_action = str(event.get("suggested_action", "none") or "none")
        hit_quality = str(event.get("hit_quality", "none") or "none")

        for entry_id in entry_ids:
            stats["usage_event_ids"].setdefault(entry_id, set()).add(event_id)
            if route_ref:
                stats["routes_by_entry"].setdefault(entry_id, set()).add(route_ref)
            stats["event_types_by_entry"].setdefault(entry_id, Counter())[event_type] += 1
            if suggested_action != "none":
                stats["suggested_actions_by_entry"].setdefault(entry_id, Counter())[suggested_action] += 1
            if hit_quality != "none":
                stats["hit_quality_by_entry"].setdefault(entry_id, Counter())[hit_quality] += 1
            if event.get("exposed_gap"):
                stats["exposed_gap_by_entry"][entry_id] = stats["exposed_gap_by_entry"].get(entry_id, 0) + 1
            if created_at and (
                not stats["first_event_at"].get(entry_id) or created_at < stats["first_event_at"][entry_id]
            ):
                stats["first_event_at"][entry_id] = created_at
            if created_at and (
                not stats["latest_event_at"].get(entry_id) or created_at > stats["latest_event_at"][entry_id]
            ):
                stats["latest_event_at"][entry_id] = created_at

        if len(entry_ids) < 2:
            continue

        for entry_id in entry_ids:
            partner_counter = stats["partner_support_by_entry"].setdefault(entry_id, Counter())
            for partner_id in entry_ids:
                if partner_id == entry_id:
                    continue
                partner_counter[partner_id] += 1

    return stats


def _build_related_card_action(
    entry_id: str,
    stats: dict[str, Any],
    entry_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    current_related_cards = normalize_text_list(entry_lookup.get(entry_id, {}).get("related_cards", []))
    partner_counter = stats["partner_support_by_entry"].get(entry_id, Counter())
    if not partner_counter and not current_related_cards:
        return None

    event_ids = sorted(stats["usage_event_ids"].get(entry_id, set()))
    routes = sorted(stats["routes_by_entry"].get(entry_id, set()))
    return {
        "action_key": f"review-related-cards::entry::{entry_id}",
        "action_type": "review-related-cards",
        "target": {"kind": "entry", "ref": entry_id},
        "priority_score": score_action(
            action_type="review-related-cards",
            event_count=len(event_ids),
            hit_quality=stats["hit_quality_by_entry"].get(entry_id, Counter()),
            exposed_gap_count=stats["exposed_gap_by_entry"].get(entry_id, 0),
        ),
        "event_count": len(event_ids),
        "event_ids": event_ids,
        "entry_ids": [entry_id],
        "routes": routes,
        "signals": {
            "event_types": sort_counter(stats["event_types_by_entry"].get(entry_id, Counter())),
            "suggested_actions": sort_counter(stats["suggested_actions_by_entry"].get(entry_id, Counter())),
            "hit_quality": sort_counter(stats["hit_quality_by_entry"].get(entry_id, Counter())),
            "exposed_gap_count": stats["exposed_gap_by_entry"].get(entry_id, 0),
            "current_related_cards": current_related_cards,
            "partner_support": {
                partner_id: int(count)
                for partner_id, count in sorted(partner_counter.items())
            },
        },
        "reasons": ["co-used-entry-ids"],
        "first_event_at": stats["first_event_at"].get(entry_id, ""),
        "latest_event_at": stats["latest_event_at"].get(entry_id, ""),
        "ai_decision_required": True,
    }


def build_related_card_actions(
    events: list[dict[str, Any]],
    entry_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    stats = _collect_related_card_observation_stats(events)
    actions: list[dict[str, Any]] = []
    for entry_id in sorted(stats["usage_event_ids"]):
        action = _build_related_card_action(entry_id=entry_id, stats=stats, entry_lookup=entry_lookup)
        if action:
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


def _collect_cross_index_observation_stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "usage_event_ids": {},
        "observed_routes_by_entry": {},
        "first_event_at": {},
        "latest_event_at": {},
        "event_types_by_entry": {},
        "suggested_actions_by_entry": {},
        "hit_quality_by_entry": {},
        "exposed_gap_by_entry": {},
    }

    for event in events:
        if str(event.get("event_type", "") or "") != "observation":
            continue
        entry_ids = normalize_entry_ids(event.get("entry_ids", []))
        if not entry_ids:
            continue

        event_id = str(event.get("event_id", "") or "")
        route_ref = route_label(event.get("route_hint", []))
        created_at = str(event.get("created_at", "") or "")
        event_type = str(event.get("event_type", "") or "")
        suggested_action = str(event.get("suggested_action", "none") or "none")
        hit_quality = str(event.get("hit_quality", "none") or "none")

        for entry_id in entry_ids:
            stats["usage_event_ids"].setdefault(entry_id, set()).add(event_id)
            if route_ref:
                stats["observed_routes_by_entry"].setdefault(entry_id, Counter())[route_ref] += 1
            stats["event_types_by_entry"].setdefault(entry_id, Counter())[event_type] += 1
            if suggested_action != "none":
                stats["suggested_actions_by_entry"].setdefault(entry_id, Counter())[suggested_action] += 1
            if hit_quality != "none":
                stats["hit_quality_by_entry"].setdefault(entry_id, Counter())[hit_quality] += 1
            if event.get("exposed_gap"):
                stats["exposed_gap_by_entry"][entry_id] = stats["exposed_gap_by_entry"].get(entry_id, 0) + 1
            if created_at and (
                not stats["first_event_at"].get(entry_id) or created_at < stats["first_event_at"][entry_id]
            ):
                stats["first_event_at"][entry_id] = created_at
            if created_at and (
                not stats["latest_event_at"].get(entry_id) or created_at > stats["latest_event_at"][entry_id]
            ):
                stats["latest_event_at"][entry_id] = created_at

    return stats


def _build_cross_index_action(
    entry_id: str,
    stats: dict[str, Any],
    entry_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    entry = entry_lookup.get(entry_id, {})
    current_cross_index = normalize_text_list(entry.get("cross_index", []))
    observed_routes = stats["observed_routes_by_entry"].get(entry_id, Counter())
    domain_route = route_label(parse_route_segments(entry.get("domain_path", [])))
    if domain_route:
        observed_routes.pop(domain_route, None)

    if not observed_routes and not current_cross_index:
        return None

    event_ids = sorted(stats["usage_event_ids"].get(entry_id, set()))
    return {
        "action_key": f"review-cross-index::entry::{entry_id}",
        "action_type": "review-cross-index",
        "target": {"kind": "entry", "ref": entry_id},
        "priority_score": score_action(
            action_type="review-cross-index",
            event_count=len(event_ids),
            hit_quality=stats["hit_quality_by_entry"].get(entry_id, Counter()),
            exposed_gap_count=stats["exposed_gap_by_entry"].get(entry_id, 0),
        ),
        "event_count": len(event_ids),
        "event_ids": event_ids,
        "entry_ids": [entry_id],
        "routes": sorted(observed_routes.keys()),
        "signals": {
            "event_types": sort_counter(stats["event_types_by_entry"].get(entry_id, Counter())),
            "suggested_actions": sort_counter(stats["suggested_actions_by_entry"].get(entry_id, Counter())),
            "hit_quality": sort_counter(stats["hit_quality_by_entry"].get(entry_id, Counter())),
            "exposed_gap_count": stats["exposed_gap_by_entry"].get(entry_id, 0),
            "current_cross_index": current_cross_index,
            "observed_route_support": {
                route_ref: int(count)
                for route_ref, count in sorted(observed_routes.items())
            },
        },
        "reasons": ["repeated-route-alignment"],
        "first_event_at": stats["first_event_at"].get(entry_id, ""),
        "latest_event_at": stats["latest_event_at"].get(entry_id, ""),
        "ai_decision_required": True,
    }


def build_cross_index_actions(
    events: list[dict[str, Any]],
    entry_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    stats = _collect_cross_index_observation_stats(events)
    actions: list[dict[str, Any]] = []
    for entry_id in sorted(stats["usage_event_ids"]):
        action = _build_cross_index_action(entry_id=entry_id, stats=stats, entry_lookup=entry_lookup)
        if action:
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


def suggest_confidence_review(
    action: dict[str, Any],
    supporting_events: list[dict[str, Any]],
    entry_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if action.get("action_type") != "review-confidence":
        return None
    if str(action.get("target", {}).get("kind", "")) != "entry":
        return None
    entry_id = str(action.get("target", {}).get("ref", "") or "")
    entry = entry_lookup.get(entry_id, {})
    current_confidence = float(entry.get("confidence", 0.0) or 0.0)
    status = str(entry.get("status", "") or "")
    hit_quality = Counter(
        str(event.get("hit_quality", "none") or "none")
        for event in supporting_events
        if str(event.get("hit_quality", "none") or "none") != "none"
    )
    exposed_gap_count = sum(1 for event in supporting_events if event.get("exposed_gap"))
    delta = -(
        (0.05 * hit_quality.get("weak", 0))
        + (0.10 * hit_quality.get("miss", 0))
        + (0.20 * hit_quality.get("misleading", 0))
        + (0.05 * exposed_gap_count)
    )
    delta = max(delta, -0.40)
    suggested_confidence = round(max(0.0, min(1.0, current_confidence + delta)), 2)
    if suggested_confidence >= 0.75:
        review_state = "normal-trusted-use"
    elif suggested_confidence >= 0.50:
        review_state = "watch-and-review"
    else:
        review_state = "revise-or-deprecate"
    return {
        "entry_id": entry_id,
        "current_confidence": round(current_confidence, 2),
        "suggested_delta": round(delta, 2),
        "suggested_confidence": suggested_confidence,
        "current_status": status,
        "review_state": review_state,
    }


def suggest_observation_disposition(
    action: dict[str, Any],
    supporting_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if action.get("action_type") != "review-observation-evidence":
        return None
    predictive_summary = summarize_predictive_evidence(supporting_events)
    if predictive_summary["future_utility_event_count"] > 0:
        recommendation = "rewrite-to-predictive-card-evidence"
    elif predictive_summary["complete_event_count"] > 0:
        recommendation = "keep-history-only-or-ignore-low-utility"
    elif int(action.get("event_count", 0) or 0) > 1:
        recommendation = "rewrite-or-split-observations"
    else:
        recommendation = "ignore-if-one-off"
    return {
        "recommendation": recommendation,
        "complete_event_count": predictive_summary["complete_event_count"],
        "incomplete_event_count": predictive_summary["incomplete_event_count"],
        "future_utility_event_count": predictive_summary["future_utility_event_count"],
        "low_utility_event_count": predictive_summary["low_utility_event_count"],
    }


def _collect_related_partner_stats(
    entry_id: str,
    supporting_events: list[dict[str, Any]],
) -> tuple[int, Counter[str], dict[str, list[str]], dict[str, set[str]]]:
    usage_count = len(supporting_events)
    partner_support: Counter[str] = Counter()
    partner_event_ids: dict[str, list[str]] = {}
    partner_routes: dict[str, set[str]] = {}

    for event in supporting_events:
        event_id = str(event.get("event_id", "") or "").strip()
        route_ref = route_label(event.get("route_hint", []))
        entry_ids = normalize_entry_ids(event.get("entry_ids", []))
        if entry_id not in entry_ids:
            continue
        for partner_id in entry_ids:
            if partner_id == entry_id:
                continue
            partner_support[partner_id] += 1
            if event_id:
                partner_event_ids.setdefault(partner_id, []).append(event_id)
            if route_ref:
                partner_routes.setdefault(partner_id, set()).add(route_ref)

    return usage_count, partner_support, partner_event_ids, partner_routes


def _build_related_candidate_links(
    usage_count: int,
    partner_support: Counter[str],
    partner_event_ids: dict[str, list[str]],
    partner_routes: dict[str, set[str]],
    entry_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    candidate_links: list[dict[str, Any]] = []
    for partner_id, support_count in sorted(partner_support.items()):
        if partner_id not in entry_lookup:
            continue
        usage_ratio = round(float(support_count) / float(usage_count), 2) if usage_count else 0.0
        score = round(float(support_count) * usage_ratio, 2)
        qualifies = (
            support_count >= RELATED_CARD_MIN_SUPPORT_COUNT
            and usage_ratio >= RELATED_CARD_MIN_USAGE_RATIO
        )
        candidate_links.append(
            {
                "entry_id": partner_id,
                "support_count": int(support_count),
                "usage_ratio": usage_ratio,
                "score": score,
                "qualifies": qualifies,
                "event_ids": sorted(set(partner_event_ids.get(partner_id, []))),
                "routes": sorted(partner_routes.get(partner_id, set())),
            }
        )

    candidate_links.sort(
        key=lambda item: (
            -float(item["score"]),
            -int(item["support_count"]),
            str(item["entry_id"]),
        )
    )
    return candidate_links


def _related_card_recommendation(
    current_related_cards: list[str],
    suggested_related_cards: list[str],
    usage_count: int,
) -> tuple[str, str, bool]:
    if suggested_related_cards != current_related_cards and suggested_related_cards:
        return (
            "update-related-cards",
            "Repeated co-use suggests a stable direct related-card link set.",
            True,
        )
    if current_related_cards and not suggested_related_cards:
        if usage_count >= RELATED_CARD_MIN_SUPPORT_COUNT:
            return (
                "remove-stale-related-cards",
                "Current related-card links are no longer supported strongly enough by recent co-use evidence.",
                True,
            )
        return (
            "watch-current-related-cards",
            "Fresh evidence is still too sparse to justify automatic removal of current related-card links.",
            False,
        )
    if suggested_related_cards == current_related_cards and suggested_related_cards:
        return (
            "keep-current-related-cards",
            "Current related-card links still match the strongest direct co-use evidence.",
            False,
        )
    return (
        "insufficient-related-card-evidence",
        "Co-use evidence is too weak or too sparse to justify direct related-card links.",
        False,
    )


def suggest_related_card_update(
    action: dict[str, Any],
    supporting_events: list[dict[str, Any]],
    entry_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if action.get("action_type") != "review-related-cards":
        return None
    if str(action.get("target", {}).get("kind", "")) != "entry":
        return None

    entry_id = str(action.get("target", {}).get("ref", "") or "").strip()
    if not entry_id:
        return None

    current_related_cards = normalize_text_list(entry_lookup.get(entry_id, {}).get("related_cards", []))
    usage_count, partner_support, partner_event_ids, partner_routes = _collect_related_partner_stats(
        entry_id=entry_id,
        supporting_events=supporting_events,
    )
    candidate_links = _build_related_candidate_links(
        usage_count=usage_count,
        partner_support=partner_support,
        partner_event_ids=partner_event_ids,
        partner_routes=partner_routes,
        entry_lookup=entry_lookup,
    )
    suggested_related_cards = [
        item["entry_id"]
        for item in candidate_links
        if item["qualifies"]
    ][:RELATED_CARD_MAX_COUNT]

    added_cards = [item for item in suggested_related_cards if item not in current_related_cards]
    removed_cards = [item for item in current_related_cards if item not in suggested_related_cards]
    recommendation, reason, eligible = _related_card_recommendation(
        current_related_cards=current_related_cards,
        suggested_related_cards=suggested_related_cards,
        usage_count=usage_count,
    )

    return {
        "entry_id": entry_id,
        "current_related_cards": current_related_cards,
        "suggested_related_cards": suggested_related_cards,
        "added_cards": added_cards,
        "removed_cards": removed_cards,
        "usage_count": usage_count,
        "candidate_links": candidate_links[:RELATED_CARD_MAX_COUNT + 2],
        "recommendation": recommendation,
        "reason": reason,
        "max_related_cards": RELATED_CARD_MAX_COUNT,
        "min_support_count": RELATED_CARD_MIN_SUPPORT_COUNT,
        "min_usage_ratio": RELATED_CARD_MIN_USAGE_RATIO,
        "apply_supported_mode": APPLY_MODE_RELATED_CARDS,
        "apply_eligible": eligible and entry_id in entry_lookup,
    }


def _collect_cross_index_route_support(
    entry_id: str,
    domain_route: str,
    supporting_events: list[dict[str, Any]],
) -> tuple[int, Counter[str], dict[str, list[str]]]:
    usage_count = len(supporting_events)
    route_support: Counter[str] = Counter()
    route_event_ids: dict[str, list[str]] = {}

    for event in supporting_events:
        route_ref = route_label(event.get("route_hint", []))
        if not route_ref or route_ref == domain_route:
            continue
        if entry_id not in normalize_entry_ids(event.get("entry_ids", [])):
            continue
        route_support[route_ref] += 1
        event_id = str(event.get("event_id", "") or "").strip()
        if event_id:
            route_event_ids.setdefault(route_ref, []).append(event_id)

    return usage_count, route_support, route_event_ids


def _build_cross_index_candidate_routes(
    current_cross_index: list[str],
    usage_count: int,
    route_support: Counter[str],
    route_event_ids: dict[str, list[str]],
) -> list[dict[str, Any]]:
    candidate_routes: list[dict[str, Any]] = []
    for route_ref, support_count in sorted(route_support.items()):
        usage_ratio = round(float(support_count) / float(usage_count), 2) if usage_count else 0.0
        score = round(float(support_count) * usage_ratio, 2)
        qualifies = (
            support_count >= CROSS_INDEX_MIN_SUPPORT_COUNT
            and usage_ratio >= CROSS_INDEX_MIN_USAGE_RATIO
        )
        candidate_routes.append(
            {
                "route": route_ref,
                "support_count": int(support_count),
                "usage_ratio": usage_ratio,
                "score": score,
                "qualifies": qualifies,
                "current": route_ref in current_cross_index,
                "event_ids": sorted(set(route_event_ids.get(route_ref, []))),
            }
        )

    candidate_routes.sort(
        key=lambda item: (
            -float(item["score"]),
            -int(item["support_count"]),
            str(item["route"]),
        )
    )
    return candidate_routes


def _cross_index_recommendation(
    current_cross_index: list[str],
    suggested_cross_index: list[str],
    added_routes: list[str],
    removed_routes: list[str],
) -> tuple[str, str, bool]:
    if suggested_cross_index != current_cross_index and added_routes and not removed_routes:
        return (
            "update-cross-index",
            "Repeated route evidence suggests stable alternate retrieval paths for this entry.",
            True,
        )
    if removed_routes:
        return (
            "review-cross-index-pruning",
            "Current low-risk apply only strengthens stable alternate routes. Any cross-index pruning should stay proposal-only until stronger removal evidence exists.",
            False,
        )
    if suggested_cross_index == current_cross_index and suggested_cross_index:
        return (
            "keep-current-cross-index",
            "Current cross-index routes still match the strongest recent alternate-route evidence.",
            False,
        )
    return (
        "insufficient-cross-index-evidence",
        "Route evidence is too weak or too sparse to justify changing cross-index routes.",
        False,
    )


def suggest_cross_index_update(
    action: dict[str, Any],
    supporting_events: list[dict[str, Any]],
    entry_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if action.get("action_type") != "review-cross-index":
        return None
    if str(action.get("target", {}).get("kind", "")) != "entry":
        return None

    entry_id = str(action.get("target", {}).get("ref", "") or "").strip()
    entry = entry_lookup.get(entry_id, {})
    if not entry_id or not entry:
        return None

    current_cross_index = normalize_text_list(entry.get("cross_index", []))
    domain_route = route_label(parse_route_segments(entry.get("domain_path", [])))
    usage_count, route_support, route_event_ids = _collect_cross_index_route_support(
        entry_id=entry_id,
        domain_route=domain_route,
        supporting_events=supporting_events,
    )
    candidate_routes = _build_cross_index_candidate_routes(
        current_cross_index=current_cross_index,
        usage_count=usage_count,
        route_support=route_support,
        route_event_ids=route_event_ids,
    )

    keep_current_routes = list(current_cross_index)
    qualifying_new_routes = [
        item["route"]
        for item in candidate_routes
        if item["qualifies"] and item["route"] not in current_cross_index
    ]

    suggested_cross_index = list(dict.fromkeys(keep_current_routes + qualifying_new_routes))[:CROSS_INDEX_MAX_COUNT]
    added_routes = [route_ref for route_ref in suggested_cross_index if route_ref not in current_cross_index]
    removed_routes = [route_ref for route_ref in current_cross_index if route_ref not in suggested_cross_index]
    recommendation, reason, eligible = _cross_index_recommendation(
        current_cross_index=current_cross_index,
        suggested_cross_index=suggested_cross_index,
        added_routes=added_routes,
        removed_routes=removed_routes,
    )

    return {
        "entry_id": entry_id,
        "domain_route": domain_route,
        "current_cross_index": current_cross_index,
        "suggested_cross_index": suggested_cross_index,
        "added_routes": added_routes,
        "removed_routes": removed_routes,
        "usage_count": usage_count,
        "candidate_routes": candidate_routes[: CROSS_INDEX_MAX_COUNT + 2],
        "recommendation": recommendation,
        "reason": reason,
        "max_cross_index": CROSS_INDEX_MAX_COUNT,
        "min_support_count": CROSS_INDEX_MIN_SUPPORT_COUNT,
        "min_usage_ratio": CROSS_INDEX_MIN_USAGE_RATIO,
        "min_removal_usage_count": CROSS_INDEX_MIN_REMOVAL_USAGE_COUNT,
        "apply_supported_mode": APPLY_MODE_CROSS_INDEX,
        "apply_eligible": eligible and entry_id in entry_lookup,
    }


def summarize_distinct_predictive_values(
    events: list[dict[str, Any]],
    field: str,
) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for event in events:
        predictive = event.get("predictive_observation", {})
        if not isinstance(predictive, dict):
            continue
        value = str(predictive.get(field, "") or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def suggest_split_review(
    action: dict[str, Any],
    supporting_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if action.get("action_type") != "review-entry-update":
        return None
    if str(action.get("target", {}).get("kind", "")) != "entry":
        return None

    route_values = sorted(
        {
            route_label(event.get("route_hint", []))
            for event in supporting_events
            if event.get("route_hint")
        }
    )
    task_summaries = collect_task_summaries(supporting_events)
    scenarios = summarize_distinct_predictive_values(supporting_events, "scenario")
    observed_results = summarize_distinct_predictive_values(supporting_events, "observed_result")
    operational_uses = summarize_distinct_predictive_values(supporting_events, "operational_use")
    complete_predictive_count = sum(1 for event in supporting_events if has_predictive_evidence(event))
    support_count = int(action.get("event_count", 0) or 0)
    same_route_variety = (
        support_count >= 2
        and len(route_values) < 2
        and (
            len(scenarios) >= 2
            or len(observed_results) >= 2
            or len(operational_uses) >= 2
            or len(task_summaries) >= 3
        )
    )
    same_route_branching = (
        len(route_values) < 2
        and complete_predictive_count >= 3
        and (
            (len(scenarios) >= 3 and len(observed_results) >= 3)
            or (len(scenarios) >= 3 and len(operational_uses) >= 3)
            or (len(observed_results) >= 3 and len(operational_uses) >= 3)
        )
    )
    overloaded = support_count >= 2 and (len(route_values) >= 2 or same_route_branching)

    if overloaded:
        recommendation = "consider-split-review"
        if same_route_branching:
            reason = (
                "Same-route evidence already shows clearly separated predictive branches, so this entry "
                "should be reviewed as potentially overloaded even before new routes accumulate."
            )
        else:
            reason = (
                "Supporting evidence suggests this entry may now carry multiple predictive relations "
                "or route-specific subcases."
            )
    else:
        recommendation = "keep-as-hub-for-now"
        if same_route_variety:
            reason = (
                "Same-route repetition alone does not justify a split. Keep the card as a hub for now "
                "unless future evidence shows multi-route or clearly separated predictive branches."
            )
        else:
            reason = (
                "Repeated hits alone do not justify a split. Keep broad hub cards intact while they still "
                "express one bounded predictive relation."
            )

    return {
        "recommendation": recommendation,
        "support_count": support_count,
        "distinct_route_count": len(route_values),
        "distinct_task_summary_count": len(task_summaries),
        "distinct_scenario_count": len(scenarios),
        "distinct_observed_result_count": len(observed_results),
        "distinct_operational_use_count": len(operational_uses),
        "complete_predictive_event_count": complete_predictive_count,
        "reason": reason,
    }


def describe_apply_eligibility(
    action: dict[str, Any],
    supporting_events: list[dict[str, Any]],
) -> dict[str, Any]:
    if action["action_type"] == "review-related-cards":
        return {
            "supported_mode": APPLY_MODE_RELATED_CARDS,
            "eligible": False,
            "reason": "Related-card apply eligibility depends on the derived co-use suggestion.",
        }
    if action["action_type"] == "review-cross-index":
        return {
            "supported_mode": APPLY_MODE_CROSS_INDEX,
            "eligible": False,
            "reason": "Cross-index apply eligibility depends on the derived route-support suggestion.",
        }
    if action["action_type"] == "review-i18n":
        return {
            "supported_mode": APPLY_MODE_I18N_ZH_CN,
            "eligible": False,
            "reason": "i18n apply requires an AI-authored translation plan file.",
        }
    if action["action_type"] == "review-route-i18n":
        return {
            "supported_mode": "manual-code-change",
            "eligible": False,
            "reason": (
                "Route display labels require an AI-authored code patch; "
                "canonical routes must not be auto-renamed."
            ),
        }
    if is_semantic_review_action(action):
        return {
            "supported_mode": APPLY_MODE_SEMANTIC_REVIEW,
            "eligible": False,
            "reason": "Semantic-review apply requires an AI-authored semantic review plan file.",
        }
    if action["action_type"] != "consider-new-candidate":
        return {
            "supported_mode": APPLY_MODE_NEW_CANDIDATES,
            "eligible": False,
            "reason": "Automatic apply is limited to new candidate creation; this action stays proposal-only.",
        }
    if action["target"]["kind"] != "route":
        return {
            "supported_mode": APPLY_MODE_NEW_CANDIDATES,
            "eligible": False,
            "reason": "Automatic apply only supports route-grouped candidate creation.",
        }
    route_segments = parse_route_segments(action["target"].get("ref", ""))
    if len(route_segments) < 3:
        return {
            "supported_mode": APPLY_MODE_NEW_CANDIDATES,
            "eligible": False,
            "reason": "Automatic apply requires a semantically specific route with at least 3 segments.",
        }
    if not collect_task_summaries(supporting_events):
        return {
            "supported_mode": APPLY_MODE_NEW_CANDIDATES,
            "eligible": False,
            "reason": "Automatic apply requires supporting observations with task summaries.",
        }
    support_count = int(action.get("event_count", 0) or 0)
    complete_predictive_count = sum(1 for event in supporting_events if has_predictive_evidence(event))
    future_utility_count = sum(1 for event in supporting_events if has_predictive_utility(event))
    if support_count >= 2:
        if future_utility_count < 1:
            return {
                "supported_mode": APPLY_MODE_NEW_CANDIDATES,
                "eligible": False,
                "candidate_creation_mode": "grouped",
                "complete_predictive_event_count": complete_predictive_count,
                "future_utility_event_count": future_utility_count,
                "reason": (
                    "Automatic candidate creation requires future utility: a concrete operational_use "
                    "and reusable action-selection value."
                ),
            }
        return {
            "supported_mode": APPLY_MODE_NEW_CANDIDATES,
            "eligible": True,
            "candidate_creation_mode": "grouped",
            "complete_predictive_event_count": complete_predictive_count,
            "future_utility_event_count": future_utility_count,
            "reason": "Eligible for conservative candidate scaffold creation.",
        }
    if support_count == 1:
        if future_utility_count >= 1:
            return {
                "supported_mode": APPLY_MODE_NEW_CANDIDATES,
                "eligible": True,
                "candidate_creation_mode": "seed",
                "complete_predictive_event_count": complete_predictive_count,
                "future_utility_event_count": future_utility_count,
                "reason": "Eligible for low-confidence seed candidate creation from one complete, future-useful predictive observation.",
            }
        if complete_predictive_count >= 1:
            return {
                "supported_mode": APPLY_MODE_NEW_CANDIDATES,
                "eligible": False,
                "candidate_creation_mode": "seed",
                "complete_predictive_event_count": complete_predictive_count,
                "future_utility_event_count": future_utility_count,
                "reason": (
                    "Single-observation candidate creation requires future utility: a concrete operational_use "
                    "and reusable action-selection value."
                ),
            }
        return {
            "supported_mode": APPLY_MODE_NEW_CANDIDATES,
            "eligible": False,
            "complete_predictive_event_count": complete_predictive_count,
            "future_utility_event_count": future_utility_count,
            "reason": "Single-observation candidate creation requires complete predictive evidence: scenario, action_taken, and observed_result.",
        }
    return {
        "supported_mode": APPLY_MODE_NEW_CANDIDATES,
        "eligible": False,
        "complete_predictive_event_count": complete_predictive_count,
        "future_utility_event_count": future_utility_count,
        "reason": "Automatic apply requires at least 1 supporting new-candidate observation.",
    }


def annotate_actions_with_apply_eligibility(
    repo_root: Path,
    actions: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    indexed_events = events_by_id(events)
    entry_lookup = build_entry_lookup(repo_root)
    annotated: list[dict[str, Any]] = []
    for action in actions:
        annotated_action = dict(action)
        supporting_events = supporting_events_for_action(action, indexed_events)
        task_summaries = collect_task_summaries(supporting_events)
        annotated_action["task_summaries"] = task_summaries
        annotated_action["recommended_next_step"] = build_next_step(
            action_type=action["action_type"],
            target_kind=str(action["target"]["kind"]),
            target_ref=str(action["target"]["ref"]),
            routes=list(action.get("routes", [])),
        )
        annotated_action["suggested_artifact_kind"] = suggested_artifact_kind(
            action_type=action["action_type"],
            target_kind=str(action["target"]["kind"]),
        )
        annotated_action["apply_eligibility"] = describe_apply_eligibility(
            action=action,
            supporting_events=supporting_events,
        )
        annotated_action["provenance"] = summarize_provenance(supporting_events)
        timeline_summary = summarize_observation_timeline(supporting_events)
        annotated_action["timeline_summary"] = timeline_summary
        annotated_action["predictive_evidence_summary"] = summarize_predictive_evidence(supporting_events)
        candidate_scaffold = suggest_new_candidate_scaffold(
            action=annotated_action,
            supporting_events=supporting_events,
            timeline_summary=timeline_summary,
        )
        if candidate_scaffold:
            annotated_action["candidate_scaffold_preview"] = candidate_scaffold
        confidence_review = suggest_confidence_review(
            action=annotated_action,
            supporting_events=supporting_events,
            entry_lookup=entry_lookup,
        )
        if confidence_review:
            annotated_action["suggested_confidence_change"] = confidence_review
        disposition = suggest_observation_disposition(
            action=annotated_action,
            supporting_events=supporting_events,
        )
        if disposition:
            annotated_action["disposition_suggestion"] = disposition
        related_card_suggestion = suggest_related_card_update(
            action=annotated_action,
            supporting_events=supporting_events,
            entry_lookup=entry_lookup,
        )
        if related_card_suggestion:
            annotated_action["related_card_suggestion"] = related_card_suggestion
            annotated_action["apply_eligibility"] = {
                "supported_mode": APPLY_MODE_RELATED_CARDS,
                "eligible": bool(related_card_suggestion.get("apply_eligible", False)),
                "reason": str(related_card_suggestion.get("reason", "") or ""),
            }
        cross_index_suggestion = suggest_cross_index_update(
            action=annotated_action,
            supporting_events=supporting_events,
            entry_lookup=entry_lookup,
        )
        if cross_index_suggestion:
            annotated_action["cross_index_suggestion"] = cross_index_suggestion
            annotated_action["apply_eligibility"] = {
                "supported_mode": APPLY_MODE_CROSS_INDEX,
                "eligible": bool(cross_index_suggestion.get("apply_eligible", False)),
                "reason": str(cross_index_suggestion.get("reason", "") or ""),
            }
        split_review = suggest_split_review(
            action=annotated_action,
            supporting_events=supporting_events,
        )
        if split_review:
            annotated_action["split_review_suggestion"] = split_review
        semantic_review = build_semantic_review_suggestion(
            action=annotated_action,
            entry_lookup=entry_lookup,
        )
        if semantic_review:
            annotated_action["semantic_review_suggestion"] = semantic_review
            annotated_action["apply_eligibility"] = {
                "supported_mode": APPLY_MODE_SEMANTIC_REVIEW,
                "eligible": False,
                "reason": "Semantic-review apply requires an AI-authored semantic review plan file.",
            }
        annotated.append(annotated_action)
    return annotated
