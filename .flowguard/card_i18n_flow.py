"""FlowGuard model for Khaos Brain card creation and zh-CN display cleanup.

This model checks the narrow workflow behind English-only cards:

    external memory event -> card creation surface -> i18n cleanup -> sleep finalization

It intentionally models card text abstractly. The only text state tracked is
whether a card has the optional `i18n.zh-CN` display payload.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from typing import Iterable

from flowguard import (
    Explorer,
    FunctionResult,
    Invariant,
    InvariantResult,
    Workflow,
    run_exact_sequence,
)


@dataclass(frozen=True)
class Event:
    kind: str
    i18n_cleanup: bool = False


@dataclass(frozen=True)
class Card:
    card_id: str
    source: str
    has_zh_cn: bool


@dataclass(frozen=True)
class State:
    cards: tuple[Card, ...] = ()

    def add_card(self, source: str, *, has_zh_cn: bool = False) -> "State":
        return replace(
            self,
            cards=self.cards + (Card(f"{source}-{len(self.cards) + 1}", source, has_zh_cn),),
        )

    def translate_missing(self) -> "State":
        return replace(
            self,
            cards=tuple(replace(card, has_zh_cn=True) if not card.has_zh_cn else card for card in self.cards),
        )

    def missing_zh_count(self) -> int:
        return sum(1 for card in self.cards if not card.has_zh_cn)


@dataclass(frozen=True)
class CreationResult:
    event: Event
    created_source: str = ""


@dataclass(frozen=True)
class I18nResult:
    event: Event
    cleaned: bool


class CardCreationBlock:
    """Input x State -> Set(Output x State) for every supported card creation surface."""

    name = "CardCreationBlock"
    reads = ("cards",)
    writes = ("cards",)
    accepted_input_type = Event
    input_description = "abstract memory/card event"
    output_description = "CreationResult"
    idempotency = "Repeated abstract events create separate candidate/adopted cards; dedupe is outside this narrow i18n model."

    def apply(self, input_obj: Event, state: State) -> Iterable[FunctionResult]:
        source_by_kind = {
            "manual_candidate_capture": "manual",
            "sleep_candidate_pass": "sleep",
            "dream_candidate": "dream",
            "organization_adoption": "organization",
        }
        source = source_by_kind.get(input_obj.kind, "")
        if not source:
            yield FunctionResult(
                output=CreationResult(input_obj),
                new_state=state,
                label="no_card_created",
                reason="structured observation or i18n-only pass does not create a card",
            )
            return
        yield FunctionResult(
            output=CreationResult(input_obj, source),
            new_state=state.add_card(source, has_zh_cn=False),
            label=f"card_created_by_{source}",
            reason="new card stores English canonical fields first and lacks zh-CN until i18n cleanup",
        )


class I18nCleanupBlock:
    """Input x State -> Set(Output x State) for Sleep-owned display translation cleanup."""

    name = "I18nCleanupBlock"
    reads = ("cards",)
    writes = ("cards",)
    accepted_input_type = CreationResult
    input_description = "CreationResult"
    output_description = "I18nResult"
    idempotency = "A repeated cleanup leaves already translated cards unchanged."

    def apply(self, input_obj: CreationResult, state: State) -> Iterable[FunctionResult]:
        event = input_obj.event
        if event.kind in {"sleep_candidate_pass", "sleep_i18n_only_pass"} and event.i18n_cleanup:
            yield FunctionResult(
                output=I18nResult(event, True),
                new_state=state.translate_missing(),
                label="sleep_i18n_cleanup_applied",
                reason="AI-authored zh-CN plan was applied as the Sleep cleanup step",
            )
            return
        if event.kind in {"sleep_candidate_pass", "sleep_i18n_only_pass"}:
            yield FunctionResult(
                output=I18nResult(event, False),
                new_state=state,
                label="sleep_i18n_cleanup_skipped",
                reason="Sleep reached i18n check without an applied translation plan",
            )
            return
        yield FunctionResult(
            output=I18nResult(event, False),
            new_state=state,
            label="not_sleep_i18n_owner",
            reason="non-Sleep card creation does not translate during the same active task",
        )


class SleepFinalizeBlock:
    """Input x State -> Set(Output x State) for the Sleep pass completion boundary."""

    name = "SleepFinalizeBlock"
    reads = ("cards",)
    writes = ()
    accepted_input_type = I18nResult
    input_description = "I18nResult"
    output_description = "terminal text label"
    idempotency = "Finalization is read-only in this model."

    def apply(self, input_obj: I18nResult, state: State) -> Iterable[FunctionResult]:
        if input_obj.event.kind not in {"sleep_candidate_pass", "sleep_i18n_only_pass"}:
            yield FunctionResult(
                output="active_task_done",
                new_state=state,
                label="active_task_done",
                reason="non-Sleep work can leave English-only cards for a later Sleep i18n pass",
            )
            return
        if state.missing_zh_count():
            yield FunctionResult(
                output="sleep_finalized_with_missing_i18n",
                new_state=state,
                label="sleep_finalized_with_missing_i18n",
                reason="Sleep finalized while cards still lacked zh-CN display payloads",
            )
            return
        yield FunctionResult(
            output="sleep_finalized_clean",
            new_state=state,
            label="sleep_finalized_clean",
            reason="Sleep finalization sees no card text missing zh-CN display payloads",
        )


WORKFLOW = Workflow(
    (CardCreationBlock(), I18nCleanupBlock(), SleepFinalizeBlock()),
    name="card_i18n_flow",
)

INITIAL_STATES = (State(),)

OBSERVED_INPUTS = (
    Event("task_observation"),
    Event("manual_candidate_capture"),
    Event("dream_candidate"),
    Event("organization_adoption"),
    Event("sleep_candidate_pass", i18n_cleanup=True),
    Event("sleep_candidate_pass", i18n_cleanup=False),
    Event("sleep_i18n_only_pass", i18n_cleanup=True),
    Event("sleep_i18n_only_pass", i18n_cleanup=False),
)

IDEAL_SLEEP_INPUTS = (
    Event("task_observation"),
    Event("sleep_candidate_pass", i18n_cleanup=True),
    Event("sleep_i18n_only_pass", i18n_cleanup=True),
)


def no_sleep_finalize_with_missing_i18n(state: State, trace: object) -> InvariantResult:
    if hasattr(trace, "has_label") and trace.has_label("sleep_finalized_with_missing_i18n"):
        return InvariantResult.fail("Sleep finalized while at least one card was missing zh-CN display fields.")
    return InvariantResult.pass_()


def all_created_cards_are_sleep_owned(state: State, trace: object) -> InvariantResult:
    non_sleep = [card.card_id for card in state.cards if card.source != "sleep"]
    if non_sleep:
        return InvariantResult.fail(
            "Non-Sleep card creation exists in the modeled workflow.",
            {"non_sleep_cards": ",".join(non_sleep)},
        )
    return InvariantResult.pass_()


NO_SLEEP_FINALIZE_WITH_MISSING_I18N = Invariant(
    name="no_sleep_finalize_with_missing_i18n",
    description="A completed Sleep pass must not leave card text missing zh-CN display payloads.",
    predicate=no_sleep_finalize_with_missing_i18n,
)

ALL_CREATED_CARDS_ARE_SLEEP_OWNED = Invariant(
    name="all_created_cards_are_sleep_owned",
    description="Strict hypothesis check: every created card came from Sleep.",
    predicate=all_created_cards_are_sleep_owned,
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


def _run_sequence(sequence: tuple[Event, ...]) -> dict[str, object]:
    report = run_exact_sequence(
        workflow=WORKFLOW,
        initial_state=State(),
        external_input_sequence=sequence,
        invariants=(NO_SLEEP_FINALIZE_WITH_MISSING_I18N,),
    )
    return _compact_report(report)


def main() -> int:
    observed_report = Explorer(
        workflow=WORKFLOW,
        initial_states=INITIAL_STATES,
        external_inputs=OBSERVED_INPUTS,
        invariants=(NO_SLEEP_FINALIZE_WITH_MISSING_I18N,),
        max_sequence_length=2,
        required_labels=(
            "card_created_by_manual",
            "card_created_by_sleep",
            "card_created_by_dream",
            "card_created_by_organization",
            "sleep_i18n_cleanup_applied",
            "sleep_i18n_cleanup_skipped",
            "sleep_finalized_clean",
            "sleep_finalized_with_missing_i18n",
        ),
    ).explore()
    strict_sleep_only_report = Explorer(
        workflow=WORKFLOW,
        initial_states=INITIAL_STATES,
        external_inputs=OBSERVED_INPUTS,
        invariants=(ALL_CREATED_CARDS_ARE_SLEEP_OWNED,),
        max_sequence_length=1,
    ).explore()
    ideal_sleep_report = Explorer(
        workflow=WORKFLOW,
        initial_states=INITIAL_STATES,
        external_inputs=IDEAL_SLEEP_INPUTS,
        invariants=(NO_SLEEP_FINALIZE_WITH_MISSING_I18N,),
        max_sequence_length=2,
        required_labels=("sleep_finalized_clean",),
    ).explore()
    scenarios = {
        "manual_then_later_sleep_i18n": _run_sequence(
            (
                Event("manual_candidate_capture"),
                Event("sleep_i18n_only_pass", i18n_cleanup=True),
            )
        ),
        "sleep_candidate_with_i18n_cleanup": _run_sequence((Event("sleep_candidate_pass", i18n_cleanup=True),)),
        "sleep_candidate_without_i18n_cleanup": _run_sequence((Event("sleep_candidate_pass", i18n_cleanup=False),)),
        "organization_adoption_before_sleep": _run_sequence((Event("organization_adoption"),)),
    }
    result = {
        "model": "card_i18n_flow",
        "flowguard_schema_version": "1.0",
        "question_results": {
            "strict_all_card_creation_only_sleep": strict_sleep_only_report.ok,
            "sleep_i18n_cleanup_closes_loop_when_applied": ideal_sleep_report.ok,
            "observed_workflow_has_paths_that_leave_missing_i18n": not observed_report.ok,
        },
        "observed_workflow_report": _compact_report(observed_report),
        "strict_sleep_only_report": _compact_report(strict_sleep_only_report),
        "ideal_sleep_report": _compact_report(ideal_sleep_report),
        "scenarios": scenarios,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if ideal_sleep_report.ok and not observed_report.ok and not strict_sleep_only_report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
