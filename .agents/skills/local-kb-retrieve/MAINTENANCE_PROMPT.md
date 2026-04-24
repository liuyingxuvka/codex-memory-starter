# Local KB Sleep Maintenance Prompt

Use this prompt in a separate Codex chat or scheduled automation that is dedicated to maintaining the local predictive knowledge library.

Rule authority:

- `PROJECT_SPEC.md` is the canonical source for thresholds, governance rules, and maintenance boundaries.
- `docs/maintenance_runbook.md` is the canonical operational reference for what the current tooling safely supports.
- This prompt should stay operational. If this prompt and the spec disagree, the spec wins.

Goal:

- keep the library easy to navigate
- recall prior sleep-maintenance lessons before changing the library
- consolidate observations into candidate knowledge
- surface undeclared taxonomy branches
- record what this maintenance pass learned before it ends
- leave an auditable trail of what changed

Current implementation boundary:

- you may inspect taxonomy, navigation, history, and consolidation artifacts
- you may let `kb_consolidate.py` auto-create low-risk candidate scaffolds with `--apply-mode new-candidates`
- you may let `kb_consolidate.py` update stable direct `related_cards` with `--apply-mode related-cards`
- you may let `kb_consolidate.py` update low-risk direct `cross_index` routes with `--apply-mode cross-index`
- you may let `kb_consolidate.py` apply AI-authored Chinese display translations with `--apply-mode i18n-zh-CN --i18n-plan <path>`
- you may let `kb_consolidate.py` apply AI-authored semantic card decisions with `--apply-mode semantic-review --semantic-review-plan <path>`; one run may modify at most 3 trusted cards
- you must run a sleep self-preflight search before taxonomy, consolidation, or apply work
- you must run a final sleep postflight check and append one structured observation when the pass exposed a reusable lesson, miss, process weakness, route gap, card weakness, or maintenance hazard
- you may record explicit maintenance decisions with `kb_maintenance.py` so ignored observations, rejected candidates, and confidence reviews leave durable history traces
- you may inspect or restore `kb/history/events.jsonl` through `kb_rollback.py`
- do not silently rewrite trusted cards or official taxonomy during this maintenance pass; trusted-card semantic changes require an explicit semantic-review plan, evidence ids, rationale, risk, expected retrieval effect, and rollback note
- if a trusted-scope promotion, rewrite, demotion, or deprecation is not clearly represented in a semantic-review plan and supported by the current tooling, leave it as proposal-only
- after writing the final maintenance observation, stop the current sleep pass; do not immediately rerun consolidation on the observation that was just appended

Execution contract:

- Before the first stateful maintenance command, write a visible sleep execution plan in the run transcript. The plan must break the pass into concrete checkpoints such as self-preflight, taxonomy inspection, proposal run, eligible apply lanes, i18n cleanup, route-label review, validation, final postflight, and summary.
- Keep that plan current while working. Mark each checkpoint as pending, in progress, completed, skipped with reason, or blocked with a concrete blocker.
- Do not stop after a short proposal or one successful command when a natural next checkpoint remains. Continue until every required checkpoint is completed, explicitly skipped, or blocked.
- When a command exposes a problem that is inside the current low-risk maintenance boundary, try the supported repair path and rerun the relevant validation. Do not merely report the problem and stop.
- When a problem is outside the current apply boundary, leave it as proposal-only, record a maintenance decision or final observation when useful, and continue with the remaining safe checkpoints.
- Treat the run as incomplete unless the final summary includes the plan status, validations run, issues repaired, issues left proposal-only, and the final postflight observation status.

Checklist:

1. Run a sleep self-preflight search so the maintenance pass recalls prior maintenance lessons before changing memory:
`python .agents/skills/local-kb-retrieve/scripts/kb_search.py --path-hint system/knowledge-library/maintenance --query "sleep maintenance consolidation i18n route labels split review postflight" --top-k 5 --json`
   Treat the results as bounded context. Current instructions and repository files still win over any retrieved card.
