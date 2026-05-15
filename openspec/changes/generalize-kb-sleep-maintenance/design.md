## Context

Sleep maintenance currently has the raw ingredients for better generalization: feedback events preserve `project_ref`, `thread_ref`, `workspace_root`, timestamps, and contrastive evidence; consolidation already summarizes provenance and same-project timelines; semantic review can rewrite, promote, demote, deprecate, or adjust confidence on cards.

The missing piece is a required judgment layer. Project names are already discouraged in primary routes, but the system does not force Sleep to classify whether evidence is project-local, skill-specific, single-project but generalizable, or broadly supported across projects. As a result, new candidate scaffolds and old-card rewrites can remain too project-shaped even when the reusable lesson is more general, while skill-bound evidence can also be over-generalized if the skill context is stripped away.

## Goals / Non-Goals

**Goals:**
- Make evidence scope classification explicit in Sleep proposal output.
- Preserve Skill/plugin/tool-specific context when the lesson is genuinely about using that capability.
- Use project/thread chronology to interpret evidence without turning project names into default card scope.
- Improve new candidate scaffolds so they carry generalization guidance and provenance evidence.
- Improve existing-card review so Sleep can recommend generalizing older project-flavored cards.
- Require semantic review apply plans to include scope assessment for card-changing actions.
- Keep the implementation file-based, inspectable, and reversible.
- Use FlowGuard before production code edits to check the state transitions and prevent over-generalization or under-generalization.

**Non-Goals:**
- Do not add embeddings, vector search, databases, or external services.
- Do not introduce automatic trusted-card rewrites without an AI-authored semantic review plan.
- Do not force every project-local card to become general.
- Do not change canonical routes during i18n display cleanup.

## Decisions

### Decision 1: Add scope assessment as proposal metadata

Sleep proposal actions will expose a scope assessment with a small fixed vocabulary:

- `project-local`: the evidence depends on a named project, repository, workspace, or local mechanism.
- `skill-specific`: the evidence depends on a named Codex Skill, plugin, connector, or tool capability and should keep that capability in the route or wording.
- `single-project-generalizable`: evidence currently comes from one project or workspace, but the causal rule is written in a reusable functional form.
- `cross-project-general`: evidence spans multiple projects, workspaces, or independent contexts.
- `insufficient-evidence`: the action lacks enough evidence to decide the scope safely.

Alternative considered: infer scope only inside the maintenance prompt. That would be cheaper, but harder to test and easier for future agents to skip. Proposal metadata gives both humans and tests a visible object to inspect.

### Decision 2: Keep scope assessment advisory for candidate creation but mandatory for semantic apply

Candidate scaffolds may include scope assessment and guidance even when they are low-confidence seeds. Semantic review apply decisions must include a `scope_assessment` object before they can change or preserve an active card surface.

Alternative considered: block all candidate creation without high-confidence scope. That would be too strict because low-confidence seed candidates are useful as retrieval hooks. The stricter gate belongs where trusted or active card content changes.

### Decision 3: Treat same-project repetition as chronology evidence, not automatic generality evidence

Repeated observations from the same project strengthen the story of what happened inside that project. Cross-project evidence strengthens generality. Single-project evidence can still be generalizable when the rule is clearly functional, but Sleep must say why.

Alternative considered: use event count alone to raise generality. That would produce brittle cards because one noisy project can look like many independent confirmations.

### Decision 4: Preserve skill-bound scope as a valid non-project-specific outcome

Evidence about using a named Skill, plugin, connector, or tool should not be forced into a broad project-agnostic rule. Sleep can still generalize within that capability, such as "when using the presentations Skill for deck work..." or "when a GitHub release task invokes the release Skill...", but it should keep the capability name when the result depends on that capability.

Alternative considered: treat skills as normal tags only. That loses the operational trigger that future agents need when choosing whether to invoke or avoid a Skill.

### Decision 5: Extend existing-card review rather than adding a separate old-card maintenance lane

The existing `review-entry-update` action already represents old-card review pressure. This change extends its signals with generalization review instead of creating a new action type.

Alternative considered: add a new `review-generalization` action. That would be clearer in isolation but would duplicate the semantic review flow and create more suppression/decision bookkeeping.

### Decision 6: Validate the flow with FlowGuard and focused tests

Before code edits, use a small FlowGuard model for the Sleep generalization decision flow:

`observation cluster + existing card state -> proposal signal -> optional semantic review -> applied or history-only outcome`

The model should catch these bad states:

- project-local cards are generalized without an explicit justification
- skill-specific cards lose the skill or plugin boundary needed for future invocation
- generalizable evidence stays trapped in project-only wording
- semantic apply changes a card without scope assessment
- same-project repetition is treated as cross-project evidence

Tests then verify concrete implementation behavior.

## Risks / Trade-offs

- Over-generalization risk -> Mitigation: keep `project-local` as a first-class valid outcome and require reasoning for single-project generalization.
- Skill-bound over-generalization risk -> Mitigation: keep `skill-specific` as a first-class valid outcome when a lesson depends on a named Skill, plugin, connector, or tool capability.
- Under-generalization risk -> Mitigation: existing-card review will explicitly recommend `rewrite-as-general-rule` when old cards look project-shaped but evidence supports a functional rule.
- Prompt-only drift risk -> Mitigation: encode scope assessment in proposal output and semantic-review validation, not only in prose.
- Schema churn risk -> Mitigation: keep new fields additive and local to proposal/action/decision artifacts; do not require a new public card schema field for v0.1.
- Release risk -> Mitigation: run FlowGuard, focused tests, install sync/check, release audit, and version/tag/release alignment before publishing.

## Migration Plan

1. Add documentation and prompt rules for Sleep generalization review.
2. Add implementation helpers that compute provenance scope, project/source summaries, and generalization recommendations.
3. Include scope assessment in new candidate scaffold previews and `review-entry-update` action annotations.
4. Require `scope_assessment` in semantic review apply decisions for `keep`, `rewrite`, `adjust-confidence`, `promote`, `demote`, and `deprecate`.
5. Add tests for candidate scaffolds, old-card review, project-local preservation, and semantic-review validation.
6. Run focused tests and broader regression checks.
7. Sync installed Codex skills/automations with `scripts/install_codex_kb.py --json` and verify with `--check --json`.
8. Release as a patch or minor version based on the final public delta and release audit.
