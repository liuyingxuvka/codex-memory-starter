from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from local_kb.common import normalize_string_list, parse_route_segments, slugify
from local_kb.consolidate_events import (
    APPLY_MODE_CROSS_INDEX,
    APPLY_MODE_I18N_ZH_CN,
    APPLY_MODE_NEW_CANDIDATES,
    APPLY_MODE_NONE,
    APPLY_MODE_RELATED_CARDS,
    APPLY_MODE_SEMANTIC_REVIEW,
    AUTO_CANDIDATE_SCOPE,
    CONSOLIDATION_NOTES,
    SCHEMA_VERSION,
    build_entry_lookup,
    build_entry_path_lookup,
    collect_task_summaries,
    events_by_id,
    group_candidate_actions,
    has_predictive_evidence,
    has_predictive_utility,
    history_events_path,
    load_history_events,
    normalize_apply_mode,
    normalize_text_list,
    relative_repo_path,
    sanitize_run_id,
    supporting_events_for_action,
    suppress_resolved_actions,
    utc_now_iso,
)
from local_kb.consolidate_suggestions import (
    annotate_actions_with_apply_eligibility,
    build_cross_index_actions,
    build_related_card_actions,
    describe_apply_eligibility,
)
from local_kb.history import build_history_event, record_history_event
from local_kb.i18n import ZH_CN, merge_i18n_payload, missing_i18n_fields
from local_kb.i18n_maintenance import build_i18n_actions, load_i18n_plan, translation_for_entry
from local_kb.semantic_review import (
    SEMANTIC_REVIEW_AUTO_APPLY_DECISIONS,
    SEMANTIC_REVIEW_REMOVAL_DECISIONS,
    SEMANTIC_REVIEW_SURFACE_DECISIONS,
    is_semantic_review_action,
    is_trusted_card,
    normalize_semantic_decision,
    normalize_semantic_evidence_event_ids,
    normalize_semantic_review_plan,
    normalize_semantic_risk,
    normalize_semantic_utility_assessment,
    semantic_review_changed_fields,
    semantic_review_confidence,
    semantic_review_decisions_by_action_key,
    semantic_review_entry_storage_path,
    semantic_review_needs_i18n_followup,
    semantic_review_updated_fields,
)
from local_kb.store import candidate_dir, write_yaml_file


def consolidation_run_dir(repo_root: Path, run_id: str) -> Path:
    return repo_root / "kb" / "history" / "consolidation" / run_id


def action_stub_dir(repo_root: Path, run_id: str) -> Path:
    return consolidation_run_dir(repo_root, run_id) / "actions"


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def build_snapshot_payload(
    repo_root: Path,
    run_id: str,
    generated_at: str,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "local-kb-consolidation-snapshot",
        "run_id": run_id,
        "generated_at": generated_at,
        "history_path": relative_repo_path(repo_root, history_events_path(repo_root)),
        "event_count": len(events),
        "events": events,
    }


def build_proposal_payload(
    repo_root: Path,
    run_id: str,
    generated_at: str,
    actions: list[dict[str, Any]],
    event_count: int,
    max_events: int | None,
) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "local-kb-consolidation-proposal",
        "run_id": run_id,
        "generated_at": generated_at,
        "history_path": relative_repo_path(repo_root, history_events_path(repo_root)),
        "event_count": event_count,
        "candidate_action_count": len(actions),
        "actions": actions,
        "notes": CONSOLIDATION_NOTES,
    }
    if max_events is not None:
        payload["max_events"] = max_events
    return payload


def action_stub_filename(action_key: str, index: int) -> str:
    base_name = slugify(action_key.replace("::", "-"))[:72] or f"action-{index + 1}"
    action_hash = hashlib.sha1(action_key.encode("utf-8")).hexdigest()[:8]
    return f"{index + 1:03d}-{base_name}-{action_hash}.json"


def build_action_stub_payload(
    action: dict[str, Any],
    run_id: str,
    generated_at: str,
) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "local-kb-consolidation-action-stub",
        "run_id": run_id,
        "generated_at": generated_at,
        "action_key": action["action_key"],
        "action_type": action["action_type"],
        "target": dict(action["target"]),
        "priority_score": int(action["priority_score"]),
        "event_count": int(action["event_count"]),
        "event_ids": list(action.get("event_ids", [])),
        "routes": list(action.get("routes", [])),
        "task_summaries": list(action.get("task_summaries", [])),
        "signals": dict(action.get("signals", {})),
        "suggested_artifact_kind": str(action.get("suggested_artifact_kind", "")),
        "apply_eligibility": dict(action.get("apply_eligibility", {})),
        "recommended_next_step": str(action.get("recommended_next_step", "")),
        "ai_decision_required": bool(action.get("ai_decision_required", True)),
    }
    if action.get("provenance"):
        payload["provenance"] = dict(action["provenance"])
    if action.get("timeline_summary"):
        payload["timeline_summary"] = dict(action["timeline_summary"])
    if action.get("predictive_evidence_summary"):
        payload["predictive_evidence_summary"] = dict(action["predictive_evidence_summary"])
    if action.get("candidate_scaffold_preview"):
        payload["candidate_scaffold_preview"] = dict(action["candidate_scaffold_preview"])
    if action.get("suggested_confidence_change"):
        payload["suggested_confidence_change"] = dict(action["suggested_confidence_change"])
    if action.get("disposition_suggestion"):
        payload["disposition_suggestion"] = dict(action["disposition_suggestion"])
    if action.get("cross_index_suggestion"):
        payload["cross_index_suggestion"] = dict(action["cross_index_suggestion"])
    if action.get("related_card_suggestion"):
        payload["related_card_suggestion"] = dict(action["related_card_suggestion"])
    if action.get("split_review_suggestion"):
        payload["split_review_suggestion"] = dict(action["split_review_suggestion"])
    if action.get("i18n_suggestion"):
        payload["i18n_suggestion"] = dict(action["i18n_suggestion"])
    if action.get("semantic_review_suggestion"):
        payload["semantic_review_suggestion"] = dict(action["semantic_review_suggestion"])
    return payload


