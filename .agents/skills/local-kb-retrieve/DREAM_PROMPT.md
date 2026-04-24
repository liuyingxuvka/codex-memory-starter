# Local KB Dream Prompt

Use this prompt in a separate Codex chat or scheduled automation that is dedicated to bounded dream-mode exploration for the local predictive knowledge library.

Rule authority:

- `PROJECT_SPEC.md` is the canonical source for boundaries and governance.
- `docs/dream_runbook.md` is the operational reference for dream mode.
- `docs/maintenance_runbook.md` still governs sleep maintenance and remains separate.

Goal:

- inspect exactly one high-value executable exploration opportunity
- allow any grounded card or idea into the candidate pool if it has an executable validation plan
- write only to history or `kb/candidates/`
- leave trusted memory untouched

Default path:

1. Run the dedicated dream runner:
`python .agents/skills/local-kb-retrieve/scripts/kb_dream.py --json --sleep-cooldown-minutes 45`
2. Inspect the generated artifacts under `kb/history/dream/<run-id>/`.
3. Report:
   - run id
   - preflight entries retrieved
   - selected experiment
   - execution-plan checkpoint status
   - safety tier and rollback plan
   - created candidates, if any
   - history events written
   - run-level Dream-process observation
   - anything left for live-task confirmation

Guardrails:

- skip the run if recent sleep maintenance may still overlap
- retrieve prior Dream-process experience before selecting experiments
- select exactly one executable experiment
- require `experiment_design`, `validation_plan`, `success_criteria`, `failure_criteria`, `safety_tier`, and `rollback_plan` before execution
- if consolidation already marks a route candidate as sleep-eligible, leave candidate creation to sleep rather than duplicating it in dream mode
- do not rewrite trusted cards or taxonomy directly
- do not install dependencies or perform broad code changes
- keep external-system experiments proposal-only unless a human explicitly approves them in an active task
- keep route-specific experiment observations separate from the run-level Dream-process observation
- treat dream-created candidates as provisional until later live-task evidence confirms them
