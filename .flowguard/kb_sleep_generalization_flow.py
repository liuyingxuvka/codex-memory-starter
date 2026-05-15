"""FlowGuard model for KB Sleep generalization review.

Risk purpose:
This FlowGuard model reviews the `generalize-kb-sleep-maintenance` change before
and after production edits. It guards against two user-facing failures: Sleep
over-generalizing project-local cards into false universal rules, and Sleep
leaving reusable lessons trapped in project-shaped candidate or trusted-card
wording. Future agents should run this file when editing Sleep consolidation,
candidate scaffold, or semantic review behavior. Companion command:
`python .flowguard\\kb_sleep_generalization_flow.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterable

from flowguard import Explorer, FunctionResult, Invariant, InvariantResult, Workflow, run_exact_sequence


SCOPE_PROJECT_LOCAL = "project-local"
SCOPE_SKILL_SPECIFIC = "skill-specific"
SCOPE_SINGLE_PROJECT_GENERALIZABLE = "single-project-generalizable"
SCOPE_CROSS_PROJECT_GENERAL = "cross-project-general"
SCOPE_INSUFFICIENT = "insufficient-evidence"

RECOMMEND_KEEP_PROJECT_LOCAL = "keep-project-local"
RECOMMEND_KEEP_SKILL_SPECIFIC = "keep-skill-specific"
RECOMMEND_REWRITE_GENERAL = "rewrite-as-general-rule"
RECOMMEND_CREATE_GENERAL = "create-general-candidate"
RECOMMEND_HISTORY_ONLY = "history-only"


@dataclass(frozen=True)
class GeneralizationCase:
    kind: str
    project_count: int
    has_functional_rule: bool = False
    has_project_specific_dependency: bool = False
    has_skill_specific_dependency: bool = False
    existing_card_project_shaped: bool = False
    semantic_apply_requested: bool = False
    scope_assessment_present: bool = False


@dataclass(frozen=True)
class GeneralizationState:
    decisions: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneralizationDecision:
    evidence: GeneralizationCase
    scope: str
    recommendation: str
    semantic_apply_allowed: bool
    semantic_apply_blocked_reason: str = ""


class SleepGeneralizationBlock:
    """Input x State -> Set(Output x State) for Sleep scope classification."""

    name = "SleepGeneralizationBlock"
    reads = ("decisions",)
    writes = ("decisions",)
    accepted_input_type = GeneralizationCase
    input_description = "GeneralizationCase"
    output_description = "GeneralizationDecision"
    idempotency = "The same evidence cluster produces the same scope classification and card-surface recommendation."

    def __init__(self, *, variant: str = "accepted") -> None:
        self.variant = variant

    def apply(self, input_obj: GeneralizationCase, state: GeneralizationState) -> Iterable[FunctionResult]:
        scope = self._scope(input_obj)
        recommendation = self._recommendation(input_obj, scope)
        semantic_apply_allowed = False
        blocked_reason = ""
        if input_obj.semantic_apply_requested:
            if input_obj.scope_assessment_present:
                semantic_apply_allowed = True
            else:
                blocked_reason = "missing-scope-assessment"

        decision = GeneralizationDecision(
            evidence=input_obj,
            scope=scope,
            recommendation=recommendation,
            semantic_apply_allowed=semantic_apply_allowed,
            semantic_apply_blocked_reason=blocked_reason,
        )
        label_parts = [input_obj.kind, scope, recommendation]
        if input_obj.semantic_apply_requested:
            label_parts.append("semantic-apply-allowed" if semantic_apply_allowed else "semantic-apply-blocked")
        yield FunctionResult(
            output=decision,
            new_state=GeneralizationState(state.decisions + (f"{input_obj.kind}:{scope}:{recommendation}",)),
            label="__".join(label_parts),
            reason="Sleep classifies evidence scope before creating or changing card surfaces.",
        )

    def _scope(self, evidence: GeneralizationCase) -> str:
        if self.variant == "bad_same_project_cross" and evidence.project_count == 1 and evidence.has_functional_rule:
            return SCOPE_CROSS_PROJECT_GENERAL
        if self.variant == "bad_project_local_general" and evidence.has_project_specific_dependency:
            return SCOPE_SINGLE_PROJECT_GENERALIZABLE
        if self.variant == "bad_skill_specific_general" and evidence.has_skill_specific_dependency:
            return SCOPE_SINGLE_PROJECT_GENERALIZABLE
        if evidence.has_project_specific_dependency:
            return SCOPE_PROJECT_LOCAL
        if evidence.has_skill_specific_dependency:
            return SCOPE_SKILL_SPECIFIC
        if evidence.has_functional_rule and evidence.project_count > 1:
            return SCOPE_CROSS_PROJECT_GENERAL
        if evidence.has_functional_rule and evidence.project_count == 1:
            return SCOPE_SINGLE_PROJECT_GENERALIZABLE
        return SCOPE_INSUFFICIENT

    def _recommendation(self, evidence: GeneralizationCase, scope: str) -> str:
        if self.variant == "bad_old_card_stays_project_shaped" and evidence.existing_card_project_shaped:
            return RECOMMEND_KEEP_PROJECT_LOCAL
        if scope == SCOPE_PROJECT_LOCAL:
            return RECOMMEND_KEEP_PROJECT_LOCAL
        if scope == SCOPE_SKILL_SPECIFIC:
            return RECOMMEND_KEEP_SKILL_SPECIFIC
        if scope == SCOPE_INSUFFICIENT:
            return RECOMMEND_HISTORY_ONLY
        if evidence.existing_card_project_shaped:
            return RECOMMEND_REWRITE_GENERAL
        return RECOMMEND_CREATE_GENERAL


def build_workflow(*, variant: str = "accepted") -> Workflow:
    return Workflow((SleepGeneralizationBlock(variant=variant),), name=f"kb_sleep_generalization_{variant}")


WORKFLOW = build_workflow()
INITIAL_STATES = (GeneralizationState(),)
INPUTS = (
    GeneralizationCase("single_project_generalizable_new", 1, has_functional_rule=True),
    GeneralizationCase(
        "single_project_generalizable_old",
        1,
        has_functional_rule=True,
        existing_card_project_shaped=True,
    ),
    GeneralizationCase(
        "project_local_lane_card",
        1,
        has_functional_rule=True,
        has_project_specific_dependency=True,
        existing_card_project_shaped=True,
    ),
    GeneralizationCase(
        "skill_specific_release_card",
        1,
        has_functional_rule=True,
        has_skill_specific_dependency=True,
        existing_card_project_shaped=True,
    ),
    GeneralizationCase("cross_project_general", 2, has_functional_rule=True),
    GeneralizationCase("insufficient_evidence", 1),
    GeneralizationCase(
        "semantic_apply_without_scope",
        1,
        has_functional_rule=True,
        semantic_apply_requested=True,
        scope_assessment_present=False,
    ),
    GeneralizationCase(
        "semantic_apply_with_scope",
        1,
        has_functional_rule=True,
        semantic_apply_requested=True,
        scope_assessment_present=True,
    ),
)


def same_project_is_not_cross_project(state: GeneralizationState, trace: object) -> InvariantResult:
    for decision_ref in state.decisions:
        if decision_ref.startswith("single_project_generalizable_") and f":{SCOPE_CROSS_PROJECT_GENERAL}:" in decision_ref:
            return InvariantResult.fail(
                "Same-project evidence was treated as cross-project general evidence.",
                {"decision": decision_ref},
            )
    if not hasattr(trace, "steps"):
        return InvariantResult.pass_()
    for step in trace.steps:
        decision = getattr(step, "output", None)
        if not isinstance(decision, GeneralizationDecision):
            continue
        if (
            decision.evidence.project_count == 1
            and not decision.evidence.has_project_specific_dependency
            and decision.scope == SCOPE_CROSS_PROJECT_GENERAL
        ):
            return InvariantResult.fail(
                "Same-project evidence was treated as cross-project general evidence.",
                {"case": decision.evidence.kind, "scope": decision.scope},
            )
    return InvariantResult.pass_()


def project_local_stays_bounded(state: GeneralizationState, trace: object) -> InvariantResult:
    for decision_ref in state.decisions:
        if decision_ref.startswith("project_local_") and f":{SCOPE_PROJECT_LOCAL}:" not in decision_ref:
            return InvariantResult.fail(
                "Project-specific evidence was not kept project-local.",
                {"decision": decision_ref},
            )
        if decision_ref.startswith("project_local_") and decision_ref.endswith(f":{RECOMMEND_REWRITE_GENERAL}"):
            return InvariantResult.fail(
                "Project-specific evidence was recommended for generic rewrite.",
                {"decision": decision_ref},
            )
    if not hasattr(trace, "steps"):
        return InvariantResult.pass_()
    for step in trace.steps:
        decision = getattr(step, "output", None)
        if not isinstance(decision, GeneralizationDecision):
            continue
        if decision.evidence.has_project_specific_dependency and decision.scope != SCOPE_PROJECT_LOCAL:
            return InvariantResult.fail(
                "Project-specific evidence was not kept project-local.",
                {"case": decision.evidence.kind, "scope": decision.scope},
            )
        if (
            decision.evidence.has_project_specific_dependency
            and decision.recommendation == RECOMMEND_REWRITE_GENERAL
        ):
            return InvariantResult.fail(
                "Project-specific evidence was recommended for generic rewrite.",
                {"case": decision.evidence.kind},
            )
    return InvariantResult.pass_()


def skill_specific_stays_bounded(state: GeneralizationState, trace: object) -> InvariantResult:
    for decision_ref in state.decisions:
        if decision_ref.startswith("skill_specific_") and f":{SCOPE_SKILL_SPECIFIC}:" not in decision_ref:
            return InvariantResult.fail(
                "Skill-specific evidence was not kept skill-specific.",
                {"decision": decision_ref},
            )
        if decision_ref.startswith("skill_specific_") and decision_ref.endswith(f":{RECOMMEND_REWRITE_GENERAL}"):
            return InvariantResult.fail(
                "Skill-specific evidence was recommended for capability-independent rewrite.",
                {"decision": decision_ref},
            )
    if not hasattr(trace, "steps"):
        return InvariantResult.pass_()
    for step in trace.steps:
        decision = getattr(step, "output", None)
        if not isinstance(decision, GeneralizationDecision):
            continue
        if decision.evidence.has_skill_specific_dependency and decision.scope != SCOPE_SKILL_SPECIFIC:
            return InvariantResult.fail(
                "Skill-specific evidence was not kept skill-specific.",
                {"case": decision.evidence.kind, "scope": decision.scope},
            )
        if (
            decision.evidence.has_skill_specific_dependency
            and decision.recommendation == RECOMMEND_REWRITE_GENERAL
        ):
            return InvariantResult.fail(
                "Skill-specific evidence was recommended for capability-independent rewrite.",
                {"case": decision.evidence.kind},
            )
    return InvariantResult.pass_()


def reusable_old_cards_get_generalization_review(state: GeneralizationState, trace: object) -> InvariantResult:
    for decision_ref in state.decisions:
        if decision_ref.startswith("single_project_generalizable_old:") and not decision_ref.endswith(
            f":{RECOMMEND_REWRITE_GENERAL}"
        ):
            return InvariantResult.fail(
                "A project-shaped old card with reusable evidence was not recommended for generic rewrite.",
                {"decision": decision_ref},
            )
    if not hasattr(trace, "steps"):
        return InvariantResult.pass_()
    for step in trace.steps:
        decision = getattr(step, "output", None)
        if not isinstance(decision, GeneralizationDecision):
            continue
        evidence = decision.evidence
        is_reusable_project_shaped_old_card = (
            evidence.existing_card_project_shaped
            and evidence.has_functional_rule
            and not evidence.has_project_specific_dependency
        )
        if is_reusable_project_shaped_old_card and decision.recommendation != RECOMMEND_REWRITE_GENERAL:
            return InvariantResult.fail(
                "A project-shaped old card with reusable evidence was not recommended for generic rewrite.",
                {"case": evidence.kind, "recommendation": decision.recommendation},
            )
    return InvariantResult.pass_()


def semantic_apply_requires_scope_assessment(state: GeneralizationState, trace: object) -> InvariantResult:
    if not hasattr(trace, "steps"):
        return InvariantResult.pass_()
    for step in trace.steps:
        decision = getattr(step, "output", None)
        if not isinstance(decision, GeneralizationDecision):
            continue
        evidence = decision.evidence
        if evidence.semantic_apply_requested and not evidence.scope_assessment_present and decision.semantic_apply_allowed:
            return InvariantResult.fail(
                "Semantic review apply was allowed without scope assessment.",
                {"case": evidence.kind},
            )
    return InvariantResult.pass_()


INVARIANTS = (
    Invariant(
        "same_project_is_not_cross_project",
        "Same-project repetition is chronology evidence, not automatic cross-project generality.",
        same_project_is_not_cross_project,
    ),
    Invariant(
        "project_local_stays_bounded",
        "Cards depending on a project-specific mechanism must stay project-local.",
        project_local_stays_bounded,
    ),
    Invariant(
        "skill_specific_stays_bounded",
        "Cards depending on a Skill, plugin, connector, or tool capability must keep that boundary.",
        skill_specific_stays_bounded,
    ),
    Invariant(
        "reusable_old_cards_get_generalization_review",
        "Old project-shaped cards with functional evidence should be reviewed for generic rewrite.",
        reusable_old_cards_get_generalization_review,
    ),
    Invariant(
        "semantic_apply_requires_scope_assessment",
        "Semantic review apply must not change card surfaces without scope assessment.",
        semantic_apply_requires_scope_assessment,
    ),
)


def _report_dict(report: object) -> dict[str, object]:
    if hasattr(report, "to_dict"):
        return report.to_dict()
    return json.loads(report.to_json_text())


def _compact_report(report: object) -> dict[str, object]:
    payload = _report_dict(report)
    traces = payload.get("traces", []) or []
    labels_seen = sorted({label for trace in traces for label in trace.get("labels", [])})
    return {
        "ok": payload.get("ok"),
        "summary": payload.get("summary"),
        "violation_count": len(payload.get("violations", []) or []),
        "reachability_failure_count": len(payload.get("reachability_failures", []) or []),
        "labels_seen": labels_seen,
    }


def _run_case(case: GeneralizationCase, *, variant: str = "accepted") -> dict[str, object]:
    report = run_exact_sequence(
        workflow=build_workflow(variant=variant),
        initial_state=GeneralizationState(),
        external_input_sequence=(case,),
        invariants=INVARIANTS,
    )
    payload = report.to_dict()
    traces = payload.get("traces", []) or []
    labels_seen = sorted({label for trace in traces for label in trace.get("labels", [])})
    return {
        "observed_status": payload.get("observed_status"),
        "model_ok": payload.get("model_report", {}).get("ok"),
        "labels_seen": labels_seen,
        "violation_names": payload.get("observed_violation_names", []),
    }


def main() -> int:
    explorer_report = Explorer(
        workflow=WORKFLOW,
        initial_states=INITIAL_STATES,
        external_inputs=INPUTS,
        invariants=INVARIANTS,
        max_sequence_length=1,
        required_labels=(
            "single_project_generalizable_new__single-project-generalizable__create-general-candidate",
            "single_project_generalizable_old__single-project-generalizable__rewrite-as-general-rule",
            "project_local_lane_card__project-local__keep-project-local",
            "skill_specific_release_card__skill-specific__keep-skill-specific",
            "cross_project_general__cross-project-general__create-general-candidate",
            "semantic_apply_without_scope__single-project-generalizable__create-general-candidate__semantic-apply-blocked",
            "semantic_apply_with_scope__single-project-generalizable__create-general-candidate__semantic-apply-allowed",
        ),
    ).explore()
    scenarios = {case.kind: _run_case(case) for case in INPUTS}
    bad_same_project = _run_case(INPUTS[0], variant="bad_same_project_cross")
    bad_project_local = _run_case(INPUTS[2], variant="bad_project_local_general")
    bad_skill_specific = _run_case(INPUTS[3], variant="bad_skill_specific_general")
    bad_old_card = _run_case(INPUTS[1], variant="bad_old_card_stays_project_shaped")
    semantic_without_scope_labels = scenarios["semantic_apply_without_scope"]["labels_seen"]
    semantic_with_scope_labels = scenarios["semantic_apply_with_scope"]["labels_seen"]
    question_results = {
        "accepted_flow_passes": bool(explorer_report.ok),
        "same_project_cross_project_bad_variant_rejected": bad_same_project["observed_status"] != "ok",
        "project_local_bad_variant_rejected": bad_project_local["observed_status"] != "ok",
        "skill_specific_bad_variant_rejected": bad_skill_specific["observed_status"] != "ok",
        "old_card_under_generalization_bad_variant_rejected": bad_old_card["observed_status"] != "ok",
        "semantic_apply_without_scope_is_blocked": any(
            str(label).endswith("__semantic-apply-blocked") for label in semantic_without_scope_labels
        ),
        "semantic_apply_with_scope_is_allowed": any(
            str(label).endswith("__semantic-apply-allowed") for label in semantic_with_scope_labels
        ),
    }
    result = {
        "model": "kb_sleep_generalization_flow",
        "flowguard_schema_version": "1.0",
        "question_results": question_results,
        "explorer_report": _compact_report(explorer_report),
        "scenarios": scenarios,
        "bad_variants": {
            "bad_same_project_cross": bad_same_project,
            "bad_project_local_general": bad_project_local,
            "bad_skill_specific_general": bad_skill_specific,
            "bad_old_card_stays_project_shaped": bad_old_card,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if all(question_results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