2. Inspect the explicit taxonomy tree:
`python .agents/skills/local-kb-retrieve/scripts/kb_taxonomy.py --json`
3. Inspect the smallest undeclared taxonomy routes implied by current entries:
`python .agents/skills/local-kb-retrieve/scripts/kb_taxonomy.py --gaps-only --json`
4. If route structure looks unclear, inspect the current route tree view:
`python .agents/skills/local-kb-retrieve/scripts/kb_nav.py --json`
5. Inspect recent history in proposal mode:
`python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py --json --apply-mode none`
6. While reviewing observations, distinguish between:
   - generic retrospectives or advice summaries
   - predictive-model evidence with a clear scenario, action, observed result, and operational use
   Only the second category should be promoted directly toward cards. Generic summaries should be rewritten, split, or left as weak evidence.
7. Preserve and inspect provenance for each observation when available: timestamp, agent name, thread reference, project reference, and workspace root. This metadata matters when deciding whether a lesson is one-off, project-local, or worth re-review by a similar agent flow later.
   Do not read those observations as isolated bullets only. When the same project, workspace, or thread appears repeatedly, inspect the chronology and use it to reconstruct the episode: what was tried earlier, what changed later, and which revision actually improved the result.
   Route-quality rule: when creating or reviewing candidate cards, prefer a `domain_path` that describes the reusable function or direction of the lesson. Project, repository, or product names should normally stay in provenance, tags, trigger keywords, or explanatory text, not as the main route. During sleep review, if an existing candidate's route is too project-specific, adjust it when safely editing the candidate or leave a concrete path-adjustment note before promotion.
8. If the grouped actions are coherent, run the lowest-risk apply mode:
`python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py --json --apply-mode new-candidates`
   Only do this when the eligible routes are semantically specific enough; in the current implementation, broad routes and routes with fewer than 3 segments should stay proposal-only. A single observation may create only a low-confidence seed candidate, and only when it already has complete predictive evidence: scenario, action taken, and observed result.
For entry-link maintenance, `python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py --json --apply-mode related-cards` may update direct `related_cards` fields when repeated co-use evidence is already stable.
For alternate-route maintenance, `python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py --json --apply-mode cross-index` may update direct `cross_index` fields when repeated route evidence is already stable enough to justify a low-risk change.
9. For card semantic maintenance, inspect `review-candidate`, `review-confidence`, and `review-entry-update` stubs. If AI judgment supports a concrete decision, author `kb/history/consolidation/<run_id>-semantic/semantic_review_plan.yaml` and run:
`python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py --json --run-id <run_id>-semantic --apply-mode semantic-review --semantic-review-plan kb/history/consolidation/<run_id>-semantic/semantic_review_plan.yaml`
   The plan must use decisions `keep`, `rewrite`, `adjust-confidence`, `promote`, `demote`, or `deprecate` for automatic apply. `split` and `merge` may be recorded as proposal-only until they are represented as concrete safe rewrites. Each applied decision must set `apply: true`, cite current action `evidence_event_ids`, include `rationale`, `risk`, `expected_retrieval_effect`, and `rollback_note`, and respect the trusted-card budget of 3.
10. After candidate creation or any card text change, inspect missing Chinese display translations with:
`python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py --json --apply-mode i18n-zh-CN --run-id <run_id>-i18n-check`
   If the i18n apply report skips entries because no translation payload was provided, author `kb/history/consolidation/<run_id>-i18n/i18n_zh-CN_plan.yaml` and rerun:
`python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py --json --apply-mode i18n-zh-CN --run-id <run_id>-i18n --i18n-plan kb/history/consolidation/<run_id>-i18n/i18n_zh-CN_plan.yaml`
11. Inspect the per-action proposal stubs for this run:
`python .agents/skills/local-kb-retrieve/scripts/kb_proposals.py --run-id <run_id> --json`
12. If a weak observation should stay history-only, a candidate should be rejected, a confidence review should be recorded, or a split review should be closed without rewriting the card yet, append a maintenance decision trace:
`python .agents/skills/local-kb-retrieve/scripts/kb_maintenance.py --decision-type observation-ignored|candidate-rejected|confidence-reviewed|split-reviewed --action-key <action_key> --resolved-event-ids <csv_event_ids> --reason "<why>" --json`
   For `split-reviewed`, always bind the decision to the concrete supporting event ids from the current review. Do not close split review with empty `resolved-event-ids`.
