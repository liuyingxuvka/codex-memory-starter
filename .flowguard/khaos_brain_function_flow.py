"""Executable model-first review for Khaos Brain stateful workflows.

This is a project-local model used by the model-first-function-flow skill.
The external flowguard package is not installed in this workspace, so this
file keeps the same finite-state discipline with a small standard-library
explorer and records that limitation in the adoption log.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import product
import json
from typing import Callable, Iterable


LOCAL_LANES = ("kb-sleep", "kb-dream", "kb-architect")
ORG_LANES = ("kb-org-contribute", "kb-org-maintenance")


@dataclass(frozen=True)
class Input:
    kind: str
    lane: str = ""
    card_hash: str = ""
    ui_running: bool = False


@dataclass(frozen=True)
class Output:
    label: str
    detail: str = ""


@dataclass(frozen=True)
class State:
    local_lock: str = ""
    org_lock: str = ""
    org_imports: tuple[str, ...] = ()
    org_main: tuple[str, ...] = ()
    local_known: tuple[str, ...] = ()
    upload_effects: tuple[str, ...] = ()
    download_effects: tuple[str, ...] = ()
    update_status: str = "current"
    update_available: bool = False
    user_requested: bool = False
    ui_running: bool = False


@dataclass(frozen=True)
class Step:
    block: str
    input: Input
    output: Output
    old_state: State
    new_state: State


@dataclass(frozen=True)
class Trace:
    inputs: tuple[Input, ...]
    steps: tuple[Step, ...]
    final_state: State


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    trace: Trace | None = None


def _append_unique(values: tuple[str, ...], value: str) -> tuple[str, ...]:
    return values if value in values else values + (value,)


def _remove(values: tuple[str, ...], value: str) -> tuple[str, ...]:
    return tuple(item for item in values if item != value)


class MaintenanceLaneBlock:
    """Input x State -> Set(Output x State) for local and organization locks."""

    name = "MaintenanceLaneBlock"
    reads = ("local_lock", "org_lock")
    writes = ("local_lock", "org_lock")
    idempotency = "Repeated start for the same lane heartbeats; different lane in the same group waits. Failure releases the owned lock."

    def apply(self, event: Input, state: State) -> Iterable[tuple[Output, State]]:
        if event.kind not in {"start_lane", "finish_lane", "fail_lane"}:
            return
        lanes = LOCAL_LANES if event.lane in LOCAL_LANES else ORG_LANES if event.lane in ORG_LANES else ()
        if not lanes:
            yield Output("unknown_lane", event.lane), state
            return
        lock_field = "local_lock" if lanes == LOCAL_LANES else "org_lock"
        held = getattr(state, lock_field)
        group = "local" if lock_field == "local_lock" else "org"
        if event.kind == "start_lane":
            if held in {"", event.lane}:
                yield Output(f"{group}_lane_acquired", event.lane), replace(state, **{lock_field: event.lane})
            else:
                yield Output(f"{group}_lane_wait", f"{event.lane} waits for {held}"), state
            return
        if held == event.lane:
            label = f"{group}_lane_failed_release" if event.kind == "fail_lane" else f"{group}_lane_released"
            yield Output(label, event.lane), replace(state, **{lock_field: ""})
        else:
            yield Output(f"{group}_lane_release_ignored", event.lane), state


class OrganizationExchangeBlock:
    """Input x State -> Set(Output x State) for imports/main exchange."""

    name = "OrganizationExchangeBlock"
    reads = ("org_imports", "org_main", "local_known", "upload_effects", "download_effects")
    writes = ("org_imports", "org_main", "local_known", "upload_effects", "download_effects")
    idempotency = "A content hash can be uploaded, promoted, or downloaded once; repeats are no-op outputs."

    def __init__(self, *, broken: bool = False) -> None:
        self.broken = broken

    def apply(self, event: Input, state: State) -> Iterable[tuple[Output, State]]:
        if event.kind == "contribute":
            card_hash = event.card_hash
            if not card_hash:
                yield Output("upload_rejected", "missing hash"), state
                return
            if not self.broken and (
                card_hash in state.org_imports
                or card_hash in state.org_main
                or card_hash in state.upload_effects
                or card_hash in state.local_known
            ):
                yield Output("upload_duplicate_skipped", card_hash), state
                return
            yield Output("uploaded_to_imports", card_hash), replace(
                state,
                org_imports=_append_unique(state.org_imports, card_hash),
                upload_effects=state.upload_effects + (card_hash,),
            )
            return
        if event.kind == "promote_import":
            card_hash = event.card_hash
            if card_hash not in state.org_imports:
                yield Output("promote_missing_import", card_hash), state
                return
            yield Output("promoted_to_main", card_hash), replace(
                state,
                org_imports=_remove(state.org_imports, card_hash),
                org_main=_append_unique(state.org_main, card_hash),
            )
            return
        if event.kind == "download":
            card_hash = event.card_hash
            if card_hash in state.local_known:
                yield Output("download_duplicate_skipped", card_hash), state
                return
            if card_hash in state.org_main:
                yield Output("downloaded_from_main", card_hash), replace(
                    state,
                    local_known=state.local_known + (card_hash,),
                    download_effects=state.download_effects + (card_hash,),
                )
                return
            if self.broken and card_hash in state.org_imports:
                yield Output("downloaded_from_imports", card_hash), replace(
                    state,
                    local_known=state.local_known + (card_hash,),
                    download_effects=state.download_effects + (card_hash,),
                )
                return
            yield Output("download_no_main_card", card_hash), state


class SoftwareUpdateBlock:
    """Input x State -> Set(Output x State) for the user-prepared update gate."""

    name = "SoftwareUpdateBlock"
    reads = ("update_status", "update_available", "user_requested", "ui_running")
    writes = ("update_status", "update_available", "user_requested", "ui_running")
    idempotency = "Architect check marks upgrading only once, only after user request and UI closure."

    def apply(self, event: Input, state: State) -> Iterable[tuple[Output, State]]:
        if event.kind == "remote_available":
            status = "prepared" if state.user_requested and state.update_status != "failed" else "available"
            yield Output("remote_update_available"), replace(
                state,
                update_status=status,
                update_available=True,
                user_requested=False if state.update_status == "failed" else state.user_requested,
            )
            return
        if event.kind == "prepare_update":
            if not state.update_available:
                yield Output("prepare_ignored_no_update"), replace(state, user_requested=False, update_status="current")
                return
            yield Output("update_prepared"), replace(state, user_requested=True, update_status="prepared")
            return
        if event.kind == "ui_state":
            yield Output("ui_state_changed", str(event.ui_running)), replace(state, ui_running=event.ui_running)
            return
        if event.kind == "architect_update_check":
            if state.update_status == "upgrading":
                yield Output("update_already_upgrading"), state
                return
            if state.update_status == "failed":
                yield Output("update_failed_awaiting_user"), replace(state, user_requested=False)
                return
            if not state.update_available:
                yield Output("update_noop_no_update"), state
                return
            if not state.user_requested:
                yield Output("update_waits_for_user"), state
                return
            if state.ui_running:
                yield Output("update_waits_for_ui_close"), state
                return
            yield Output("apply_update"), replace(state, update_status="upgrading")
            return
        if event.kind == "update_done":
            if state.update_status != "upgrading":
                yield Output("update_done_ignored"), state
                return
            yield Output("update_marked_current"), replace(
                state,
                update_status="current",
                update_available=False,
                user_requested=False,
            )
            return
        if event.kind == "update_failed":
            if state.update_status != "upgrading":
                yield Output("update_failed_ignored"), state
                return
            yield Output("update_marked_failed"), replace(state, update_status="failed", user_requested=False)


BLOCKS = (MaintenanceLaneBlock(), OrganizationExchangeBlock(), SoftwareUpdateBlock())
BROKEN_BLOCKS = (MaintenanceLaneBlock(), OrganizationExchangeBlock(broken=True), SoftwareUpdateBlock())


EXTERNAL_INPUTS = (
    Input("start_lane", lane="kb-sleep"),
    Input("start_lane", lane="kb-dream"),
    Input("finish_lane", lane="kb-sleep"),
    Input("finish_lane", lane="kb-dream"),
    Input("fail_lane", lane="kb-sleep"),
    Input("fail_lane", lane="kb-dream"),
    Input("start_lane", lane="kb-org-contribute"),
    Input("start_lane", lane="kb-org-maintenance"),
    Input("finish_lane", lane="kb-org-contribute"),
    Input("finish_lane", lane="kb-org-maintenance"),
    Input("fail_lane", lane="kb-org-contribute"),
    Input("fail_lane", lane="kb-org-maintenance"),
    Input("contribute", card_hash="h1"),
    Input("promote_import", card_hash="h1"),
    Input("download", card_hash="h1"),
    Input("remote_available"),
    Input("prepare_update"),
    Input("ui_state", ui_running=True),
    Input("ui_state", ui_running=False),
    Input("architect_update_check"),
    Input("update_done"),
    Input("update_failed"),
)

INITIAL_STATES = (
    State(),
    State(org_imports=("h1",)),
    State(org_main=("h1",)),
    State(update_status="prepared", update_available=True, user_requested=True, ui_running=True),
    State(update_status="prepared", update_available=True, user_requested=True, ui_running=False),
)


def run_sequence(inputs: tuple[Input, ...], initial: State, *, broken: bool = False) -> Trace:
    state = initial
    steps: list[Step] = []
    blocks = BROKEN_BLOCKS if broken else BLOCKS
    for event in inputs:
        emitted = False
        for block in blocks:
            results = list(block.apply(event, state))
            if not results:
                continue
            if len(results) != 1:
                raise AssertionError(f"{block.name} produced nondeterministic results in this model")
            output, new_state = results[0]
            steps.append(Step(block.name, event, output, state, new_state))
            state = new_state
            emitted = True
            break
        if not emitted:
            steps.append(Step("Noop", event, Output("ignored"), state, state))
    return Trace(inputs=inputs, steps=tuple(steps), final_state=state)


def invariant_no_duplicate_side_effects(trace: Trace) -> CheckResult:
    state = trace.final_state
    for field in ("upload_effects", "download_effects"):
        values = getattr(state, field)
        if len(values) != len(set(values)):
            return CheckResult(field, False, f"duplicate side effects in {field}", trace)
    return CheckResult("no_duplicate_side_effects", True)


def invariant_download_only_from_main(trace: Trace) -> CheckResult:
    for step in trace.steps:
        if step.output.label == "downloaded_from_imports":
            return CheckResult("download_only_from_main", False, "downloaded from imports", trace)
        if step.output.label == "downloaded_from_main" and step.input.card_hash not in step.old_state.org_main:
            return CheckResult("download_only_from_main", False, "main download lacked prior main card", trace)
    return CheckResult("download_only_from_main", True)


def invariant_lock_groups_are_exclusive(trace: Trace) -> CheckResult:
    for step in trace.steps:
        if step.output.label == "local_lane_acquired":
            held = step.old_state.local_lock
            if held and held != step.input.lane:
                return CheckResult("local_lock_exclusive", False, "local lane acquired while another local lane held lock", trace)
        if step.output.label == "org_lane_acquired":
            held = step.old_state.org_lock
            if held and held != step.input.lane:
                return CheckResult("org_lock_exclusive", False, "org lane acquired while another org lane held lock", trace)
    return CheckResult("lock_groups_are_exclusive", True)


def invariant_update_apply_gate(trace: Trace) -> CheckResult:
    for step in trace.steps:
        if step.output.label != "apply_update":
            continue
        old = step.old_state
        if old.update_status != "prepared" or not old.user_requested or old.ui_running:
            return CheckResult("update_apply_gate", False, "update applied without prepared user request and closed UI", trace)
    return CheckResult("update_apply_gate", True)


INVARIANTS: tuple[Callable[[Trace], CheckResult], ...] = (
    invariant_no_duplicate_side_effects,
    invariant_download_only_from_main,
    invariant_lock_groups_are_exclusive,
    invariant_update_apply_gate,
)

REQUIRED_LABELS = {
    "local_lane_acquired",
    "local_lane_wait",
    "local_lane_failed_release",
    "org_lane_acquired",
    "org_lane_wait",
    "org_lane_failed_release",
    "uploaded_to_imports",
    "upload_duplicate_skipped",
    "promoted_to_main",
    "downloaded_from_main",
    "download_duplicate_skipped",
    "update_waits_for_ui_close",
    "update_failed_awaiting_user",
    "apply_update",
}


def explore(*, max_sequence_length: int = 3, broken: bool = False) -> dict[str, object]:
    traces: list[Trace] = []
    labels: set[str] = set()
    for initial in INITIAL_STATES:
        for length in range(1, max_sequence_length + 1):
            for sequence in product(EXTERNAL_INPUTS, repeat=length):
                trace = run_sequence(tuple(sequence), initial, broken=broken)
                traces.append(trace)
                labels.update(step.output.label for step in trace.steps)
                for invariant in INVARIANTS:
                    result = invariant(trace)
                    if not result.ok:
                        return {
                            "ok": False,
                            "broken_model": broken,
                            "failure": result.name,
                            "detail": result.detail,
                            "trace": trace_to_dict(result.trace or trace),
                            "checked_traces": len(traces),
                        }
    missing = sorted(REQUIRED_LABELS - labels)
    if missing:
        return {
            "ok": False,
            "broken_model": broken,
            "failure": "missing_required_labels",
            "detail": ", ".join(missing),
            "checked_traces": len(traces),
        }
    return {
        "ok": True,
        "broken_model": broken,
        "checked_traces": len(traces),
        "labels_seen": sorted(labels),
        "scenario_review": {
            "repeated_inputs": "covered by repeated sequence exploration up to length 3",
            "human_expectation": (
                "maintenance lanes wait inside their group, org imports are not downloaded, "
                "duplicate hashes do not create duplicate exchange side effects, and software "
                "updates apply only after user preparation with the UI closed"
            ),
        },
        "loop_stuck_review": {
            "local_lock": "lock states have explicit finish_lane escape edges; progress still depends on the running lane finishing",
            "organization_lock": "organization lock states have explicit finish_lane escape edges; progress still depends on the running lane finishing",
            "update_upgrading": "upgrading blocks UI startup until the update skill marks current or failed; this model treats that external completion as a fairness assumption",
            "status": "known_limitations_documented",
        },
    }


def trace_to_dict(trace: Trace) -> dict[str, object]:
    return {
        "inputs": [input_obj.__dict__ for input_obj in trace.inputs],
        "steps": [
            {
                "block": step.block,
                "input": step.input.__dict__,
                "output": step.output.__dict__,
                "old_state": step.old_state.__dict__,
                "new_state": step.new_state.__dict__,
            }
            for step in trace.steps
        ],
        "final_state": trace.final_state.__dict__,
    }


def main() -> int:
    expected = explore()
    broken = explore(broken=True)
    report = {
        "model": "khaos_brain_function_flow",
        "flowguard_package_available": False,
        "correct_model": expected,
        "broken_variant": broken,
        "broken_variant_expected_to_fail": True,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if expected.get("ok") and not broken.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