def emit_action_stubs(
    repo_root: Path,
    run_id: str,
    generated_at: str,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    target_dir = action_stub_dir(repo_root, run_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    stub_paths: list[str] = []
    for index, action in enumerate(actions):
        stub_path = target_dir / action_stub_filename(str(action["action_key"]), index)
        stub_payload = build_action_stub_payload(
            action=action,
            run_id=run_id,
            generated_at=generated_at,
        )
        write_json_file(stub_path, stub_payload)
        stub_paths.append(relative_repo_path(repo_root, stub_path))

    return {
        "action_stub_dir": relative_repo_path(repo_root, target_dir),
        "action_stub_count": len(stub_paths),
        "action_stub_paths": stub_paths,
    }


def emit_artifacts(
    repo_root: Path,
    run_id: str,
    generated_at: str,
    snapshot_payload: dict[str, Any],
    proposal_payload: dict[str, Any],
) -> dict[str, Any]:
    run_dir = consolidation_run_dir(repo_root, run_id)
    snapshot_path = run_dir / "snapshot.json"
    proposal_path = run_dir / "proposal.json"
    write_json_file(snapshot_path, snapshot_payload)
    write_json_file(proposal_path, proposal_payload)
    action_stub_artifacts = emit_action_stubs(
        repo_root=repo_root,
        run_id=run_id,
        generated_at=generated_at,
        actions=list(proposal_payload.get("actions", [])),
    )
    artifact_paths: dict[str, Any] = {
        "run_dir": relative_repo_path(repo_root, run_dir),
        "snapshot_path": relative_repo_path(repo_root, snapshot_path),
        "proposal_path": relative_repo_path(repo_root, proposal_path),
    }
    artifact_paths.update(action_stub_artifacts)
    return artifact_paths


def route_candidate_id(route_ref: str) -> str:
    route_slug = slugify(route_ref.replace("/", "-"))[:32] or "route"
    route_hash = hashlib.sha1(route_ref.encode("utf-8")).hexdigest()[:8]
    return f"cand-auto-{route_slug}-{route_hash}"


def summarize_examples(values: list[str], limit: int = 3) -> str:
    if not values:
        return ""
    clipped = values[:limit]
    suffix = " ..." if len(values) > limit else ""
    return "; ".join(clipped) + suffix


def build_auto_candidate_entry(
    action: dict[str, Any],
    supporting_events: list[dict[str, Any]],
    run_id: str,
    generated_at: str,
) -> dict[str, Any]:
    route_ref = str(action["target"]["ref"])
    route_segments = parse_route_segments(route_ref)
    route_title = " / ".join(route_segments) if route_segments else route_ref
    task_summaries = collect_task_summaries(supporting_events)
    updated_at = generated_at[:10]
    scaffold_preview = action.get("candidate_scaffold_preview", {})
    if not isinstance(scaffold_preview, dict):
        scaffold_preview = {}
    if_block = scaffold_preview.get("if", {})
    if not isinstance(if_block, dict):
        if_block = {}
    action_block = scaffold_preview.get("action", {})
    if not isinstance(action_block, dict):
        action_block = {}
    predict_block = scaffold_preview.get("predict", {})
    if not isinstance(predict_block, dict):
        predict_block = {}
    use_block = scaffold_preview.get("use", {})
    if not isinstance(use_block, dict):
        use_block = {}
    alternatives = [
        item
        for item in predict_block.get("alternatives", [])
        if isinstance(item, dict)
        and (str(item.get("when", "") or "").strip() or str(item.get("result", "") or "").strip())
    ]
    event_count = int(action["event_count"])
    complete_predictive_count = sum(1 for event in supporting_events if has_predictive_evidence(event))
    future_utility_count = sum(1 for event in supporting_events if has_predictive_utility(event))
    seed_candidate = event_count == 1 and future_utility_count >= 1
    tags = sorted(set(route_segments + ["auto-generated", "consolidation"]))
    if seed_candidate:
        tags = sorted(set(tags + ["seed-candidate", "low-confidence"]))
    if alternatives:
        tags = sorted(set(tags + ["contrastive-evidence"]))
    return {
        "id": route_candidate_id(route_ref),
        "title": str(scaffold_preview.get("title", "") or f"Repeated route gap in {route_title}"),
        "type": "model",
        "scope": AUTO_CANDIDATE_SCOPE,
        "domain_path": route_segments,
        "cross_index": [],
        "tags": tags,
        "trigger_keywords": sorted(set(route_segments)),
        "if": {
            "notes": str(
                if_block.get(
                    "notes",
                    (
                        f"Auto-created from {action['event_count']} grouped new-candidate observations. "
                        f"Example task summaries: {summarize_examples(task_summaries)}"
                    ).strip(),
                )
                or ""
            ).strip()
        },
        "action": {
            "description": str(
                action_block.get(
                    "description",
                    f"Handle tasks routed through {route_title} without a consolidated KB card.",
                )
                or ""
            ).strip()
        },
        "predict": {
            "expected_result": str(
                predict_block.get(
                    "expected_result",
                    (
                        f"Grouped observations suggest Codex will keep missing reusable guidance for {route_title} "
                        "until a route-specific card is authored."
                    ),
                )
                or ""
            ).strip(),
            "alternatives": alternatives,
        },
        "use": {
            "guidance": str(
                use_block.get(
                    "guidance",
                    (
                        "Review the cited observations and replace this auto-created scaffold with a specific "
                        "predictive card before any promotion."
                    ),
                )
                or ""
            ).strip()
        },
        "confidence": 0.4 if seed_candidate else round(min(0.75, 0.45 + (0.05 * event_count)), 2),
        "source": [
            {
                "origin": "auto consolidation apply",
                "date": updated_at,
                "run_id": run_id,
                "route": route_ref,
                "candidate_creation_mode": "seed" if seed_candidate else "grouped",
                "complete_predictive_event_count": complete_predictive_count,
                "future_utility_event_count": future_utility_count,
                "event_ids": list(action["event_ids"]),
            }
        ],
        "status": "candidate",
        "updated_at": updated_at,
    }


def build_empty_apply_summary(apply_mode: str) -> dict[str, Any]:
    return {
        "apply_mode": apply_mode,
        "created_candidate_count": 0,
        "updated_entry_count": 0,
        "skipped_action_count": 0,
        "created_candidates": [],
        "updated_entries": [],
        "skipped_actions": [],
    }


def _normalize_ordered_text_list(value: Any) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in normalize_string_list(value):
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _build_skipped_apply_action(action: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "action_key": action["action_key"],
        "action_type": action["action_type"],
        "target": dict(action["target"]),
        "reason": reason,
        "event_ids": list(action.get("event_ids", [])),
    }


def apply_new_candidate_actions(
    repo_root: Path,
    actions: list[dict[str, Any]],
    events: list[dict[str, Any]],
    run_id: str,
    generated_at: str,
) -> dict[str, Any]:
    indexed_events = events_by_id(events)
    created_candidates: list[dict[str, Any]] = []
    skipped_actions: list[dict[str, Any]] = []
    i18n_followup_entries: list[dict[str, Any]] = []

    for action in actions:
        supporting_events = supporting_events_for_action(action, indexed_events)
        eligibility = action.get("apply_eligibility") or describe_apply_eligibility(action, supporting_events)
        if action.get("action_type") != "consider-new-candidate":
            supported_mode = str(eligibility.get("supported_mode", "") or "")
            mode_label = supported_mode or "another"
            skipped_actions.append(
                {
                    "action_key": action["action_key"],
                    "action_type": action["action_type"],
                    "target": dict(action["target"]),
                    "reason": (
                        f"Action belongs to {mode_label} apply mode; "
                        "new-candidates apply only creates route candidate scaffolds."
                    ).strip(),
                    "event_ids": list(action["event_ids"]),
                }
            )
            continue
        if not eligibility.get("eligible", False):
            skipped_actions.append(
                {
                    "action_key": action["action_key"],
                    "action_type": action["action_type"],
                    "target": dict(action["target"]),
                    "reason": eligibility["reason"],
                    "event_ids": list(action["event_ids"]),
                }
            )
            continue

        entry = build_auto_candidate_entry(
            action=action,
            supporting_events=supporting_events,
            run_id=run_id,
            generated_at=generated_at,
        )
        target_path = candidate_dir(repo_root) / f"{entry['id']}.yaml"
        relative_target_path = relative_repo_path(repo_root, target_path)
        if target_path.exists():
            skipped_actions.append(
                {
                    "action_key": action["action_key"],
                    "action_type": action["action_type"],
                    "target": dict(action["target"]),
                    "reason": f"Candidate file already exists: {relative_target_path}",
                    "event_ids": list(action["event_ids"]),
                }
            )
            continue

        write_yaml_file(target_path, entry)
        missing_i18n = missing_i18n_fields(entry, ZH_CN)
        if missing_i18n:
            i18n_followup_entries.append(
                {
                    "entry_id": entry["id"],
                    "entry_path": relative_target_path,
                    "missing_i18n_fields": missing_i18n,
                }
            )
        history_event = build_history_event(
            "candidate-created",
            source={
                "kind": "consolidation-apply",
                "agent": "kb-consolidate",
                "run_id": run_id,
            },
            target={
                "kind": "candidate-entry",
                "entry_id": entry["id"],
                "entry_path": relative_target_path,
                "scope": entry["scope"],
                "domain_path": entry["domain_path"],
            },
            rationale=f"Applied grouped consider-new-candidate action {action['action_key']}",
            context={
                "action_key": action["action_key"],
                "event_count": action["event_count"],
                "event_ids": list(action["event_ids"]),
                "auto_apply_mode": APPLY_MODE_NEW_CANDIDATES,
                "title": entry["title"],
                "entry_type": entry["type"],
            },
        )
        record_history_event(repo_root, history_event)
        created_candidates.append(
            {
                "action_key": action["action_key"],
                "entry_id": entry["id"],
                "entry_path": relative_target_path,
                "event_ids": list(action["event_ids"]),
                "missing_i18n_fields": missing_i18n,
            }
        )

    i18n_followup = {
        "required": bool(i18n_followup_entries),
        "language": ZH_CN,
        "missing_entry_count": len(i18n_followup_entries),
        "entries": i18n_followup_entries,
        "recommended_apply_mode": APPLY_MODE_I18N_ZH_CN,
        "reason": (
            "New candidate entries keep English canonical fields only; author a zh-CN translation plan "
            "and run i18n apply after candidate creation."
        ),
    }
    return {
        "apply_mode": APPLY_MODE_NEW_CANDIDATES,
        "created_candidate_count": len(created_candidates),
        "updated_entry_count": 0,
        "skipped_action_count": len(skipped_actions),
        "created_candidates": created_candidates,
        "updated_entries": [],
        "skipped_actions": skipped_actions,
        "i18n_followup": i18n_followup,
    }


def _resolve_related_card_apply_context(
    action: dict[str, Any],
    entry_lookup: dict[str, dict[str, Any]],
    entry_path_lookup: dict[str, Path],
) -> tuple[dict[str, Any] | None, str | None]:
    suggestion = action.get("related_card_suggestion", {})
    eligibility = action.get("apply_eligibility", {})
    if not eligibility.get("eligible", False):
        return None, str(
            eligibility.get("reason", "") or "Related-card suggestion is not eligible for apply."
        )

    entry_id = str(action.get("target", {}).get("ref", "") or "")
    if entry_id not in entry_lookup or entry_id not in entry_path_lookup:
        return None, f"Entry not found for related-card update: {entry_id}"

    payload = dict(entry_lookup[entry_id])
    current_related_cards = normalize_text_list(payload.get("related_cards", []))
    suggested_related_cards = normalize_text_list(suggestion.get("suggested_related_cards", []))
    if suggested_related_cards == current_related_cards:
        return None, "Related-card field already matches the current suggestion."

    return {
        "entry_id": entry_id,
        "payload": payload,
        "target_path": entry_path_lookup[entry_id],
        "current_related_cards": current_related_cards,
        "suggested_related_cards": suggested_related_cards,
    }, None


def _apply_single_related_card_action(
    repo_root: Path,
    action: dict[str, Any],
    update_context: dict[str, Any],
    run_id: str,
    updated_at: str,
) -> dict[str, Any]:
    payload = dict(update_context["payload"])
    current_related_cards = list(update_context["current_related_cards"])
    suggested_related_cards = list(update_context["suggested_related_cards"])
    target_path = update_context["target_path"]
    entry_id = str(update_context["entry_id"])

    if suggested_related_cards:
        payload["related_cards"] = suggested_related_cards
    else:
        payload.pop("related_cards", None)
    payload["updated_at"] = updated_at

    relative_target_path = relative_repo_path(repo_root, target_path)
    write_yaml_file(target_path, payload)

    history_event = build_history_event(
        "related-cards-updated",
        source={
            "kind": "consolidation-apply",
            "agent": "kb-consolidate",
            "run_id": run_id,
        },
        target={
            "kind": "entry",
            "entry_id": entry_id,
            "entry_path": relative_target_path,
            "scope": str(payload.get("scope", "") or ""),
            "domain_path": parse_route_segments(payload.get("domain_path", [])),
        },
        rationale=f"Applied grouped related-card action {action['action_key']}",
        context={
            "action_key": action["action_key"],
            "event_count": int(action.get("event_count", 0) or 0),
            "event_ids": list(action.get("event_ids", [])),
            "auto_apply_mode": APPLY_MODE_RELATED_CARDS,
            "previous_related_cards": current_related_cards,
            "updated_related_cards": suggested_related_cards,
        },
    )
    record_history_event(repo_root, history_event)
    return {
        "action_key": action["action_key"],
        "entry_id": entry_id,
        "entry_path": relative_target_path,
        "previous_related_cards": current_related_cards,
        "updated_related_cards": suggested_related_cards,
        "event_ids": list(action.get("event_ids", [])),
    }


def _resolve_cross_index_apply_context(
    action: dict[str, Any],
    entry_lookup: dict[str, dict[str, Any]],
    entry_path_lookup: dict[str, Path],
) -> tuple[dict[str, Any] | None, str | None]:
    suggestion = action.get("cross_index_suggestion", {})
    eligibility = action.get("apply_eligibility", {})
    if not eligibility.get("eligible", False):
        return None, str(
            eligibility.get("reason", "") or "Cross-index suggestion is not eligible for apply."
        )

    entry_id = str(action.get("target", {}).get("ref", "") or "")
    if entry_id not in entry_lookup or entry_id not in entry_path_lookup:
        return None, f"Entry not found for cross-index update: {entry_id}"

    payload = dict(entry_lookup[entry_id])
    current_cross_index = _normalize_ordered_text_list(payload.get("cross_index", []))
    suggested_cross_index = _normalize_ordered_text_list(suggestion.get("suggested_cross_index", []))
    if suggested_cross_index == current_cross_index:
        return None, "Cross-index field already matches the current suggestion."

    return {
        "entry_id": entry_id,
        "payload": payload,
        "target_path": entry_path_lookup[entry_id],
        "current_cross_index": current_cross_index,
        "suggested_cross_index": suggested_cross_index,
    }, None


def _apply_single_cross_index_action(
    repo_root: Path,
    action: dict[str, Any],
    update_context: dict[str, Any],
    run_id: str,
    updated_at: str,
) -> dict[str, Any]:
    payload = dict(update_context["payload"])
    current_cross_index = list(update_context["current_cross_index"])
    suggested_cross_index = list(update_context["suggested_cross_index"])
    target_path = update_context["target_path"]
    entry_id = str(update_context["entry_id"])

    payload["cross_index"] = suggested_cross_index
    payload["updated_at"] = updated_at

    relative_target_path = relative_repo_path(repo_root, target_path)
    write_yaml_file(target_path, payload)

    history_event = build_history_event(
        "cross-index-updated",
        source={
            "kind": "consolidation-apply",
            "agent": "kb-consolidate",
            "run_id": run_id,
        },
        target={
            "kind": "entry",
            "entry_id": entry_id,
            "entry_path": relative_target_path,
            "scope": str(payload.get("scope", "") or ""),
            "domain_path": parse_route_segments(payload.get("domain_path", [])),
        },
        rationale=f"Applied grouped cross-index action {action['action_key']}",
        context={
            "action_key": action["action_key"],
            "event_count": int(action.get("event_count", 0) or 0),
            "event_ids": list(action.get("event_ids", [])),
            "auto_apply_mode": APPLY_MODE_CROSS_INDEX,
            "previous_cross_index": current_cross_index,
            "updated_cross_index": suggested_cross_index,
        },
    )
    record_history_event(repo_root, history_event)
    return {
        "action_key": action["action_key"],
        "entry_id": entry_id,
        "entry_path": relative_target_path,
        "previous_cross_index": current_cross_index,
        "updated_cross_index": suggested_cross_index,
        "event_ids": list(action.get("event_ids", [])),
    }


def apply_related_card_actions(
    repo_root: Path,
    actions: list[dict[str, Any]],
    run_id: str,
    generated_at: str,
) -> dict[str, Any]:
    entry_lookup = build_entry_lookup(repo_root)
    entry_path_lookup = build_entry_path_lookup(repo_root)
    updated_entries: list[dict[str, Any]] = []
    skipped_actions: list[dict[str, Any]] = []
    updated_at = generated_at[:10]

    for action in actions:
        if action.get("action_type") != "review-related-cards":
            skipped_actions.append(
                _build_skipped_apply_action(
                    action,
                    "Apply mode related-cards only updates related-card review actions.",
                )
            )
            continue

        update_context, skip_reason = _resolve_related_card_apply_context(
            action=action,
            entry_lookup=entry_lookup,
            entry_path_lookup=entry_path_lookup,
        )
        if skip_reason:
            skipped_actions.append(_build_skipped_apply_action(action, skip_reason))
            continue

        updated_entries.append(
            _apply_single_related_card_action(
                repo_root=repo_root,
                action=action,
                update_context=update_context,
                run_id=run_id,
                updated_at=updated_at,
            )
        )

    return {
        "apply_mode": APPLY_MODE_RELATED_CARDS,
        "created_candidate_count": 0,
        "updated_entry_count": len(updated_entries),
        "skipped_action_count": len(skipped_actions),
        "created_candidates": [],
        "updated_entries": updated_entries,
        "skipped_actions": skipped_actions,
    }


def apply_cross_index_actions(
    repo_root: Path,
    actions: list[dict[str, Any]],
    run_id: str,
    generated_at: str,
) -> dict[str, Any]:
    entry_lookup = build_entry_lookup(repo_root)
    entry_path_lookup = build_entry_path_lookup(repo_root)
    updated_entries: list[dict[str, Any]] = []
    skipped_actions: list[dict[str, Any]] = []
    updated_at = generated_at[:10]

    for action in actions:
        if action.get("action_type") != "review-cross-index":
            skipped_actions.append(
                _build_skipped_apply_action(
                    action,
                    "Apply mode cross-index only updates cross-index review actions.",
                )
            )
            continue

        update_context, skip_reason = _resolve_cross_index_apply_context(
            action=action,
            entry_lookup=entry_lookup,
            entry_path_lookup=entry_path_lookup,
        )
        if skip_reason:
            skipped_actions.append(_build_skipped_apply_action(action, skip_reason))
            continue

        updated_entries.append(
            _apply_single_cross_index_action(
                repo_root=repo_root,
                action=action,
                update_context=update_context,
                run_id=run_id,
                updated_at=updated_at,
            )
        )

    return {
        "apply_mode": APPLY_MODE_CROSS_INDEX,
        "created_candidate_count": 0,
        "updated_entry_count": len(updated_entries),
        "skipped_action_count": len(skipped_actions),
        "created_candidates": [],
        "updated_entries": updated_entries,
        "skipped_actions": skipped_actions,
    }


def apply_i18n_actions(
    repo_root: Path,
    actions: list[dict[str, Any]],
    run_id: str,
    generated_at: str,
    i18n_plan_path: Path | None,
) -> dict[str, Any]:
    entry_lookup = build_entry_lookup(repo_root)
    entry_path_lookup = build_entry_path_lookup(repo_root)
    plan = load_i18n_plan(i18n_plan_path)
    updated_entries: list[dict[str, Any]] = []
    skipped_actions: list[dict[str, Any]] = []
    updated_at = generated_at[:10]
    plan_language = str(plan.get("language") or "")
    if i18n_plan_path:
        try:
            relative_plan_path = relative_repo_path(repo_root, i18n_plan_path)
        except ValueError:
            relative_plan_path = str(i18n_plan_path)
    else:
        relative_plan_path = ""

    for action in actions:
        if action.get("action_type") != "review-i18n":
            if action.get("action_type") == "review-route-i18n":
                skipped_actions.append(
                    _build_skipped_apply_action(
                        action,
                        (
                            "Route display labels require an AI-authored code patch; "
                            "i18n-zh-CN apply only updates entry text translations."
                        ),
                    )
                )
                continue
            skipped_actions.append(
                _build_skipped_apply_action(
                    action,
                    "Apply mode i18n-zh-CN only updates i18n review actions.",
                )
            )
            continue

        if plan_language != ZH_CN:
            skipped_actions.append(_build_skipped_apply_action(action, "i18n plan language must be zh-CN."))
            continue

        entry_id = str(action.get("target", {}).get("ref", "") or "").strip()
        if entry_id not in entry_lookup or entry_id not in entry_path_lookup:
            skipped_actions.append(_build_skipped_apply_action(action, f"Entry not found for i18n update: {entry_id}"))
            continue

        translation_payload = translation_for_entry(plan, entry_id)
        if not translation_payload:
            skipped_actions.append(
                _build_skipped_apply_action(
                    action,
                    "No AI-authored translation payload was provided for this entry.",
                )
            )
            continue

        current_payload = dict(entry_lookup[entry_id])
        previous_missing_fields = missing_i18n_fields(current_payload, ZH_CN)
        merged_payload = merge_i18n_payload(current_payload, ZH_CN, translation_payload)
        new_missing_fields = missing_i18n_fields(merged_payload, ZH_CN)
        if merged_payload.get("i18n") == current_payload.get("i18n"):
            skipped_actions.append(_build_skipped_apply_action(action, "i18n payload already matches the current entry."))
            continue

        merged_payload["updated_at"] = updated_at
        target_path = entry_path_lookup[entry_id]
        relative_target_path = relative_repo_path(repo_root, target_path)
        write_yaml_file(target_path, merged_payload)

        history_event = build_history_event(
            "i18n-updated",
            source={
                "kind": "consolidation-apply",
                "agent": "kb-consolidate",
                "run_id": run_id,
            },
            target={
                "kind": "entry",
                "entry_id": entry_id,
                "entry_path": relative_target_path,
                "scope": str(merged_payload.get("scope", "") or ""),
                "domain_path": parse_route_segments(merged_payload.get("domain_path", [])),
            },
            rationale=f"Applied AI-authored zh-CN i18n plan for {action['action_key']}",
            context={
                "action_key": action["action_key"],
                "auto_apply_mode": APPLY_MODE_I18N_ZH_CN,
                "language": ZH_CN,
                "i18n_plan_path": relative_plan_path,
                "previous_missing_i18n_fields": previous_missing_fields,
                "remaining_missing_i18n_fields": new_missing_fields,
            },
        )
        record_history_event(repo_root, history_event)
        updated_entries.append(
            {
                "action_key": action["action_key"],
                "entry_id": entry_id,
                "entry_path": relative_target_path,
                "language": ZH_CN,
                "previous_missing_i18n_fields": previous_missing_fields,
                "remaining_missing_i18n_fields": new_missing_fields,
            }
        )

    return {
        "apply_mode": APPLY_MODE_I18N_ZH_CN,
        "created_candidate_count": 0,
        "updated_entry_count": len(updated_entries),
        "skipped_action_count": len(skipped_actions),
        "created_candidates": [],
        "updated_entries": updated_entries,
        "skipped_actions": skipped_actions,
        "i18n_plan_path": relative_plan_path,
    }


def _semantic_review_plan_path_label(repo_root: Path, semantic_review_plan_path: Path | None) -> str:
    if semantic_review_plan_path is None:
        return ""
    try:
        return relative_repo_path(repo_root, semantic_review_plan_path)
    except ValueError:
        return str(semantic_review_plan_path)


def _semantic_review_skip(action: dict[str, Any], reason: str) -> dict[str, Any]:
    return _build_skipped_apply_action(action, reason)


def _semantic_review_requires_trusted_budget(
    current_payload: dict[str, Any],
    decision_name: str,
    updated_payload: dict[str, Any] | None = None,
) -> bool:
    if is_trusted_card(current_payload):
        return True
    if decision_name in {"promote", "deprecate", "demote"}:
        return True
    if updated_payload is not None and is_trusted_card(updated_payload):
        return True
    return False


def _semantic_review_append_source(
    payload: dict[str, Any],
    *,
    run_id: str,
    updated_at: str,
    action_key: str,
    decision_name: str,
    evidence_event_ids: list[str],
) -> None:
    source = payload.get("source", [])
    if not isinstance(source, list):
        source = [source] if source else []
    source.append(
        {
            "origin": "semantic review apply",
            "date": updated_at,
            "run_id": run_id,
            "action_key": action_key,
            "decision": decision_name,
            "event_ids": evidence_event_ids,
        }
    )
    payload["source"] = source


def _semantic_review_apply_updates(
    current_payload: dict[str, Any],
    updates: dict[str, Any],
    decision_name: str,
) -> tuple[dict[str, Any] | None, str]:
    payload = deepcopy(current_payload)
    if decision_name == "adjust-confidence":
        confidence = semantic_review_confidence(updates.get("confidence"))
        if confidence is None:
            return None, "adjust-confidence requires updated_fields.confidence between 0 and 1."
        payload["confidence"] = confidence
    elif decision_name == "deprecate":
        payload["status"] = "deprecated"
        if "confidence" in updates:
            confidence = semantic_review_confidence(updates.get("confidence"))
            if confidence is None:
                return None, "deprecate confidence must be between 0 and 1 when provided."
            payload["confidence"] = confidence
    else:
        for field, value in updates.items():
            if field == "confidence":
                confidence = semantic_review_confidence(value)
                if confidence is None:
                    return None, "confidence must be between 0 and 1."
                payload[field] = confidence
                continue
            if field == "domain_path":
                payload[field] = parse_route_segments(value)
                continue
            if field in {"cross_index", "related_cards", "tags", "trigger_keywords"}:
                payload[field] = _normalize_ordered_text_list(value)
                continue
            payload[field] = value
    return payload, ""


def _semantic_review_target_path_for_decision(
    repo_root: Path,
    current_path: Path,
    payload: dict[str, Any],
    decision_name: str,
) -> Path:
    if decision_name == "promote":
        return semantic_review_entry_storage_path(repo_root, payload)
    if decision_name == "demote":
        return semantic_review_entry_storage_path(repo_root, payload, force_candidates=True)
    return current_path


def _semantic_review_validate_decision(
    action: dict[str, Any],
    decision: dict[str, Any],
    current_payload: dict[str, Any],
) -> tuple[str, list[str], str, dict[str, str], str]:
    decision_name = normalize_semantic_decision(decision.get("decision"))
    if not decision_name:
        return "", [], "", {}, "Unsupported or missing semantic review decision."
    if decision_name not in SEMANTIC_REVIEW_AUTO_APPLY_DECISIONS:
        return decision_name, [], "", {}, f"Decision {decision_name} is proposal-only in the current apply tool."
    if not bool(decision.get("apply", False)):
        return decision_name, [], "", {}, "Semantic review decisions must set apply: true before they are recorded or applied."

    entry_id = str(action.get("target", {}).get("ref", "") or "").strip()
    decision_entry_id = str(decision.get("entry_id", "") or "").strip()
    if decision_entry_id and decision_entry_id != entry_id:
        return decision_name, [], "", {}, f"Decision entry_id {decision_entry_id} does not match action target {entry_id}."

    evidence_event_ids = normalize_semantic_evidence_event_ids(decision)
    action_event_ids = {str(event_id).strip() for event_id in action.get("event_ids", []) if str(event_id).strip()}
    if not evidence_event_ids:
        return decision_name, [], "", {}, "Semantic review decisions require evidence_event_ids."
    if action_event_ids and not set(evidence_event_ids).issubset(action_event_ids):
        return decision_name, evidence_event_ids, "", {}, "Semantic review evidence_event_ids must come from the current action."

    rationale = str(decision.get("rationale", "") or "").strip()
    expected_effect = str(decision.get("expected_retrieval_effect", "") or "").strip()
    rollback_note = str(decision.get("rollback_note", "") or "").strip()
    if not rationale:
        return decision_name, evidence_event_ids, "", {}, "Semantic review decisions require rationale."
    utility_assessment = normalize_semantic_utility_assessment(decision.get("utility_assessment"))
    utility_judgment = utility_assessment.get("judgment", "")
    if not utility_judgment:
        return decision_name, evidence_event_ids, "", utility_assessment, "Semantic review decisions require utility_assessment.judgment."
    if decision_name in SEMANTIC_REVIEW_SURFACE_DECISIONS and utility_judgment != "useful":
        return (
            decision_name,
            evidence_event_ids,
            "",
            utility_assessment,
            "Surface-retaining semantic review decisions require utility_assessment.judgment: useful.",
        )
    if decision_name in SEMANTIC_REVIEW_REMOVAL_DECISIONS and utility_judgment == "useful":
        return (
            decision_name,
            evidence_event_ids,
            "",
            utility_assessment,
            "Demote/deprecate semantic review decisions require a non-useful utility assessment.",
        )
    if decision_name != "keep" and not expected_effect:
        return decision_name, evidence_event_ids, "", utility_assessment, "Semantic review file changes require expected_retrieval_effect."
    if decision_name != "keep" and not rollback_note:
        return decision_name, evidence_event_ids, "", utility_assessment, "Semantic review file changes require rollback_note."

    risk = normalize_semantic_risk(
        decision.get("risk"),
        trusted_surface=is_trusted_card(current_payload),
        decision=decision_name,
    )
    return decision_name, evidence_event_ids, risk, utility_assessment, ""


def _record_semantic_review_event(
    repo_root: Path,
    *,
    run_id: str,
    action: dict[str, Any],
    decision: dict[str, Any],
    decision_name: str,
    risk: str,
    utility_assessment: dict[str, str],
    evidence_event_ids: list[str],
    current_payload: dict[str, Any],
    updated_payload: dict[str, Any],
    current_path: Path,
    updated_path: Path,
    changed_fields: list[str],
    plan_path_label: str,
    trusted_card_limit: int,
    applied_file_change: bool,
) -> None:
    entry_id = str(updated_payload.get("id") or current_payload.get("id") or action.get("target", {}).get("ref") or "")
    history_event = build_history_event(
        "semantic-reviewed",
        source={
            "kind": "consolidation-apply",
            "agent": "kb-consolidate",
            "run_id": run_id,
        },
        target={
            "kind": "entry",
            "entry_id": entry_id,
            "entry_path": relative_repo_path(repo_root, updated_path),
            "scope": str(updated_payload.get("scope", "") or ""),
            "domain_path": parse_route_segments(updated_payload.get("domain_path", [])),
        },
        rationale=str(decision.get("rationale", "") or "").strip(),
        context={
            "action_key": action["action_key"],
            "resolved_action_key": action["action_key"],
            "resolved_event_ids": evidence_event_ids,
            "auto_apply_mode": APPLY_MODE_SEMANTIC_REVIEW,
            "semantic_review_plan_path": plan_path_label,
            "decision": decision_name,
            "risk": risk,
            "utility_assessment": dict(utility_assessment),
            "applied_file_change": applied_file_change,
            "changed_fields": changed_fields,
            "previous_entry_path": relative_repo_path(repo_root, current_path),
            "updated_entry_path": relative_repo_path(repo_root, updated_path),
            "previous_status": str(current_payload.get("status", "") or ""),
            "updated_status": str(updated_payload.get("status", "") or ""),
            "previous_confidence": current_payload.get("confidence"),
            "updated_confidence": updated_payload.get("confidence"),
            "expected_retrieval_effect": str(decision.get("expected_retrieval_effect", "") or "").strip(),
            "rollback_note": str(decision.get("rollback_note", "") or "").strip(),
            "trusted_card_limit": trusted_card_limit,
        },
    )
    record_history_event(repo_root, history_event)


def apply_semantic_review_actions(
    repo_root: Path,
    actions: list[dict[str, Any]],
    run_id: str,
    generated_at: str,
    semantic_review_plan_path: Path | None,
) -> dict[str, Any]:
    entry_lookup = build_entry_lookup(repo_root)
    entry_path_lookup = build_entry_path_lookup(repo_root)
    plan = normalize_semantic_review_plan(semantic_review_plan_path)
    decisions_by_action_key = semantic_review_decisions_by_action_key(plan)
    plan_path_label = _semantic_review_plan_path_label(repo_root, semantic_review_plan_path)
    trusted_card_limit = int(plan.get("trusted_card_limit", 3) or 0)
    trusted_entry_ids_modified: set[str] = set()
    reviewed_entries: list[dict[str, Any]] = []
    updated_entries: list[dict[str, Any]] = []
    skipped_actions: list[dict[str, Any]] = []
    i18n_followup_entries: list[dict[str, Any]] = []
    updated_at = generated_at[:10]

    for action in actions:
        if not is_semantic_review_action(action):
            skipped_actions.append(
                _semantic_review_skip(
                    action,
                    "Apply mode semantic-review only processes entry semantic review actions.",
                )
            )
            continue

        action_key = str(action.get("action_key", "") or "").strip()
        decision = decisions_by_action_key.get(action_key)
        if not decision:
            skipped_actions.append(
                _semantic_review_skip(
                    action,
                    "No AI-authored semantic review decision was provided for this action.",
                )
            )
            continue

        entry_id = str(action.get("target", {}).get("ref", "") or "").strip()
        if entry_id not in entry_lookup or entry_id not in entry_path_lookup:
            skipped_actions.append(_semantic_review_skip(action, f"Entry not found for semantic review: {entry_id}"))
            continue

        current_payload = deepcopy(entry_lookup[entry_id])
        current_path = entry_path_lookup[entry_id]
        decision_name, evidence_event_ids, risk, utility_assessment, validation_error = _semantic_review_validate_decision(
            action=action,
            decision=decision,
            current_payload=current_payload,
        )
        if validation_error:
            skipped_actions.append(_semantic_review_skip(action, validation_error))
            continue

        if decision_name == "keep":
            _record_semantic_review_event(
                repo_root,
                run_id=run_id,
                action=action,
                decision=decision,
                decision_name=decision_name,
                risk=risk,
                utility_assessment=utility_assessment,
                evidence_event_ids=evidence_event_ids,
                current_payload=current_payload,
                updated_payload=current_payload,
                current_path=current_path,
                updated_path=current_path,
                changed_fields=[],
                plan_path_label=plan_path_label,
                trusted_card_limit=trusted_card_limit,
                applied_file_change=False,
            )
            reviewed_entries.append(
                {
                    "action_key": action_key,
                    "entry_id": entry_id,
                    "entry_path": relative_repo_path(repo_root, current_path),
                    "decision": decision_name,
                    "risk": risk,
                    "utility_assessment": dict(utility_assessment),
                    "event_ids": evidence_event_ids,
                }
            )
            continue

        updates, disallowed_fields = semantic_review_updated_fields(decision)
        if disallowed_fields:
            skipped_actions.append(
                _semantic_review_skip(
                    action,
                    f"Semantic review updated_fields contains unsupported fields: {', '.join(disallowed_fields)}",
                )
            )
            continue

        updated_payload, update_error = _semantic_review_apply_updates(current_payload, updates, decision_name)
        if update_error or updated_payload is None:
            skipped_actions.append(_semantic_review_skip(action, update_error))
            continue

        if decision_name == "promote":
            target_scope = str(decision.get("target_scope") or updates.get("scope") or current_payload.get("scope") or "private").strip().lower()
            if target_scope not in {"public", "private"}:
                skipped_actions.append(_semantic_review_skip(action, "promote requires target_scope public or private."))
                continue
            updated_payload["scope"] = target_scope
            updated_payload["status"] = "trusted"
        elif decision_name == "demote":
            target_scope = str(decision.get("target_scope") or current_payload.get("scope") or "private").strip().lower()
            if target_scope not in {"public", "private"}:
                skipped_actions.append(_semantic_review_skip(action, "demote target_scope must be public or private when provided."))
                continue
            updated_payload["scope"] = target_scope
            updated_payload["status"] = "candidate"

        changed_fields = semantic_review_changed_fields(current_payload, updated_payload)
        if not changed_fields and decision_name not in {"promote", "demote"}:
            skipped_actions.append(_semantic_review_skip(action, "Semantic review decision produced no entry change."))
            continue

        trusted_surface_change = _semantic_review_requires_trusted_budget(
            current_payload,
            decision_name,
            updated_payload,
        )
        if trusted_surface_change and entry_id not in trusted_entry_ids_modified:
            if len(trusted_entry_ids_modified) >= trusted_card_limit:
                skipped_actions.append(
                    _semantic_review_skip(
                        action,
                        f"Trusted-card semantic review budget exhausted for this run (limit={trusted_card_limit}).",
                    )
                )
                continue
            trusted_entry_ids_modified.add(entry_id)

        updated_payload["updated_at"] = updated_at
        _semantic_review_append_source(
            updated_payload,
            run_id=run_id,
            updated_at=updated_at,
            action_key=action_key,
            decision_name=decision_name,
            evidence_event_ids=evidence_event_ids,
        )
        target_path = _semantic_review_target_path_for_decision(
            repo_root,
            current_path,
            updated_payload,
            decision_name,
        )
        if target_path != current_path and target_path.exists():
            skipped_actions.append(
                _semantic_review_skip(
                    action,
                    f"Semantic review target file already exists: {relative_repo_path(repo_root, target_path)}",
                )
            )
            continue

        write_yaml_file(target_path, updated_payload)
        if target_path != current_path and current_path.exists():
            current_path.unlink()

        entry_lookup[entry_id] = updated_payload
        entry_path_lookup[entry_id] = target_path
        changed_fields = semantic_review_changed_fields(current_payload, updated_payload)
        missing_i18n = missing_i18n_fields(updated_payload, ZH_CN)
        if semantic_review_needs_i18n_followup(changed_fields, updated_payload) or missing_i18n:
            i18n_followup_entries.append(
                {
                    "entry_id": entry_id,
                    "entry_path": relative_repo_path(repo_root, target_path),
                    "changed_fields": changed_fields,
                    "missing_i18n_fields": missing_i18n,
                }
            )

        _record_semantic_review_event(
            repo_root,
            run_id=run_id,
            action=action,
            decision=decision,
            decision_name=decision_name,
            risk=risk,
            utility_assessment=utility_assessment,
            evidence_event_ids=evidence_event_ids,
            current_payload=current_payload,
            updated_payload=updated_payload,
            current_path=current_path,
            updated_path=target_path,
            changed_fields=changed_fields,
            plan_path_label=plan_path_label,
            trusted_card_limit=trusted_card_limit,
            applied_file_change=True,
        )
        updated_entries.append(
            {
                "action_key": action_key,
                "entry_id": entry_id,
                "previous_entry_path": relative_repo_path(repo_root, current_path),
                "entry_path": relative_repo_path(repo_root, target_path),
                "decision": decision_name,
                "risk": risk,
                "utility_assessment": dict(utility_assessment),
                "changed_fields": changed_fields,
                "event_ids": evidence_event_ids,
                "previous_entry": current_payload,
                "updated_entry": updated_payload,
            }
        )

    i18n_followup = {
        "required": bool(i18n_followup_entries),
        "language": ZH_CN,
        "missing_entry_count": len(i18n_followup_entries),
        "entries": i18n_followup_entries,
        "recommended_apply_mode": APPLY_MODE_I18N_ZH_CN,
        "reason": (
            "Semantic review changed canonical card fields or found missing zh-CN display fields; "
            "author or refresh the zh-CN translation plan after semantic review."
        ),
    }
    return {
        "apply_mode": APPLY_MODE_SEMANTIC_REVIEW,
        "created_candidate_count": 0,
        "updated_entry_count": len(updated_entries),
        "reviewed_entry_count": len(reviewed_entries),
        "skipped_action_count": len(skipped_actions),
        "created_candidates": [],
        "updated_entries": updated_entries,
        "reviewed_entries": reviewed_entries,
        "skipped_actions": skipped_actions,
        "semantic_review_plan_path": plan_path_label,
        "trusted_card_limit": trusted_card_limit,
        "trusted_card_modified_count": len(trusted_entry_ids_modified),
        "i18n_followup": i18n_followup,
    }


def build_apply_payload(
    repo_root: Path,
    run_id: str,
    generated_at: str,
    apply_summary: dict[str, Any],
    event_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "local-kb-consolidation-apply-report",
        "run_id": run_id,
        "generated_at": generated_at,
        "history_path": relative_repo_path(repo_root, history_events_path(repo_root)),
        "history_event_count_before_apply": event_count,
        **apply_summary,
    }


def emit_apply_artifact(
    repo_root: Path,
    run_id: str,
    apply_payload: dict[str, Any],
) -> str:
    run_dir = consolidation_run_dir(repo_root, run_id)
    apply_path = run_dir / "apply.json"
    write_json_file(apply_path, apply_payload)
    return relative_repo_path(repo_root, apply_path)


def _prepare_consolidation_context(
    repo_root: Path,
    run_id: str | None,
    apply_mode: str,
    max_events: int | None,
) -> dict[str, Any]:
    return {
        "clean_run_id": sanitize_run_id(run_id),
        "normalized_apply_mode": normalize_apply_mode(apply_mode),
        "generated_at": utc_now_iso(),
        "events": load_history_events(repo_root, max_events=max_events),
    }


def _prepare_consolidation_actions(
    repo_root: Path,
    events: list[dict[str, Any]],
    include_i18n: bool = False,
    only_i18n: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entry_lookup = build_entry_lookup(repo_root)
    grouped_actions: list[dict[str, Any]] = []
    if not only_i18n:
        grouped_actions = group_candidate_actions(events)
        grouped_actions.extend(build_related_card_actions(events, entry_lookup))
        grouped_actions.extend(build_cross_index_actions(events, entry_lookup))
    if include_i18n:
        grouped_actions.extend(build_i18n_actions(repo_root))
    grouped_actions = sorted(
        grouped_actions,
        key=lambda item: (
            -int(item.get("priority_score", 0) or 0),
            str(item.get("action_type", "") or ""),
            str(item.get("target", {}).get("kind", "") or ""),
            str(item.get("target", {}).get("ref", "") or ""),
        ),
    )
    grouped_actions, suppressed_actions = suppress_resolved_actions(grouped_actions, events)
    actions = annotate_actions_with_apply_eligibility(repo_root, grouped_actions, events)
    return actions, suppressed_actions


def _maybe_emit_consolidation_artifacts(
    repo_root: Path,
    run_id: str,
    generated_at: str,
    events: list[dict[str, Any]],
    proposal_payload: dict[str, Any],
    emit_files: bool,
    apply_mode: str,
) -> dict[str, Any]:
    should_emit_artifacts = emit_files or apply_mode != APPLY_MODE_NONE
    if not should_emit_artifacts:
        return {}

    snapshot_payload = build_snapshot_payload(
        repo_root=repo_root,
        run_id=run_id,
        generated_at=generated_at,
        events=events,
    )
    return emit_artifacts(
        repo_root=repo_root,
        run_id=run_id,
        generated_at=generated_at,
        snapshot_payload=snapshot_payload,
        proposal_payload=proposal_payload,
    )


def _apply_actions_for_mode(
    repo_root: Path,
    actions: list[dict[str, Any]],
    events: list[dict[str, Any]],
    run_id: str,
    generated_at: str,
    apply_mode: str,
    i18n_plan_path: Path | None = None,
    semantic_review_plan_path: Path | None = None,
) -> dict[str, Any]:
    if apply_mode == APPLY_MODE_NEW_CANDIDATES:
        return apply_new_candidate_actions(
            repo_root=repo_root,
            actions=actions,
            events=events,
            run_id=run_id,
            generated_at=generated_at,
        )
    if apply_mode == APPLY_MODE_RELATED_CARDS:
        return apply_related_card_actions(
            repo_root=repo_root,
            actions=actions,
            run_id=run_id,
            generated_at=generated_at,
        )
    if apply_mode == APPLY_MODE_CROSS_INDEX:
        return apply_cross_index_actions(
            repo_root=repo_root,
            actions=actions,
            run_id=run_id,
            generated_at=generated_at,
        )
    if apply_mode == APPLY_MODE_I18N_ZH_CN:
        return apply_i18n_actions(
            repo_root=repo_root,
            actions=actions,
            run_id=run_id,
            generated_at=generated_at,
            i18n_plan_path=i18n_plan_path,
        )
    if apply_mode == APPLY_MODE_SEMANTIC_REVIEW:
        return apply_semantic_review_actions(
            repo_root=repo_root,
            actions=actions,
            run_id=run_id,
            generated_at=generated_at,
            semantic_review_plan_path=semantic_review_plan_path,
        )
    return build_empty_apply_summary(apply_mode)


def _maybe_emit_apply_report(
    repo_root: Path,
    run_id: str,
    generated_at: str,
    apply_mode: str,
    apply_summary: dict[str, Any],
    event_count: int,
) -> str:
    if apply_mode == APPLY_MODE_NONE:
        return ""

    apply_payload = build_apply_payload(
        repo_root=repo_root,
        run_id=run_id,
        generated_at=generated_at,
        apply_summary=apply_summary,
        event_count=event_count,
    )
    return emit_apply_artifact(
        repo_root=repo_root,
        run_id=run_id,
        apply_payload=apply_payload,
    )


def _run_apply_phase(
    repo_root: Path,
    actions: list[dict[str, Any]],
    events: list[dict[str, Any]],
    run_id: str,
    generated_at: str,
    apply_mode: str,
    artifact_paths: dict[str, Any],
    i18n_plan_path: Path | None = None,
    semantic_review_plan_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    apply_summary = _apply_actions_for_mode(
        repo_root=repo_root,
        actions=actions,
        events=events,
        run_id=run_id,
        generated_at=generated_at,
        apply_mode=apply_mode,
        i18n_plan_path=i18n_plan_path,
        semantic_review_plan_path=semantic_review_plan_path,
    )
    apply_path = _maybe_emit_apply_report(
        repo_root=repo_root,
        run_id=run_id,
        generated_at=generated_at,
        apply_mode=apply_mode,
        apply_summary=apply_summary,
        event_count=len(events),
    )
    if apply_path:
        updated_artifact_paths = dict(artifact_paths)
        updated_artifact_paths["apply_path"] = apply_path
        return apply_summary, updated_artifact_paths
    return apply_summary, artifact_paths


def consolidate_history(
    repo_root: Path,
    run_id: str | None = None,
    emit_files: bool = False,
    max_events: int | None = None,
    apply_mode: str = APPLY_MODE_NONE,
    i18n_plan_path: Path | None = None,
    semantic_review_plan_path: Path | None = None,
) -> dict[str, Any]:
    context = _prepare_consolidation_context(
        repo_root=repo_root,
        run_id=run_id,
        apply_mode=apply_mode,
        max_events=max_events,
    )
    clean_run_id = str(context["clean_run_id"])
    normalized_apply_mode = str(context["normalized_apply_mode"])
    generated_at = str(context["generated_at"])
    events = list(context["events"])
    actions, suppressed_actions = _prepare_consolidation_actions(
        repo_root,
        events,
        include_i18n=normalized_apply_mode == APPLY_MODE_I18N_ZH_CN,
        only_i18n=normalized_apply_mode == APPLY_MODE_I18N_ZH_CN,
    )
    proposal_payload = build_proposal_payload(
        repo_root=repo_root,
        run_id=clean_run_id,
        generated_at=generated_at,
        actions=actions,
        event_count=len(events),
        max_events=max_events,
    )
    artifact_paths = _maybe_emit_consolidation_artifacts(
        repo_root=repo_root,
        run_id=clean_run_id,
        generated_at=generated_at,
        events=events,
        proposal_payload=proposal_payload,
        emit_files=emit_files,
        apply_mode=normalized_apply_mode,
    )
    apply_summary, artifact_paths = _run_apply_phase(
        repo_root=repo_root,
        actions=actions,
        events=events,
        run_id=clean_run_id,
        generated_at=generated_at,
        apply_mode=normalized_apply_mode,
        artifact_paths=artifact_paths,
        i18n_plan_path=i18n_plan_path,
        semantic_review_plan_path=semantic_review_plan_path,
    )

    return {
        **proposal_payload,
        "apply_mode": normalized_apply_mode,
        "apply_summary": apply_summary,
        "suppressed_action_count": len(suppressed_actions),
        "suppressed_actions": suppressed_actions,
        "action_stub_dir": artifact_paths.get("action_stub_dir", ""),
        "action_stub_count": int(artifact_paths.get("action_stub_count", 0) or 0),
        "artifact_paths": artifact_paths,
    }
