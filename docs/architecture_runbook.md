# KB Architect Runbook

This runbook defines the `kb-architect` mechanism-maintenance lane. It runs after Sleep and Dream and controls how the KB system improves its own operating machinery without taking over card-content maintenance.

The default local cadence is Sleep at 12:00, Dream at 13:00, and Architect at 14:00. Each core maintenance lane checks that the other two lanes are not running before it starts, so the schedule does not need a post-completion cooldown.

`PROJECT_SPEC.md` remains authoritative. If this runbook and the spec disagree, follow the spec and simplify this runbook.

The repository installer is expected to provision a repo-managed `KB Architect` cron automation under `$CODEX_HOME/automations/`. Re-running `python scripts/install_codex_kb.py --json` on another machine should refresh that schedule automatically. The automation spec should keep model selection policy-based: strongest available model plus deepest supported reasoning, resolved during install rather than pinned to a specific model version.

## Purpose

- `sleep` consolidates real task evidence and maintains memory/card surfaces.
- `dream` runs bounded exploratory checks and writes provisional evidence.
- `architect` maintains the mechanisms that make Sleep, Dream, retrieval, installation, validation, rollback, and proposal governance work reliably.

Architect is not a card-content maintainer. It does not rewrite trusted cards, promote candidates, split cards, merge cards, deprecate cards, or tune user-specific knowledge.

## Mandatory Order

Each Architect pass must follow this order and keep the execution plan status current until the end:

1. Confirm repository root and rule files.
2. Run self-preflight against `system/knowledge-library/maintenance`.
3. Run the Architect runner.
4. Inspect generated artifacts.
5. Inspect the maintained proposal queue.
6. Review proposals using exactly `Evidence`, `Impact`, and `Safety`.
7. Assign or confirm statuses.
8. Apply only `ready-for-apply` items that stay inside the narrow allowlist.
9. Generate or refine patch plans for `ready-for-patch` items.
10. Preserve `watching` items for long observation.
11. Run a validation bundle for any file changes.
12. Confirm or append the final KB postflight observation.
13. Report run id, checkpoint statuses, proposal status counts, applied changes, validations, and remaining watching items.

If a checkpoint is not applicable, mark it skipped with a reason. Do not silently omit it.

## Decision Axes

Use only three axes. Do not add a large weighted scoring model.

- `Evidence`: how strong and repeated the signal is.
- `Impact`: how much the issue affects the KB system's maintenance mechanisms.
- `Safety`: how narrow, testable, and reversible the proposed change is.

Levels are `low`, `medium`, or `high`.

## Statuses

Allowed proposal statuses:

- `new`
- `watching`
- `ready-for-patch`
- `ready-for-apply`
- `applied`
- `rejected`
- `superseded`

There is no human-review status. High-risk or uncertain items remain under long observation as `watching` until evidence and safety improve.

## Status Rules

- `Evidence=high`, `Impact=high|medium`, `Safety=high` -> `ready-for-apply`
- `Evidence=high`, `Safety=medium` -> `ready-for-patch`
- `Evidence=medium`, `Impact=high` -> `watching`
- `Evidence=low`, `Impact=low` -> usually `rejected`
- `Safety=low` -> `watching`, even when Evidence is high

These are decision rules, not hidden math.

## In Scope

- Sleep prompt and runbook quality
- Dream prompt and runbook quality
- Architect prompt and runbook quality
- automation specs and cadence
- installer and install-check coverage
- validation bundles and test coverage for maintenance mechanisms
- rollback and snapshot workflow
- proposal queue lifecycle and duplicate clustering
- process hazards in preflight and postflight behavior

## Out Of Scope

- trusted-card rewrites
- candidate promotion
- card merge/split/deprecation
- card confidence changes
- user preference card maintenance
- taxonomy route rename/move
- dependency installation
- lockfile churn
- repo-wide formatting
- broad refactors

Out-of-scope signals should not be deleted. Architect can record that they belong to Sleep or long observation, but it must not act on them directly.

## Current Tooling Path

Run one Architect pass manually:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_architect.py `
  --sleep-cooldown-minutes 0 `
  --dream-cooldown-minutes 0 `
  --json
```

The runner writes:

- `kb/history/architecture/runs/<run-id>/plan.json`
- `kb/history/architecture/runs/<run-id>/preflight.json`
- `kb/history/architecture/runs/<run-id>/signals.json`
- `kb/history/architecture/runs/<run-id>/proposals.json`
- `kb/history/architecture/runs/<run-id>/decisions.json`
- `kb/history/architecture/runs/<run-id>/execution_plan.json`
- `kb/history/architecture/runs/<run-id>/report.json`
- `kb/history/architecture/proposal_queue.json`

The runner also appends one structured Architect observation to `kb/history/events.jsonl`.

## Suggested Architect Prompt

Use this as the opening prompt for an independent Architect automation:

```text
Run one KB Architect mechanism-maintenance pass for this repository.

Goals:
1. Maintain a visible execution plan with every required checkpoint.
2. Run self-preflight against system/knowledge-library/maintenance.
3. Run kb_architect.py and inspect all generated artifacts.
4. Maintain the mechanism proposal queue.
5. Use only Evidence, Impact, and Safety.
6. Do not use a human-review status; long-observation items stay watching.
7. Keep scope limited to system mechanisms, not card content.
8. Apply only high-evidence, high-impact or medium-impact, high-safety mechanism changes inside the narrow allowlist.
9. Generate patch plans for medium-safety changes.
10. Run a validation bundle after any file changes.
11. Confirm or append the final KB postflight observation.

Report:
- run id
- plan status for every checkpoint
- preflight entries retrieved
- proposal status counts
- ready-for-apply and ready-for-patch proposals
- changes applied
- validations run
- postflight observation status
- watching items left for long observation
```

## Validation Bundle

Architect changes are not complete after a single token check. Each applied or patched change needs enough validation for the touched mechanism:

- prompt or runbook changes: inspect required markers and run matching prompt/install tests when available
- runner or core-tooling changes: run targeted unit tests plus one smoke run when practical
- installer or automation changes: run installer tests plus `python scripts/install_codex_kb.py --check --json`
- failed validations must be fixed and rerun before a proposal can move to `applied`
