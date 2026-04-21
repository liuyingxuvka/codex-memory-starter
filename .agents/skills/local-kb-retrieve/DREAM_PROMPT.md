# Local KB Dream Prompt

Use this prompt in a separate Codex chat or scheduled automation that is dedicated to bounded dream-mode exploration for the local predictive knowledge library.

Rule authority:

- `PROJECT_SPEC.md` is the canonical source for boundaries and governance.
- `docs/dream_runbook.md` is the operational reference for dream mode.
- `docs/maintenance_runbook.md` still governs sleep maintenance and remains separate.

Goal:

- inspect one or two high-value exploration opportunities
- prefer adjacent route validation over broad autonomy
- write only to history or `kb/candidates/`
- leave trusted memory untouched

Default path:

1. Run the dedicated dream runner:
`python .agents/skills/local-kb-retrieve/scripts/kb_dream.py --json --max-experiments 1 --sleep-cooldown-minutes 45`
2. Inspect the generated artifacts under `kb/history/dream/<run-id>/`.
3. Report:
   - run id
   - selected experiment
   - created candidates, if any
   - history events written
   - anything left for live-task confirmation

Guardrails:

- skip the run if recent sleep maintenance may still overlap
- do not rewrite trusted cards or taxonomy directly
- do not install dependencies or perform broad code changes
- treat dream-created candidates as provisional until later live-task evidence confirms them
