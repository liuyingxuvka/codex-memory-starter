"""FlowGuard model for merging the accepted card visual refresh.

The model is intentionally narrow. It checks that the sandbox-to-production
merge changes only card rendering presentation:

    accepted visual plan -> production render state -> verification output

It does not model Tkinter pixels. It models the architectural contract around
the UI patch: card data, retrieval routes, source text ownership, and the
production entry point must stay stable while the accepted card visuals become
available and the sandbox entry is removed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from typing import Iterable

from flowguard import (
    Explorer,
    FunctionContract,
    FunctionResult,
    Invariant,
    InvariantResult,
    LoopCheckConfig,
    ScenarioRun,
    Workflow,
    check_loops,
    check_trace_contracts,
    run_exact_sequence,
)


@dataclass(frozen=True)
class Event:
    kind: str


@dataclass(frozen=True)
class Plan:
    action: str


@dataclass(frozen=True)
class MergeResult:
    action: str
    ready: bool


@dataclass(frozen=True)
class State:
    card_payload_hash: str = "stable-card-data"
    retrieval_route: str = "unchanged"
    production_entry_ok: bool = True
    sandbox_entry_present: bool = True
    grid_palette: str = "old"
    grid_gradient: str = "vertical"
    grid_title_ring: bool = False
    grid_title_bold: bool = False
    detail_gradient: str = "vertical"
    detail_title_ring: bool = False
    detail_title_bold: bool = False
    detail_meta_pill: str = "wrapped"
    detail_source_body: str = "full-source-line"
    production_check_passed: bool = False

    def grid_ready(self) -> bool:
        return (
            self.grid_palette == "accepted-spectrum"
            and self.grid_gradient == "diagonal"
            and self.grid_title_ring
            and self.grid_title_bold
        )

    def detail_ready(self) -> bool:
        return (
            self.detail_gradient == "diagonal"
            and self.detail_title_ring
            and self.detail_title_bold
            and self.detail_meta_pill == "adaptive-single-line"
            and self.detail_source_body == "full-source-line"
        )

    def cleanup_ready(self) -> bool:
        return not self.sandbox_entry_present


class VisualPlanBlock:
    """Input x State -> Set(Output x State) for accepted visual merge actions."""

    name = "VisualPlanBlock"
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    accepted_input_type = Event
    input_description = "accepted UI merge event"
    output_description = "Plan"
    idempotency = "Repeated planning for the same visual action is read-only."

    def apply(self, input_obj: Event, state: State) -> Iterable[FunctionResult]:
        allowed = {
            "merge_grid_cards",
            "merge_detail_header",
            "remove_sandbox",
            "production_check",
        }
        action = input_obj.kind if input_obj.kind in allowed else "ignore"
        yield FunctionResult(
            output=Plan(action),
            new_state=state,
            label=f"planned_{action}",
            reason="plan is read-only and carries the requested visual action forward",
        )


class ProductionVisualMergeBlock:
    """Input x State -> Set(Output x State) for production card rendering state."""

    name = "ProductionVisualMergeBlock"
    reads = (
        "grid_palette",
        "grid_gradient",
        "grid_title_ring",
        "grid_title_bold",
        "detail_gradient",
        "detail_title_ring",
        "detail_title_bold",
        "detail_meta_pill",
        "detail_source_body",
        "sandbox_entry_present",
        "production_entry_ok",
    )
    writes = (
        "grid_palette",
        "grid_gradient",
        "grid_title_ring",
        "grid_title_bold",
        "detail_gradient",
        "detail_title_ring",
        "detail_title_bold",
        "detail_meta_pill",
        "detail_source_body",
        "sandbox_entry_present",
        "production_check_passed",
    )
    accepted_input_type = Plan
    input_description = "Plan"
    output_description = "MergeResult"
    idempotency = "Repeated visual merges set the same render flags and do not duplicate data or routes."

    def __init__(self, *, variant: str = "accepted") -> None:
        self.variant = variant

    def apply(self, input_obj: Plan, state: State) -> Iterable[FunctionResult]:
        action = input_obj.action
        if action == "merge_grid_cards":
            next_state = replace(
                state,
                grid_palette="accepted-spectrum",
                grid_gradient="vertical" if self.variant == "bad_vertical_gradient" else "diagonal",
                grid_title_ring=True,
                grid_title_bold=True,
                retrieval_route="changed" if self.variant == "bad_route_mutation" else state.retrieval_route,
            )
            yield FunctionResult(
                output=MergeResult(action, next_state.grid_ready()),
                new_state=next_state,
                label="grid_visual_ready" if next_state.grid_ready() else "grid_visual_incomplete",
                reason="grid cards carry the accepted palette, diagonal gradient, title ring, and bold title",
            )
            return
        if action == "merge_detail_header":
            next_state = replace(
                state,
                detail_gradient="diagonal",
                detail_title_ring=True,
                detail_title_bold=True,
                detail_meta_pill="wrapped" if self.variant == "bad_detail_wrap" else "adaptive-single-line",
                detail_source_body="mutated-source-line" if self.variant == "bad_source_body_mutation" else state.detail_source_body,
            )
            yield FunctionResult(
                output=MergeResult(action, next_state.detail_ready()),
                new_state=next_state,
                label="detail_visual_ready" if next_state.detail_ready() else "detail_visual_incomplete",
                reason="detail header mirrors the accepted card treatment and keeps the body source text unchanged",
            )
            return
        if action == "remove_sandbox":
            next_state = replace(state, sandbox_entry_present=False)
            yield FunctionResult(
                output=MergeResult(action, next_state.cleanup_ready()),
                new_state=next_state,
                label="sandbox_removed",
                reason="temporary sandbox entry is removed after production merge",
            )
            return
        if action == "production_check":
            ready = state.production_entry_ok and state.grid_ready() and state.detail_ready() and state.cleanup_ready()
            next_state = replace(state, production_check_passed=ready)
            yield FunctionResult(
                output=MergeResult(action, ready),
                new_state=next_state,
                label="production_check_passed" if ready else "production_check_failed",
                reason="official UI is only ready when production entry, grid, detail, and cleanup gates all pass",
            )
            return
        yield FunctionResult(
            output=MergeResult(action, False),
            new_state=state,
            label="ignored_unknown_action",
            reason="unknown events do not mutate production state",
        )


class VisualVerificationBlock:
    """Input x State -> Set(Output x State) for terminal verification labels."""

    name = "VisualVerificationBlock"
    reads = (
        "card_payload_hash",
        "retrieval_route",
        "production_entry_ok",
        "sandbox_entry_present",
        "grid_palette",
        "grid_gradient",
        "detail_gradient",
        "detail_meta_pill",
    )
    writes: tuple[str, ...] = ()
    accepted_input_type = MergeResult
    input_description = "MergeResult"
    output_description = "verification label"
    idempotency = "Verification is read-only."

    def apply(self, input_obj: MergeResult, state: State) -> Iterable[FunctionResult]:
        if input_obj.action == "production_check" and input_obj.ready:
            label = "verified_visual_merge"
        elif input_obj.ready:
            label = f"verified_{input_obj.action}"
        else:
            label = f"verification_pending_{input_obj.action}"
        yield FunctionResult(
            output=label,
            new_state=state,
            label=label,
            reason="verification records readiness without changing production data",
        )


def build_workflow(*, variant: str = "accepted") -> Workflow:
    return Workflow(
        (VisualPlanBlock(), ProductionVisualMergeBlock(variant=variant), VisualVerificationBlock()),
        name=f"card_visual_merge_flow_{variant}",
    )


WORKFLOW = build_workflow()
INITIAL_STATES = (State(),)
INPUTS = (
    Event("merge_grid_cards"),
    Event("merge_detail_header"),
    Event("remove_sandbox"),
    Event("production_check"),
)
CORRECT_SEQUENCE = (
    Event("merge_grid_cards"),
    Event("merge_detail_header"),
    Event("remove_sandbox"),
    Event("production_check"),
)
MISSING_CLEANUP_SEQUENCE = (
    Event("merge_grid_cards"),
    Event("merge_detail_header"),
    Event("production_check"),
)


def no_data_or_route_mutation(state: State, trace: object) -> InvariantResult:
    if state.card_payload_hash != "stable-card-data":
        return InvariantResult.fail("card payload hash changed during a visual-only merge")
    if state.retrieval_route != "unchanged":
        return InvariantResult.fail("retrieval route changed during a visual-only merge")
    return InvariantResult.pass_()


def production_entry_preserved(state: State, trace: object) -> InvariantResult:
    if not state.production_entry_ok:
        return InvariantResult.fail("production desktop entry point became unavailable")
    return InvariantResult.pass_()


def accepted_grid_visual_when_merged(state: State, trace: object) -> InvariantResult:
    if hasattr(trace, "has_label") and trace.has_label("planned_merge_grid_cards") and not state.grid_ready():
        return InvariantResult.fail("merged grid card visuals do not match the accepted treatment")
    return InvariantResult.pass_()


def accepted_detail_visual_when_merged(state: State, trace: object) -> InvariantResult:
    if hasattr(trace, "has_label") and trace.has_label("planned_merge_detail_header") and not state.detail_ready():
        return InvariantResult.fail("merged detail header visuals do not match the accepted treatment")
    return InvariantResult.pass_()


INVARIANTS = (
    Invariant(
        "no_data_or_route_mutation",
        "Visual-only merge must not mutate card payloads or retrieval routes.",
        no_data_or_route_mutation,
    ),
    Invariant(
        "production_entry_preserved",
        "The official desktop entry point must remain available.",
        production_entry_preserved,
    ),
    Invariant(
        "accepted_grid_visual_when_merged",
        "Merged grid cards must use the accepted palette, diagonal gradient, title ring, and bold title.",
        accepted_grid_visual_when_merged,
    ),
    Invariant(
        "accepted_detail_visual_when_merged",
        "Merged detail headers must use the accepted diagonal header, title ring, bold title, adaptive pill, and unchanged body source text.",
        accepted_detail_visual_when_merged,
    ),
)

CONTRACTS = (
    FunctionContract(
        function_name="VisualPlanBlock",
        accepted_input_type=Event,
        output_type=Plan,
        forbidden_writes=(
            "card_payload_hash",
            "retrieval_route",
            "production_entry_ok",
            "sandbox_entry_present",
        ),
        idempotency_rule="Planning is read-only.",
        traceability_rule="The plan label must retain the external action kind.",
    ),
    FunctionContract(
        function_name="ProductionVisualMergeBlock",
        accepted_input_type=Plan,
        output_type=MergeResult,
        writes=ProductionVisualMergeBlock.writes,
        forbidden_writes=("card_payload_hash", "production_entry_ok"),
        idempotency_rule="Repeated visual merges converge on the same render state.",
        traceability_rule="Each accepted visual action emits a specific readiness label.",
    ),
    FunctionContract(
        function_name="VisualVerificationBlock",
        accepted_input_type=MergeResult,
        output_type=str,
        forbidden_writes=(
            "card_payload_hash",
            "retrieval_route",
            "production_entry_ok",
            "sandbox_entry_present",
            "grid_palette",
            "grid_gradient",
            "detail_gradient",
            "detail_meta_pill",
        ),
        idempotency_rule="Verification is read-only.",
        traceability_rule="Verification emits a label derived from the merge result.",
    ),
)


def _report_dict(report: object) -> dict[str, object]:
    if hasattr(report, "to_dict"):
        return report.to_dict()
    return json.loads(report.to_json_text())


def _compact_report(report: object) -> dict[str, object]:
    payload = _report_dict(report)
    violations = payload.get("violations", []) or []
    reachability_failures = payload.get("reachability_failures", []) or []
    traces = payload.get("traces", []) or []
    labels_seen = sorted({label for trace in traces for label in trace.get("labels", [])})
    compact: dict[str, object] = {
        "ok": payload.get("ok"),
        "summary": payload.get("summary"),
        "violation_count": len(violations),
        "reachability_failure_count": len(reachability_failures),
        "dead_branch_count": len(payload.get("dead_branches", []) or []),
        "exception_branch_count": len(payload.get("exception_branches", []) or []),
        "labels_seen": labels_seen,
    }
    if violations:
        first = violations[0]
        compact["first_violation"] = {
            "invariant_name": first.get("invariant_name"),
            "message": first.get("message"),
            "trace_labels": first.get("trace", {}).get("labels", []),
        }
    if reachability_failures:
        first_reachability = reachability_failures[0]
        compact["first_reachability_failure"] = {
            "name": first_reachability.get("name"),
            "message": first_reachability.get("message"),
        }
    return compact


def _scenario_dict(run: ScenarioRun) -> dict[str, object]:
    payload = run.to_dict()
    traces = payload.get("traces", []) or []
    labels_seen = sorted({label for trace in traces for label in trace.get("labels", [])})
    return {
        "observed_status": payload.get("observed_status"),
        "model_ok": payload.get("model_report", {}).get("ok"),
        "labels_seen": labels_seen,
        "final_states": payload.get("final_states", []),
        "violation_names": payload.get("observed_violation_names", []),
    }


def _contract_summary(run: ScenarioRun) -> dict[str, object]:
    reports = [check_trace_contracts(trace, CONTRACTS) for trace in run.traces]
    return {
        "ok": all(report.ok for report in reports),
        "checked_steps": sum(report.checked_steps for report in reports),
        "violation_count": sum(len(report.violations) for report in reports),
        "summaries": [report.summary for report in reports],
    }


def _last_label_for_event(state: State, event: Event) -> tuple[str, State]:
    run = WORKFLOW.execute(state, event)
    if not run.completed_paths:
        return "dead_branch", state
    path = run.completed_paths[0]
    label = path.trace.steps[-1].label if path.trace.steps else "no_step"
    return label, path.state


def _transition_fn(state: State) -> Iterable[tuple[str, State]]:
    if state.production_check_passed and state.cleanup_ready():
        return
    for event in INPUTS:
        yield _last_label_for_event(state, event)


def _run_loop_check() -> dict[str, object]:
    report = check_loops(
        LoopCheckConfig(
            initial_states=INITIAL_STATES,
            transition_fn=_transition_fn,
            is_terminal=lambda state: state.production_check_passed and state.cleanup_ready(),
            is_success=lambda state: state.production_check_passed and state.cleanup_ready(),
            required_success=True,
            max_depth=5,
            max_states=64,
        )
    )
    payload = report.to_dict()
    return {
        "ok": payload.get("ok"),
        "graph_summary": payload.get("graph_summary"),
        "stuck_state_count": len(payload.get("stuck_states", []) or []),
        "non_terminating_component_count": len(payload.get("non_terminating_components", []) or []),
        "unreachable_success": payload.get("unreachable_success"),
    }


def _has_label(run: ScenarioRun, label: str) -> bool:
    return any(trace.has_label(label) for trace in run.traces)


def main() -> int:
    explorer_report = Explorer(
        workflow=WORKFLOW,
        initial_states=INITIAL_STATES,
        external_inputs=INPUTS,
        invariants=INVARIANTS,
        max_sequence_length=4,
        required_labels=(
            "grid_visual_ready",
            "detail_visual_ready",
            "sandbox_removed",
            "production_check_passed",
            "verified_visual_merge",
        ),
    ).explore()
    correct_run = run_exact_sequence(WORKFLOW, State(), CORRECT_SEQUENCE, invariants=INVARIANTS)
    missing_cleanup_run = run_exact_sequence(WORKFLOW, State(), MISSING_CLEANUP_SEQUENCE, invariants=INVARIANTS)
    bad_route_run = run_exact_sequence(
        build_workflow(variant="bad_route_mutation"),
        State(),
        (Event("merge_grid_cards"),),
        invariants=INVARIANTS,
    )
    bad_detail_run = run_exact_sequence(
        build_workflow(variant="bad_detail_wrap"),
        State(),
        (Event("merge_detail_header"),),
        invariants=INVARIANTS,
    )
    bad_gradient_run = run_exact_sequence(
        build_workflow(variant="bad_vertical_gradient"),
        State(),
        (Event("merge_grid_cards"),),
        invariants=INVARIANTS,
    )
    contract_summary = _contract_summary(correct_run)
    loop_summary = _run_loop_check()

    result = {
        "model": "card_visual_merge_flow",
        "flowguard_schema_version": "1.0",
        "question_results": {
            "accepted_visual_merge_reaches_verified_state": explorer_report.ok and _has_label(correct_run, "production_check_passed"),
            "missing_sandbox_cleanup_is_blocked": not _has_label(missing_cleanup_run, "production_check_passed"),
            "route_mutation_variant_is_rejected": bad_route_run.observed_status != "ok",
            "detail_wrapping_variant_is_rejected": bad_detail_run.observed_status != "ok",
            "vertical_gradient_variant_is_rejected": bad_gradient_run.observed_status != "ok",
            "contracts_hold_for_correct_sequence": contract_summary["ok"],
            "loop_review_has_success_and_no_stuck_bottom": loop_summary["ok"],
        },
        "explorer_report": _compact_report(explorer_report),
        "correct_sequence": _scenario_dict(correct_run),
        "missing_cleanup_sequence": _scenario_dict(missing_cleanup_run),
        "bad_route_variant": _scenario_dict(bad_route_run),
        "bad_detail_wrap_variant": _scenario_dict(bad_detail_run),
        "bad_vertical_gradient_variant": _scenario_dict(bad_gradient_run),
        "contract_summary": contract_summary,
        "loop_summary": loop_summary,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    checks = result["question_results"]
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
