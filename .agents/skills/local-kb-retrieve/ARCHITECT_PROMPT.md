# KB Architect Prompt

Run one KB Architect mechanism-maintenance pass for this repository.

Rule authority:

1. Current user instructions
2. `AGENTS.md`
3. `PROJECT_SPEC.md`
4. `docs/architecture_runbook.md`
5. This prompt

Scope:

- Maintain the KB system's operating mechanisms only.
- In scope: Sleep/Dream/Architect prompts, runbooks, automation specs, install checks, rollback/snapshot/validation workflow, proposal queue governance, and narrowly scoped tests for those mechanisms.
- Out of scope: trusted-card rewrites, candidate promotion, card content merging/splitting/deprecation, user preference cards, and ordinary knowledge-card maintenance. Leave those to Sleep.

Mandatory execution contract:

1. Before the first stateful command, create a visible plan with every checkpoint below.
2. Put every checkpoint into the plan and keep its status current: pending, in progress, completed, skipped with reason, or blocked with a concrete blocker.
3. Do not skip a checkpoint silently. If it is not applicable, mark it skipped with the reason.
4. Continue until all checkpoints are completed, skipped with reason, or blocked. Do not stop after only writing a proposal.
5. Use only the three-axis decision model: `Evidence`, `Impact`, and `Safety`. Do not invent extra weighted scoring dimensions.
6. Do not use a human-review status. Long-observation items remain `watching`.
7. Finish with a KB postflight observation. If the runner already wrote one, inspect and report it; if the pass exposed an additional reusable mechanism lesson, append one more structured observation.

Required checkpoint order:

1. Confirm repository root and read `PROJECT_SPEC.md`, `docs/architecture_runbook.md`, and this prompt.
2. Run Architect self-preflight against `system/knowledge-library/maintenance`.
3. Run:
   `python .agents/skills/local-kb-retrieve/scripts/kb_architect.py --json --sleep-cooldown-minutes 0 --dream-cooldown-minutes 0`
4. Inspect the generated artifacts under `kb/history/architecture/runs/<run-id>/`.
5. Inspect the maintained queue at `kb/history/architecture/proposal_queue.json`.
6. Confirm each mechanism proposal has exactly these review axes:
   - `Evidence`
   - `Impact`
   - `Safety`
7. Confirm statuses are limited to:
   - `new`
   - `watching`
   - `ready-for-patch`
   - `ready-for-apply`
   - `applied`
   - `rejected`
   - `superseded`
8. For `ready-for-apply` proposals, apply only if all are true:
   - the change is mechanism-scoped
   - the change is not card-content maintenance
   - the change stays inside prompt, runbook, validation, or proposal-queue maintenance
   - the diff is narrow and reversible
   - the validation bundle is obvious and can be run immediately
9. For `ready-for-patch` proposals, generate or refine a patch and validation plan, but do not treat the proposal as applied until the patch is actually implemented and verified.
10. For `watching` proposals, preserve the observation path and do not force action.
11. For `rejected` or `superseded` proposals, make sure the reason is recorded.
12. Run a validation bundle for any file changes made in this pass. The bundle must be strong enough for the touched mechanism:
    - prompt/runbook-only changes: inspect required markers and run the matching prompt/install tests when available
    - runner or core-tooling changes: run targeted unit tests plus one smoke run when practical
    - installer or automation changes: run installer tests plus `python scripts/install_codex_kb.py --check --json`
    - any failed validation must be fixed and rerun before the proposal can be marked applied
13. Inspect the runner's postflight observation id and write an additional structured KB observation only if this pass exposed a new reusable mechanism lesson.
14. Report:
    - run id
    - plan status for every checkpoint
    - preflight entries retrieved
    - proposal counts by status
    - ready-for-apply and ready-for-patch items
    - changes applied, if any
    - validations run
    - postflight observation status
    - items left watching

Decision model:

- `Evidence`
  - `high`: repeated signal, usually 3 or more supporting observations/actions or recurring across Architect runs
  - `medium`: at least 2 related signals or one strong recent mechanism failure
  - `low`: one weak or isolated signal
- `Impact`
  - `high`: affects installation, automation cadence, preflight/postflight reliability, rollback, validation, or safety
  - `medium`: affects prompt/runbook clarity, proposal queue hygiene, or maintenance ergonomics
  - `low`: cosmetic, speculative, or narrow
- `Safety`
  - `high`: prompt/runbook/validation/proposal-queue change with narrow diff and immediate validation
  - `medium`: automation, install-check, or core tooling patch that is testable but should start as patch
  - `low`: taxonomy movement, dependency/lockfile change, deletion, broad refactor, or anything hard to roll back

Status rule:

- `Evidence=high`, `Impact=high|medium`, `Safety=high` -> `ready-for-apply`
- `Evidence=high`, `Safety=medium` -> `ready-for-patch`
- `Evidence=medium`, `Impact=high` -> `watching`
- `Evidence=low`, `Impact=low` -> usually `rejected`
- `Safety=low` -> `watching`, even when Evidence is high

Hard boundaries:

- Do not rewrite trusted cards.
- Do not promote candidates.
- Do not merge, split, deprecate, or delete card content.
- Do not rename taxonomy routes.
- Do not install dependencies.
- Do not run repo-wide formatting.
- Do not make broad refactors.
- Do not run Sleep or Dream from inside Architect.
