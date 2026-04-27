# Dream Exploration Runbook

This runbook defines a separate `kb-dreamer` maintenance pass for bounded exploration. It is intentionally narrower than “autonomous self-improvement.” The goal is to test adjacent possibilities without contaminating trusted memory or colliding with sleep maintenance.

`PROJECT_SPEC.md` remains authoritative. `docs/maintenance_agent_worldview.md` defines the shared Sleep/Dream/Architect judgment model. If this runbook and the spec disagree, follow the spec and simplify the runbook.

The repository installer is expected to provision a repo-managed `KB Dream` cron automation under `$CODEX_HOME/automations/`. Re-running `python scripts/install_codex_kb.py --json` on another machine should refresh that schedule automatically. The automation spec should keep model selection policy-based: strongest available model plus deepest supported reasoning, resolved during install rather than pinned to a specific model version.

## Purpose

- `sleep` consolidates real task evidence, maintenance decisions, and current-card state.
- `dream` explores nearby but not-yet-settled hypotheses through small, auditable experiments.

Dream mode is valid only when it remains:

- grounded in existing cards, misses, or route gaps
- bounded in action surface
- explicit about provenance
- candidate-only or history-only in write-back
- explicit about sandbox artifacts for any local experiment it runs

It is not a license for free-form tool wandering or hidden self-belief growth.

Before selecting experiments, read the shared maintenance-agent worldview. Treat Dream as an experiment researcher: it should clarify grounded hypotheses, record evidence strength, and hand results to Sleep or Architect without pretending sandbox evidence is confirmed real-world experience.

## Separation From Sleep

- Run dream mode in a different automation, thread, or maintenance session from sleep mode.
- Do not run dream mode while a sleep pass is active or while sleep artifacts for the same repository state are still unresolved.
- If consolidation already marks a route action as sleep-eligible for candidate creation, dream mode should leave candidate creation to sleep maintenance instead of duplicating it.
- Keep dream mode separate from Architect mechanism maintenance. Dream explores evidence; Architect maintains the operating mechanisms and proposal queue after Sleep and Dream have settled.
- Offset the schedules. A simple default is to run Sleep at 12:00, Dream at 13:00, and Architect at 14:00. Each core maintenance lane should acquire the shared waiting lock before it starts; if another lane is active, wait and recheck every five minutes rather than skipping the run.
- If there is any doubt about overlap, skip dream mode and leave a history note rather than racing the two passes.

## Eligible Inputs

Dream mode should pull from grounded signals only:

- repeated retrieval misses on similar routes
- repeated weak-hit observations
- low-confidence candidates that need one narrow validation attempt
- existing candidate or low-confidence cards that can be checked against local evidence
- proposal-only actions from consolidation that still need evidence
- repeated taxonomy gaps from `kb_taxonomy.py --gaps-only`
- explicit user hypotheses about what the system might be able to do

Avoid starting from vague curiosity alone. A card or idea may become an input only when it points at a route, a gap, an existing candidate, or a repeated question. Dream should prefer clarifying existing material over adding new candidate backlog.

## Opportunity Score

Keep selection explainable. A simple scoring rule is enough:

```text
opportunity_score =
  4 * repeated_signal
+ 3 * boundedness
+ 3 * validation_readiness
+ 2 * reuse_potential
- 4 * execution_risk
```

Interpretation:

- `repeated_signal`: how often the same miss, weak hit, or route gap has appeared
- `boundedness`: how tightly the exploration can stay within one route or hypothesis
- `validation_readiness`: whether the result can be checked with current tests, search output, or explicit criteria
- `reuse_potential`: whether the outcome would likely matter again
- `execution_risk`: how likely the run is to create churn, broad edits, or hard-to-audit state

Select a bounded, route-deduped batch of valuable executable experiments that clears the run's value gate, and avoid medium-score experiments that would only add backlog, repeat known gaps, or duplicate Sleep-owned work. A no-op is valid when no opportunity clears that gate. A candidate without an `experiment_design`, `validation_plan`, `success_criteria`, `failure_criteria`, `safety_tier`, and `rollback_plan` is not selectable.

## Run Loop

1. Gather candidate inputs from history, proposals, gaps, and explicit user hypotheses.
2. Retrieve prior Dream-process experience so the run can reuse known boundaries and lessons.
3. Attach executable experiment contracts and safety tiers before selection.
4. Score inputs with a simple explicit rule and select a small batch of the strongest valuable executable experiments for the run.
5. Skip route-and-mode experiments that already passed with strong or moderate sandbox evidence in a prior Dream report, then write experiment, sandbox, and execution-plan records under `kb/history/dream/<run-id>/` before taking action, including execution order.
6. Run the selected experiments sequentially, using the smallest practical validation for each one.
7. Evaluate the result against explicit success, failure, or inconclusive criteria.
8. Append structured history with `kb_feedback.py` or `kb_maintenance.py`. When a strong or moderate passed sandbox result validates an existing candidate or low-confidence card, include the source entry id, sandbox path, evidence grade, validation status, and a Sleep handoff with `suggested_action: update-card`. For `scenario-replay`, include the tested-card rank, the no-tested-card baseline, whether the card improved task choice, and the specific Sleep next step.
9. Create a candidate scaffold with `kb_capture_candidate.py` only if the outcome looks reusable, history-only is insufficient, nearby candidate backlog does not already represent the route family, and the safety tier permits it.
10. Append one run-level Dream-process observation that summarizes preflight, selection, write-back, and process lessons.

Every experiment record should capture:

- route hint
- task summary
- hypothesis
- allowed action surface
- experiment design
- validation plan
- safety tier
- rollback plan
- success criteria
- failure criteria
- permitted write-back
- sandbox path
- allowed writes
- evidence grade
- validation result
- Sleep handoff
- structured Sleep handoff detail when the sandbox is judging a specific card
- Architect handoff
- source entry id and handoff action when an existing card was validated

