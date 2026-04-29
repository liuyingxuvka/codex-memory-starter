"""FlowGuard model for the planned Khaos Brain maintenance-flow changes.

This model checks the plan before production edits:

    Sleep content work -> final AI zh-CN cleanup -> Architect report rollup
    -> content-boundary/install gates -> release/update readiness

The model is intentionally about workflow ownership, not text quality. It
models whether the final cleanup and summary gates prevent silent completion,
duplicate translation work, leaked local-only content, stale installs, and
incomplete Architect reports.
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


REQUIRED_ARCHITECT_REPORTS = ("sleep", "dream", "flowguard", "organization", "install")


@dataclass(frozen=True)
class Event:
    kind: str


@dataclass(frozen=True)
class StepResult:
    event: Event
    action: str


@dataclass(frozen=True)
class State:
    card_i18n_missing: bool = False
    route_i18n_missing: bool = False
    canonical_card_fields_stable: bool = True
    canonical_routes_stable: bool = True
    content_change_count: int = 0
    final_i18n_runs: int = 0
    legacy_i18n_applied: bool = False
    sleep_report_status: str = "none"
    reports_seen: tuple[str, ...] = ()
    architect_summary_status: str = "none"
    improvement_backlog_visible_to_system: bool = False
    repo_skill_changed: bool = False
    installed_synced: bool = True
    install_check_passed: bool = True
    content_boundaries_verified: bool = False
    local_only_content_leaked: bool = False
    release_state: str = "unknown"

    def i18n_clean(self) -> bool:
        return not self.card_i18n_missing and not self.route_i18n_missing

    def has_all_reports(self) -> bool:
        return all(report in self.reports_seen for report in REQUIRED_ARCHITECT_REPORTS)

    def install_healthy_for_current_repo(self) -> bool:
        return (not self.repo_skill_changed) or (self.installed_synced and self.install_check_passed)

    def release_ready(self) -> bool:
        return (
            self.i18n_clean()
            and self.sleep_report_status == "clean"
            and self.architect_summary_status == "complete"
            and self.improvement_backlog_visible_to_system
            and self.content_boundaries_verified
            and not self.local_only_content_leaked
            and self.install_healthy_for_current_repo()
        )


def _append_unique(values: tuple[str, ...], value: str) -> tuple[str, ...]:
    return values if value in values else values + (value,)


class SleepFinalI18nBlock:
    """Input x State -> Set(Output x State) for Sleep-owned final zh-CN cleanup."""

    name = "SleepFinalI18nBlock"
    reads = (
        "card_i18n_missing",
        "route_i18n_missing",
        "content_change_count",
        "final_i18n_runs",
        "sleep_report_status",
    )
    writes = (
        "card_i18n_missing",
        "route_i18n_missing",
        "content_change_count",
        "final_i18n_runs",
        "legacy_i18n_applied",
        "sleep_report_status",
    )
    accepted_input_type = Event
    output_description = "StepResult"
    idempotency = "The legacy i18n step is disabled; repeated final cleanup is a no-op once display text is clean."

    def __init__(self, *, variant: str = "accepted") -> None:
        self.variant = variant

    def apply(self, input_obj: Event, state: State) -> Iterable[FunctionResult]:
        event = input_obj
        if event.kind == "sleep_content_change":
            yield FunctionResult(
                output=StepResult(event, "sleep_content_changed"),
                new_state=replace(
                    state,
                    card_i18n_missing=True,
                    route_i18n_missing=True,
                    content_change_count=state.content_change_count + 1,
                    sleep_report_status="dirty",
                ),
                label="sleep_content_changed",
                reason="Sleep created or semantically changed card/path display content.",
            )
            return

        if event.kind == "sleep_legacy_i18n_step":
            if self.variant == "bad_legacy_i18n_duplicate" and not state.i18n_clean():
                yield FunctionResult(
                    output=StepResult(event, "legacy_i18n_applied"),
                    new_state=replace(
                        state,
                        card_i18n_missing=False,
                        route_i18n_missing=False,
                        legacy_i18n_applied=True,
                    ),
                    label="legacy_i18n_applied",
                    reason="Broken variant keeps the old mid-run translation step active.",
                )
                return
            yield FunctionResult(
                output=StepResult(event, "legacy_i18n_disabled"),
                new_state=state,
                label="legacy_i18n_disabled",
                reason="Planned flow removes the separate early translation pass.",
            )
            return

        if event.kind == "sleep_final_i18n_cleanup":
            if state.i18n_clean():
                yield FunctionResult(
                    output=StepResult(event, "final_i18n_noop_clean"),
                    new_state=state,
                    label="final_i18n_noop_clean",
                    reason="Final cleanup is idempotent when card and route display text is already clean.",
                )
                return
            yield FunctionResult(
                output=StepResult(event, "final_i18n_applied"),
                new_state=replace(
                    state,
                    card_i18n_missing=False,
                    route_i18n_missing=False,
                    final_i18n_runs=state.final_i18n_runs + 1,
                ),
                label="final_i18n_applied",
                reason="Sleep applies one unified AI-authored zh-CN completion pass at the end.",
            )
            return

        if event.kind == "sleep_finish":
            if self.variant == "bad_sleep_allows_missing_i18n":
                yield FunctionResult(
                    output=StepResult(event, "sleep_finished_clean"),
                    new_state=replace(state, sleep_report_status="clean"),
                    label="sleep_finished_clean",
                    reason="Broken variant lets Sleep report clean despite missing display translations.",
                )
                return
            if state.i18n_clean():
                yield FunctionResult(
                    output=StepResult(event, "sleep_finished_clean"),
                    new_state=replace(state, sleep_report_status="clean"),
                    label="sleep_finished_clean",
                    reason="Sleep finishes clean only after card and route zh-CN display text is complete.",
                )
                return
            yield FunctionResult(
                output=StepResult(event, "sleep_finish_blocked_missing_i18n"),
                new_state=replace(state, sleep_report_status="incomplete"),
                label="sleep_finish_blocked_missing_i18n",
                reason="Sleep cannot silently finish clean while display translations are missing.",
            )
            return

        yield FunctionResult(
            output=StepResult(event, "sleep_noop"),
            new_state=state,
            label="sleep_noop",
            reason="Event belongs to a later maintenance boundary.",
        )


class ArchitectRollupBlock:
    """Input x State -> Set(Output x State) for Architect-owned report aggregation."""

    name = "ArchitectRollupBlock"
    reads = ("sleep_report_status", "reports_seen", "repo_skill_changed", "installed_synced", "install_check_passed")
    writes = ("reports_seen", "architect_summary_status", "improvement_backlog_visible_to_system")
    accepted_input_type = StepResult
    output_description = "StepResult"
    idempotency = "Repeated report collection only records each source once; summary writing converges."

    def __init__(self, *, variant: str = "accepted") -> None:
        self.variant = variant

    def apply(self, input_obj: StepResult, state: State) -> Iterable[FunctionResult]:
        event = input_obj.event
        if event.kind == "architect_collect_sleep":
            if state.sleep_report_status in {"clean", "incomplete"}:
                yield FunctionResult(
                    output=StepResult(event, "architect_collected_sleep"),
                    new_state=replace(state, reports_seen=_append_unique(state.reports_seen, "sleep")),
                    label="architect_collected_sleep",
                    reason="Architect reads the latest Sleep report after Sleep has produced one.",
                )
                return
            yield FunctionResult(
                output=StepResult(event, "architect_sleep_report_missing"),
                new_state=state,
                label="architect_sleep_report_missing",
                reason="Architect cannot count Sleep before Sleep has emitted a report.",
            )
            return

        source_by_event = {
            "architect_collect_dream": "dream",
            "architect_collect_flowguard": "flowguard",
            "architect_collect_organization": "organization",
            "architect_collect_install": "install",
        }
        if event.kind in source_by_event:
            source = source_by_event[event.kind]
            if source == "install" and not state.install_healthy_for_current_repo():
                yield FunctionResult(
                    output=StepResult(event, "architect_install_report_unhealthy"),
                    new_state=state,
                    label="architect_install_report_unhealthy",
                    reason="Architect sees that installed Codex skills are stale relative to repo changes.",
                )
                return
            yield FunctionResult(
                output=StepResult(event, f"architect_collected_{source}"),
                new_state=replace(state, reports_seen=_append_unique(state.reports_seen, source)),
                label=f"architect_collected_{source}",
                reason=f"Architect records the {source} maintenance source.",
            )
            return

        if event.kind == "architect_write_summary":
            if self.variant == "bad_architect_summary_without_sources":
                yield FunctionResult(
                    output=StepResult(event, "architect_summary_complete"),
                    new_state=replace(
                        state,
                        architect_summary_status="complete",
                        improvement_backlog_visible_to_system=True,
                    ),
                    label="architect_summary_complete",
                    reason="Broken variant writes a complete rollup without all source reports.",
                )
                return
            if state.has_all_reports() and state.install_healthy_for_current_repo():
                yield FunctionResult(
                    output=StepResult(event, "architect_summary_complete"),
                    new_state=replace(
                        state,
                        architect_summary_status="complete",
                        improvement_backlog_visible_to_system=True,
                    ),
                    label="architect_summary_complete",
                    reason="Architect writes the system-readable rollup after all source reports are present.",
                )
                return
            yield FunctionResult(
                output=StepResult(event, "architect_summary_incomplete"),
                new_state=replace(
                    state,
                    architect_summary_status="incomplete",
                    improvement_backlog_visible_to_system=False,
                ),
                label="architect_summary_incomplete",
                reason="Architect refuses to call the rollup complete while source reports are missing or install is stale.",
            )
            return

        yield FunctionResult(
            output=input_obj,
            new_state=state,
            label="architect_noop",
            reason="Event belongs to another maintenance boundary.",
        )


class BoundaryInstallGateBlock:
    """Input x State -> Set(Output x State) for content-boundary and install-sync gates."""

    name = "BoundaryInstallGateBlock"
    reads = (
        "repo_skill_changed",
        "installed_synced",
        "install_check_passed",
        "content_boundaries_verified",
        "release_state",
    )
    writes = (
        "repo_skill_changed",
        "installed_synced",
        "install_check_passed",
        "content_boundaries_verified",
        "local_only_content_leaked",
        "release_state",
    )
    accepted_input_type = StepResult
    output_description = "StepResult"
    idempotency = "Repeated install sync and boundary review converge on the same verified state."

    def __init__(self, *, variant: str = "accepted") -> None:
        self.variant = variant

    def apply(self, input_obj: StepResult, state: State) -> Iterable[FunctionResult]:
        event = input_obj.event
        if event.kind == "skill_repo_changed":
            yield FunctionResult(
                output=StepResult(event, "repo_skill_changed"),
                new_state=replace(
                    state,
                    repo_skill_changed=True,
                    installed_synced=False,
                    install_check_passed=False,
                ),
                label="repo_skill_changed",
                reason="Repository-managed skills changed and installed Codex skills are stale until sync.",
            )
            return

        if event.kind == "install_sync":
            yield FunctionResult(
                output=StepResult(event, "install_sync_passed"),
                new_state=replace(state, installed_synced=True, install_check_passed=True),
                label="install_sync_passed",
                reason="Installer refresh and check make installed Codex skills match the repository.",
            )
            return

        if event.kind == "content_boundary_review":
            yield FunctionResult(
                output=StepResult(event, "content_boundaries_verified"),
                new_state=replace(
                    state,
                    content_boundaries_verified=True,
                    local_only_content_leaked=False,
                ),
                label="content_boundaries_verified",
                reason="Formal/candidate/local-adoption/sandbox/history boundaries were reviewed before release.",
            )
            return

        if event.kind == "release_gate":
            if self.variant == "bad_release_without_boundary":
                yield FunctionResult(
                    output=StepResult(event, "release_allowed"),
                    new_state=replace(state, release_state="allowed"),
                    label="release_allowed",
                    reason="Broken variant lets release proceed without boundary/install/i18n gates.",
                )
                return
            if state.release_ready():
                yield FunctionResult(
                    output=StepResult(event, "release_allowed"),
                    new_state=replace(state, release_state="allowed"),
                    label="release_allowed",
                    reason="Release/update is allowed only after cleanup, rollup, boundaries, and install sync pass.",
                )
                return
            block_reason = "release_blocked"
            if not state.content_boundaries_verified:
                block_reason = "release_blocked_boundary"
            elif not state.install_healthy_for_current_repo():
                block_reason = "release_blocked_install"
            elif not state.i18n_clean() or state.sleep_report_status != "clean":
                block_reason = "release_blocked_sleep_i18n"
            elif state.architect_summary_status != "complete":
                block_reason = "release_blocked_architect_summary"
            yield FunctionResult(
                output=StepResult(event, block_reason),
                new_state=replace(state, release_state="blocked"),
                label=block_reason,
                reason="Release gate blocks until all planned maintenance boundaries are satisfied.",
            )
            return

        yield FunctionResult(
            output=input_obj,
            new_state=state,
            label="gate_noop",
            reason="Event has no content-boundary or install-sync effect.",
        )


def build_workflow(*, variant: str = "accepted") -> Workflow:
    return Workflow(
        (
            SleepFinalI18nBlock(variant=variant),
            ArchitectRollupBlock(variant=variant),
            BoundaryInstallGateBlock(variant=variant),
        ),
        name=f"khaos_brain_planned_maintenance_flow_{variant}",
    )


WORKFLOW = build_workflow()
INITIAL_STATES = (State(),)
INPUTS = (
    Event("sleep_content_change"),
    Event("sleep_legacy_i18n_step"),
    Event("sleep_final_i18n_cleanup"),
    Event("sleep_finish"),
    Event("architect_collect_sleep"),
    Event("architect_collect_dream"),
    Event("architect_collect_flowguard"),
    Event("architect_collect_organization"),
    Event("architect_collect_install"),
    Event("architect_write_summary"),
    Event("skill_repo_changed"),
    Event("install_sync"),
    Event("content_boundary_review"),
    Event("release_gate"),
)

ACCEPTED_SEQUENCE = (
    Event("sleep_content_change"),
    Event("sleep_legacy_i18n_step"),
    Event("sleep_final_i18n_cleanup"),
    Event("sleep_finish"),
    Event("skill_repo_changed"),
    Event("install_sync"),
    Event("architect_collect_sleep"),
    Event("architect_collect_dream"),
    Event("architect_collect_flowguard"),
    Event("architect_collect_organization"),
    Event("architect_collect_install"),
    Event("architect_write_summary"),
    Event("content_boundary_review"),
    Event("release_gate"),
)

MISSING_FINAL_I18N_SEQUENCE = (
    Event("sleep_content_change"),
    Event("sleep_finish"),
)

LEGACY_DISABLED_SEQUENCE = (
    Event("sleep_content_change"),
    Event("sleep_legacy_i18n_step"),
    Event("sleep_final_i18n_cleanup"),
)

ARCHITECT_MISSING_SOURCE_SEQUENCE = (
    Event("sleep_finish"),
    Event("architect_collect_sleep"),
    Event("architect_write_summary"),
)

INSTALL_UNSYNCED_RELEASE_SEQUENCE = (
    Event("sleep_finish"),
    Event("architect_collect_sleep"),
    Event("architect_collect_dream"),
    Event("architect_collect_flowguard"),
    Event("architect_collect_organization"),
    Event("skill_repo_changed"),
    Event("architect_collect_install"),
    Event("architect_write_summary"),
    Event("content_boundary_review"),
    Event("release_gate"),
)


def no_canonical_mutation(state: State, trace: object) -> InvariantResult:
    if not state.canonical_card_fields_stable:
        return InvariantResult.fail("canonical English card fields changed during display cleanup")
    if not state.canonical_routes_stable:
        return InvariantResult.fail("canonical route identifiers changed during display cleanup")
    return InvariantResult.pass_()


def no_duplicate_translation_work(state: State, trace: object) -> InvariantResult:
    if state.legacy_i18n_applied:
        return InvariantResult.fail("legacy mid-run i18n step still applied translations")
    if state.final_i18n_runs > state.content_change_count:
        return InvariantResult.fail("final i18n cleanup ran more times than content changed")
    return InvariantResult.pass_()


def no_sleep_clean_with_missing_i18n(state: State, trace: object) -> InvariantResult:
    if state.sleep_report_status == "clean" and not state.i18n_clean():
        return InvariantResult.fail("Sleep reported clean while card or route display translations were missing")
    return InvariantResult.pass_()


def architect_complete_requires_sources(state: State, trace: object) -> InvariantResult:
    if state.architect_summary_status == "complete" and not state.has_all_reports():
        return InvariantResult.fail(
            "Architect marked the system rollup complete without all required reports",
            {"reports_seen": ",".join(state.reports_seen)},
        )
    if state.architect_summary_status == "complete" and not state.install_healthy_for_current_repo():
        return InvariantResult.fail("Architect marked the rollup complete while installed skills were stale")
    return InvariantResult.pass_()


def release_requires_all_gates(state: State, trace: object) -> InvariantResult:
    if state.release_state != "allowed":
        return InvariantResult.pass_()
    if not state.release_ready():
        return InvariantResult.fail("release was allowed before i18n, Architect, content-boundary, and install gates passed")
    return InvariantResult.pass_()


INVARIANTS = (
    Invariant(
        "no_canonical_mutation",
        "AI zh-CN display cleanup must not rename canonical card fields or route identifiers.",
        no_canonical_mutation,
    ),
    Invariant(
        "no_duplicate_translation_work",
        "The old mid-run translation step must stay disabled and final cleanup must be idempotent.",
        no_duplicate_translation_work,
    ),
    Invariant(
        "no_sleep_clean_with_missing_i18n",
        "Sleep cannot report clean while any card or route display translation is missing.",
        no_sleep_clean_with_missing_i18n,
    ),
    Invariant(
        "architect_complete_requires_sources",
        "Architect rollup cannot be complete without Sleep, Dream, FlowGuard, organization, and install reports.",
        architect_complete_requires_sources,
    ),
    Invariant(
        "release_requires_all_gates",
        "Release/update readiness requires i18n, Architect rollup, content-boundary, and install-sync gates.",
        release_requires_all_gates,
    ),
)

CONTRACTS = (
    FunctionContract(
        function_name="SleepFinalI18nBlock",
        accepted_input_type=Event,
        output_type=StepResult,
        writes=SleepFinalI18nBlock.writes,
        forbidden_writes=(
            "reports_seen",
            "architect_summary_status",
            "improvement_backlog_visible_to_system",
            "repo_skill_changed",
            "installed_synced",
            "install_check_passed",
            "content_boundaries_verified",
            "release_state",
        ),
        idempotency_rule="Legacy i18n is disabled; final cleanup is a no-op after display text is complete.",
        traceability_rule="Sleep emits explicit labels for content change, disabled legacy i18n, final cleanup, and finish status.",
    ),
    FunctionContract(
        function_name="ArchitectRollupBlock",
        accepted_input_type=StepResult,
        output_type=StepResult,
        writes=ArchitectRollupBlock.writes,
        forbidden_writes=(
            "card_i18n_missing",
            "route_i18n_missing",
            "canonical_card_fields_stable",
            "canonical_routes_stable",
            "content_change_count",
            "final_i18n_runs",
            "legacy_i18n_applied",
            "content_boundaries_verified",
            "release_state",
        ),
        idempotency_rule="Repeated report collection is set-like; summary status converges.",
        traceability_rule="Architect rollup labels identify which source was collected or why summary stayed incomplete.",
    ),
    FunctionContract(
        function_name="BoundaryInstallGateBlock",
        accepted_input_type=StepResult,
        output_type=StepResult,
        writes=BoundaryInstallGateBlock.writes,
        forbidden_writes=(
            "card_i18n_missing",
            "route_i18n_missing",
            "canonical_card_fields_stable",
            "canonical_routes_stable",
            "content_change_count",
            "final_i18n_runs",
            "legacy_i18n_applied",
            "reports_seen",
            "architect_summary_status",
            "improvement_backlog_visible_to_system",
        ),
        idempotency_rule="Install sync, boundary review, and release gate converge on stable statuses.",
        traceability_rule="Gate labels explain which prerequisite blocks release/update readiness.",
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


def _has_label(run: ScenarioRun, label: str) -> bool:
    return any(trace.has_label(label) for trace in run.traces)


def _run_sequence(sequence: tuple[Event, ...], *, variant: str = "accepted") -> ScenarioRun:
    return run_exact_sequence(
        build_workflow(variant=variant),
        State(),
        sequence,
        invariants=INVARIANTS,
    )


def _first_completed_state(state: State, event: Event) -> tuple[str, State]:
    run = WORKFLOW.execute(state, event)
    if not run.completed_paths:
        return "dead_branch", state
    path = run.completed_paths[0]
    label = path.trace.steps[-1].label if path.trace.steps else "no_step"
    return label, path.state


def _progress_transition_fn(state: State) -> Iterable[tuple[str, State]]:
    if state.release_state == "allowed":
        return
    if not state.i18n_clean():
        yield _first_completed_state(state, Event("sleep_final_i18n_cleanup"))
        return
    if state.sleep_report_status in {"none", "dirty"}:
        yield _first_completed_state(state, Event("sleep_finish"))
        return
    if state.repo_skill_changed and not state.install_healthy_for_current_repo():
        yield _first_completed_state(state, Event("install_sync"))
        return
    for report in REQUIRED_ARCHITECT_REPORTS:
        if report not in state.reports_seen:
            event_name = {
                "sleep": "architect_collect_sleep",
                "dream": "architect_collect_dream",
                "flowguard": "architect_collect_flowguard",
                "organization": "architect_collect_organization",
                "install": "architect_collect_install",
            }[report]
            yield _first_completed_state(state, Event(event_name))
            return
    if state.architect_summary_status != "complete":
        yield _first_completed_state(state, Event("architect_write_summary"))
        return
    if not state.content_boundaries_verified:
        yield _first_completed_state(state, Event("content_boundary_review"))
        return
    yield _first_completed_state(state, Event("release_gate"))


def _run_loop_check() -> dict[str, object]:
    report = check_loops(
        LoopCheckConfig(
            initial_states=(State(card_i18n_missing=True, route_i18n_missing=True, sleep_report_status="dirty"),),
            transition_fn=_progress_transition_fn,
            is_terminal=lambda state: state.release_state == "allowed",
            is_success=lambda state: state.release_state == "allowed",
            required_success=True,
            max_depth=12,
            max_states=64,
            report_terminal_outgoing=False,
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


def main() -> int:
    explorer_report = Explorer(
        workflow=WORKFLOW,
        initial_states=INITIAL_STATES,
        external_inputs=INPUTS,
        invariants=INVARIANTS,
        max_sequence_length=3,
        required_labels=(
            "sleep_content_changed",
            "legacy_i18n_disabled",
            "final_i18n_applied",
            "sleep_finished_clean",
            "sleep_finish_blocked_missing_i18n",
            "architect_summary_incomplete",
            "install_sync_passed",
            "content_boundaries_verified",
            "release_blocked_boundary",
            "release_blocked_install",
        ),
    ).explore()
    accepted_run = _run_sequence(ACCEPTED_SEQUENCE)
    missing_final_run = _run_sequence(MISSING_FINAL_I18N_SEQUENCE)
    legacy_disabled_run = _run_sequence(LEGACY_DISABLED_SEQUENCE)
    architect_missing_run = _run_sequence(ARCHITECT_MISSING_SOURCE_SEQUENCE)
    install_unsynced_run = _run_sequence(INSTALL_UNSYNCED_RELEASE_SEQUENCE)
    bad_sleep_run = _run_sequence(MISSING_FINAL_I18N_SEQUENCE, variant="bad_sleep_allows_missing_i18n")
    bad_legacy_run = _run_sequence(LEGACY_DISABLED_SEQUENCE, variant="bad_legacy_i18n_duplicate")
    bad_architect_run = _run_sequence(ARCHITECT_MISSING_SOURCE_SEQUENCE, variant="bad_architect_summary_without_sources")
    bad_release_run = _run_sequence((Event("release_gate"),), variant="bad_release_without_boundary")
    contract_summary = _contract_summary(accepted_run)
    loop_summary = _run_loop_check()

    result = {
        "model": "khaos_brain_planned_maintenance_flow",
        "flowguard_schema_version": "1.0",
        "question_results": {
            "accepted_plan_reaches_clean_release": (
                _has_label(accepted_run, "final_i18n_applied")
                and _has_label(accepted_run, "sleep_finished_clean")
                and _has_label(accepted_run, "install_sync_passed")
                and _has_label(accepted_run, "architect_summary_complete")
                and _has_label(accepted_run, "content_boundaries_verified")
                and _has_label(accepted_run, "release_allowed")
            ),
            "missing_final_i18n_is_blocked": (
                _has_label(missing_final_run, "sleep_finish_blocked_missing_i18n")
                and not _has_label(missing_final_run, "sleep_finished_clean")
            ),
            "legacy_i18n_step_is_disabled": (
                _has_label(legacy_disabled_run, "legacy_i18n_disabled")
                and _has_label(legacy_disabled_run, "final_i18n_applied")
            ),
            "architect_cannot_complete_without_sources": (
                _has_label(architect_missing_run, "architect_summary_incomplete")
                and not _has_label(architect_missing_run, "architect_summary_complete")
            ),
            "install_change_blocks_release_until_sync": _has_label(install_unsynced_run, "release_blocked_install"),
            "bad_sleep_variant_is_rejected": bad_sleep_run.observed_status != "ok",
            "bad_legacy_variant_is_rejected": bad_legacy_run.observed_status != "ok",
            "bad_architect_variant_is_rejected": bad_architect_run.observed_status != "ok",
            "bad_release_variant_is_rejected": bad_release_run.observed_status != "ok",
            "contracts_hold_for_accepted_sequence": contract_summary["ok"],
            "progress_loop_has_success_and_no_stuck_bottom": loop_summary["ok"],
            "bounded_explorer_finds_required_labels": explorer_report.ok,
        },
        "explorer_report": _compact_report(explorer_report),
        "accepted_sequence": _scenario_dict(accepted_run),
        "missing_final_i18n_sequence": _scenario_dict(missing_final_run),
        "legacy_disabled_sequence": _scenario_dict(legacy_disabled_run),
        "architect_missing_source_sequence": _scenario_dict(architect_missing_run),
        "install_unsynced_release_sequence": _scenario_dict(install_unsynced_run),
        "bad_sleep_variant": _scenario_dict(bad_sleep_run),
        "bad_legacy_variant": _scenario_dict(bad_legacy_run),
        "bad_architect_variant": _scenario_dict(bad_architect_run),
        "bad_release_variant": _scenario_dict(bad_release_run),
        "contract_summary": contract_summary,
        "loop_summary": loop_summary,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    checks = result["question_results"]
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
