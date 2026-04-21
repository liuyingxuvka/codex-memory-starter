# Dream Exploration Runbook

This runbook defines a separate `kb-dreamer` maintenance pass for bounded exploration. It is intentionally narrower than “autonomous self-improvement.” The goal is to test adjacent possibilities without contaminating trusted memory or colliding with sleep maintenance.

`PROJECT_SPEC.md` remains authoritative. If this runbook and the spec disagree, follow the spec and simplify the runbook.

The repository installer is expected to provision a repo-managed `KB Dream` cron automation under `$CODEX_HOME/automations/`. Re-running `python scripts/install_codex_kb.py --json` on another machine should refresh that schedule automatically.

## Purpose

- `sleep` consolidates real task evidence, maintenance decisions, and current-card state.
- `dream` explores nearby but not-yet-settled hypotheses through small, auditable experiments.

Dream mode is valid only when it remains:

- grounded in existing cards, misses, or route gaps
- bounded in action surface
- explicit about provenance
- candidate-only or history-only in write-back

It is not a license for free-form tool wandering or hidden self-belief growth.

## Separation From Sleep

- Run dream mode in a different automation, thread, or maintenance session from sleep mode.
- Do not run dream mode while a sleep pass is active or while sleep artifacts for the same repository state are still unresolved.
- Offset the schedules. A simple default is to keep at least one clear non-overlapping window between them.
- If there is any doubt about overlap, skip dream mode and leave a history note rather than racing the two passes.

## Eligible Inputs

Dream mode should pull from grounded signals only:

- repeated retrieval misses on similar routes
- repeated weak-hit observations
- low-confidence candidates that need one narrow validation attempt
- proposal-only actions from consolidation that still need evidence
- repeated taxonomy gaps from `kb_taxonomy.py --gaps-only`
- explicit user hypotheses about what the system might be able to do

Avoid starting from vague curiosity alone. The input should already point at a route, a gap, a candidate, or a repeated question.

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

Prefer one high-score experiment over many medium-score experiments.

## Run Loop

1. Gather candidate inputs from history, proposals, gaps, and explicit user hypotheses.
2. Score them with a simple explicit rule and select at most one or two experiments for the run.
3. Write an experiment record under `kb/history/dream/<run-id>/` before taking action.
4. Run the smallest practical experiment.
5. Evaluate the result against explicit success, failure, or inconclusive criteria.
6. Append structured history with `kb_feedback.py` or `kb_maintenance.py`.
7. Create a candidate scaffold with `kb_capture_candidate.py` only if the outcome looks reusable.

Every experiment record should capture:

- route hint
- task summary
- hypothesis
- allowed action surface
- success criteria
- failure criteria
- permitted write-back

## Allowed Experiment Types

- route-first retrieval experiments using `kb_search.py`
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

## Write-Back Rules

- Always write a history event, even when the dream run fails or is inconclusive.
- Use history-only write-back for noisy, one-off, or non-reusable results.
- Use candidate write-back only when the experiment produced a bounded predictive hypothesis with a clear scenario, action, and result.
- Cap confidence conservatively for dream-derived candidates until later real-task evidence confirms them.
- Preserve failure and contrastive evidence; negative results are useful and should not be silently dropped.

Dream output should be easy for later sleep maintenance to review, reject, narrow, or confirm.

## Current Tooling Path

The repository now includes a dedicated runner:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_dream.py --json
```

This runner already:

- inspects recent sleep timing before acting
- scores dream opportunities from current history and taxonomy gaps
- writes `plan.json`, `opportunities.json`, `experiments.json`, and `report.json` under `kb/history/dream/<run-id>/`
- validates one or more bounded experiments with local search
- writes history observations and candidate-only scaffolds when justified

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
2. Select at most one or two high-value experiments with explicit boundedness and validation criteria.
3. Write an experiment record before acting.
4. Prefer retrieval checks, dry-runs, proposal inspection, and candidate scaffolding over broad edits.
5. Do not rewrite trusted cards or taxonomy directly.
6. Write every result back to history, including failed or inconclusive outcomes.
7. Create a candidate only if the result is reusable and remains bounded.
8. Skip the run if sleep maintenance may overlap.

Report:
- run id used
- hypothesis chosen
- experiment executed
- result classification: success, failure, or inconclusive
- history events written
- candidates created, if any
- what still requires live-task confirmation
```

## Direct Command

Run one dream pass manually:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_dream.py `
  --max-experiments 1 `
  --sleep-cooldown-minutes 45 `
  --json
```