13. If the same trusted card keeps recurring in observations or proposal stubs, run a split review:
   - keep a **hub card** when it still expresses one bounded predictive relation and mainly serves as an entry point
   - mark an **overloaded card** for split proposal when it now mixes multiple scenarios, actions, results, or route-specific case branches, even if those branches are still arriving through the same route
   - repeated hits alone are a review signal, not an automatic split rule
14. When drafting or updating cards, rewrite the evidence into predictive form: `if / action -> predicted result -> operational use`. Reject “should / avoid / best practice” wording unless the causal prediction is explicit.
15. Model/runtime behavior cards are valid when they stay bounded and auditable. Scope them to the most precise runtime identity that is actually known. If exact model identity is not surfaced reliably, scope them more conservatively to the active Codex runtime, current environment, or known model family.
16. When maintaining those cards, prefer more than one retrieval path when justified: a runtime-facing route such as `codex/runtime-behavior/...` or `ai/runtime/...`, plus any prompting, tool-use, workflow, or planning routes that materially exposed the behavior.
17. User-specific cards are also valid when they stay bounded, evidence-based, and behaviorally framed. Keep them private by default, prefer task-conditioned preference or reaction models over personality summaries, and reject broad character-label wording even when the interaction signal feels strong.
18. For `review-related-cards` actions, only keep direct related-card links that are supported by repeated co-use of actually used `entry_ids`. Keep the card surface simple: no recursive graph expansion and no more than 3 related cards per entry.
19. For `review-cross-index` actions, only keep direct alternate retrieval paths that are supported by repeated actual route usage. Low-risk auto-apply should strengthen stable `cross_index` paths; pruning should stay proposal-first until stronger removal evidence exists. Do not use this to perform broad taxonomy rewrites.
20. Read the resulting `snapshot.json`, `proposal.json`, action stub paths, and `apply.json` paths from the consolidation output.
21. If the maintenance pass needs recovery, inspect and optionally restore history events:
`python .agents/skills/local-kb-retrieve/scripts/kb_rollback.py inspect --run-id <run_id> --write-manifest --json`
`python .agents/skills/local-kb-retrieve/scripts/kb_rollback.py restore --run-id <run_id> --artifact history-events --json`
`python .agents/skills/local-kb-retrieve/scripts/kb_rollback.py restore --run-id <run_id> --artifact semantic-review-entries --json`
22. Run the final sleep postflight check: did this maintenance pass expose a reusable lesson, a miss, a route gap, a card weakness, a process weakness, an unsafe apply pattern, or a useful split/translation/taxonomy observation?
   If yes, append one structured observation with `kb_feedback.py` before finalizing. Use route hint `system/knowledge-library/maintenance`, include the maintenance run id in `task-summary` or `project-ref`, and write scenario/action/observed-result fields in predictive form.
   If no, state explicitly that no new maintenance observation was worth recording.
23. After the final sleep postflight observation is written, stop. Do not rerun `kb_consolidate.py` in the same pass just to process the observation that was just appended.
24. Summarize the pass:
   - run id
   - sleep execution plan status for every checkpoint
   - self-preflight entries considered
   - observations processed
   - candidates created
   - related-card updates applied
   - cross-index updates applied
   - semantic-review decisions applied, reviewed, or skipped
   - actions skipped
   - validations run and whether failed checks were repaired or left proposal-only
   - maintenance decisions recorded
   - final sleep postflight observation recorded, or why none was recorded
   - proposal stub counts by action type
   - missing or updated zh-CN display translations
   - undeclared taxonomy branches
   - cards reviewed for keep-as-hub vs split-review
   - card updates or taxonomy changes still needed later

Default cadence:

- active buildout: once per day
- quieter maintenance: two or three times per week
