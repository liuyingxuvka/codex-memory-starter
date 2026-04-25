---
name: kb-dream-pass
description: Run one bounded repository-managed local KB Dream exploration pass. Use only when a user or automation explicitly asks for KB Dream, dream mode, bounded KB exploration, or the scheduled KB Dream automation; do not use for Sleep consolidation, Architect mechanism work, ordinary preflight, or trusted-card maintenance.
---

# KB Dream Pass

Run one bounded Dream pass for this predictive KB repository.

## Authority

Work from the repository root. Treat these files as authoritative and read them before stateful dream work:

- `PROJECT_SPEC.md`
- `docs/dream_runbook.md`
- `.agents/skills/local-kb-retrieve/DREAM_PROMPT.md`

Current user instructions still override repository files.

## Execution Contract

1. Keep Dream separate from Sleep and Architect.
2. Run the dedicated dream runner:
   `python .agents/skills/local-kb-retrieve/scripts/kb_dream.py --json --sleep-cooldown-minutes 0`
3. Inspect generated artifacts under `kb/history/dream/<run-id>/`, including preflight, plan, opportunity, experiment, execution-plan, and report files.
4. Require exactly one executable experiment before execution.
5. Require experiment design, validation plan, safety tier, rollback plan, and explicit success/failure criteria.
6. Keep write-back history-only or candidate-only.
7. Keep external-system experiments proposal-only unless a human explicitly approves them in an active task.
8. Do not rewrite trusted cards or taxonomy.
9. Treat dream-created candidates as provisional until later live-task evidence confirms them.

## Report

Report the run id, retrieved preflight entries, selected experiment, execution-plan checkpoint status, safety tier and rollback plan, created candidates if any, history events written, run-level Dream-process observation, and anything still needing live-task confirmation.