Every execution plan should capture checkpoint status for preflight, opportunity scan, experiment selection, experiment record, validation, experiment observation, run observation, and report writing.

## Allowed Experiment Types

- route-first retrieval experiments using `kb_search.py`
- retrieval A/B sandbox experiments that write only under `kb/history/dream/<run-id>/sandbox/`
- scenario-replay sandbox experiments that replay historical or card-derived task scenarios with and without a tested candidate card, still writing only under `kb/history/dream/<run-id>/sandbox/`
- read-only validation of existing candidate or low-confidence cards
- taxonomy-gap inspection using `kb_taxonomy.py --gaps-only`
- proposal inspection using `kb_consolidate.py` and `kb_proposals.py`
- manual candidate scaffolding with `kb_capture_candidate.py`
- narrow dry-runs that do not mutate trusted memory
- lightweight eval checks that test whether a proposed route or candidate would be useful

## Disallowed or High-Risk Moves

- direct rewrites of `kb/public/` or `kb/private/`
- direct promotion of a dream-derived candidate into trusted scope
- repo-wide formatting or cleanup
- dependency installation or lockfile churn
- destructive commands
- broad refactors
- open-ended experimentation without a prewritten hypothesis and stop condition

If a run needs one of these actions, leave it as proposal-only.

Safety tiers:

- `read-only`: retrieval, inspection, comparison, dry-run, and history observation.
- `workspace-only`: candidate scaffolding or artifact writes inside the current repository.
- `external-system`: network, accounts, system configuration, dependency installs, real automation changes, or broad workspace mutation; keep this proposal-only unless a human explicitly approves it in an active task.

## Write-Back Rules

- Always write a history event, even when the dream run fails or is inconclusive.
- Use history-only write-back for noisy, one-off, or non-reusable results.
- Use candidate write-back only when the experiment produced a bounded predictive hypothesis with a clear scenario, action, and result.
- If adjacent search results are mostly existing candidates or low-confidence scaffolds, prefer read-only validation or a Sleep handoff instead of creating another adjacent candidate.
- Cap confidence conservatively for dream-derived candidates until later real-task evidence confirms them.
- Preserve failure and contrastive evidence; negative results are useful and should not be silently dropped.
- Keep route-specific experiment observations separate from the run-level Dream-process observation.
- Keep `external-system` outcomes proposal-only by default.

Dream output should be easy for later sleep maintenance to review, reject, narrow, or confirm.

## Current Tooling Path

The repository now includes a dedicated runner:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_dream.py --json
```

This runner already:

- checks core maintenance lane status before acting
- retrieves prior Dream-process guidance into `preflight.json`
- scores dream opportunities from current history, taxonomy gaps, and existing candidate or low-confidence cards
- writes `plan.json`, `preflight.json`, `opportunities.json`, `experiments.json`, `execution_plan.json`, and `report.json` under `kb/history/dream/<run-id>/`
- writes per-experiment sandbox artifacts under `kb/history/dream/<run-id>/sandbox/`
- validates the selected bounded batch of valuable executable experiments with local search, in the order listed in the execution plan
- keeps `retrieval-ab` for route and gap checks, and uses `scenario-replay` for existing candidate or low-confidence card validation so Sleep sees the baseline, tested-card rank, task-choice delta, and next review action
- writes history observations and candidate-only scaffolds when justified
- writes a run-level Dream-process observation after completed runs

The runner is still intentionally conservative and reuses the current file-based tools under the hood:

- `kb_search.py` for retrieval checks
- `kb_taxonomy.py` for gap inspection
- `kb_consolidate.py` and `kb_proposals.py` for proposal review
- `kb_feedback.py` for structured write-back
- `kb_maintenance.py` for explicit maintenance decisions
- `kb_capture_candidate.py` for candidate scaffolds

This keeps dream mode aligned with the existing repository philosophy: AI judgment, file-based tooling, explicit logs, and reversible state.

## Suggested Dream Prompt

Use this as the opening prompt for a future independent dream automation or maintenance chat:

```text
Run one bounded local KB dream-mode pass for this repository.

Goals:
1. Start from repeated misses, weak hits, low-confidence candidates, proposal-only actions, taxonomy gaps, or an explicit user hypothesis.
2. Retrieve prior Dream-process experience before selecting experiments.
3. Require an executable experiment design, validation plan, safety tier, rollback plan, and explicit success/failure criteria before selection.
4. Select a bounded route-deduped batch of valuable executable experiments; report a no-op when no useful experiment exists.
5. Write experiment and execution-plan records before acting.
6. Prefer retrieval checks, dry-runs, proposal inspection, and candidate scaffolding over broad edits.
7. Do not rewrite trusted cards or taxonomy directly.
8. Write every experiment result back to history, including failed or inconclusive outcomes.
9. Write one separate run-level Dream-process observation.
10. Create a candidate only if the result is reusable, remains bounded, is not already represented by nearby candidate backlog, and is not `external-system`.
11. Skip the run if sleep maintenance may overlap.

Report:
- run id used
- preflight entries retrieved
- hypotheses chosen, or why no valuable experiment was selected
- execution-plan checkpoint status
- safety tier and rollback plan
- experiments executed in sequence
- result classifications: success, failure, or inconclusive
- sandbox paths, allowed writes, evidence grades, validation results, and Sleep/Architect handoff
- for scenario-replay, the tested-card rank, baseline without the tested card, task-choice delta, and Sleep next step
- history events written
- candidates created, if any
- what still requires live-task confirmation
```

## Direct Command

Run one dream pass manually:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_dream.py --json
```
