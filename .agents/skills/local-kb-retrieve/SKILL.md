---
name: local-kb-retrieve
description: Retrieve relevant entries from the local predictive knowledge base as a lightweight preflight for repository work. Use route-first retrieval: infer the task direction, then search by domain path and cross-index before relying on flat keyword matching. In Codex, prefer a scout sidecar before non-trivial work and a recorder sidecar after work when sub-agents are available. Treat "no relevant entry" as useful signal, not a reason to skip the scan up front.
---

When this skill is used, follow this workflow:

Rule authority:

- Treat `PROJECT_SPEC.md` as the canonical source for thresholds, maintenance boundaries, and governance rules.
- Treat `docs/maintenance_runbook.md` as the canonical operational runbook for sleep maintenance.
- Keep this skill focused on the workflow shape. If this skill and the spec disagree, follow the spec.

Default stance: run a quick scan first for repository tasks; keep the scan lightweight unless the returned entries are clearly relevant.
This includes GitHub publish work, release audits, README presentation passes, public template cleanup, and repo-boundary/privacy review. Those still count as repository tasks and should not bypass the scan.
Keep the active path mathematically simple and easy to audit. During normal task flow, retrieval should use explicit additive rules and should not try to normalize or repair the KB inline.

Preferred Codex operating pattern:

- For non-trivial work, start a read-oriented `kb-scout` sidecar sub-agent before the main task so the primary agent can stay focused on the critical path.
- After the main task, treat KB postflight as part of done. Start a `kb-recorder` sidecar sub-agent whenever the task exposed feedback worth keeping, comments, misses, route gaps, card weaknesses, or candidate lessons.
- Run deeper consolidation in a separate scheduled maintenance conversation or automation rather than inside the main task thread.
- If sub-agents are unavailable, or if the task is trivial, fall back to a lightweight inline scan and inline feedback note.

Rule discipline:

- Keep retrieval scoring as a simple additive rule: structural route evidence + lexical evidence + small confidence/status adjustment.
- Do not let `confidence` or `status` create a hit by themselves. They may rerank plausible matches, but they should not turn unrelated entries into matches.
- Keep runtime survival separate from KB repair. During active work, skip malformed or unusable entries and continue; leave cleanup and normalization to sleep maintenance.
- Keep parameters few and fixed. Prefer counts, weights, and thresholds that a human can inspect over adaptive or opaque heuristics.

Sleep maintenance lanes:

- `deterministic repair`: schema normalization, field-type cleanup, canonical path alignment, low-ambiguity formatting, and other fixes that can be expressed as fixed rules and validated mechanically.
- `semantic repair`: candidate creation, card rewrites, merges, promotions, deprecations, taxonomy changes, and other changes that depend on accumulated evidence rather than a single malformed field.
- Keep semantic auto-apply thresholds simple. Do not restate every threshold here; use the canonical thresholds from `PROJECT_SPEC.md` and `docs/maintenance_runbook.md`.
- If a change does not satisfy a deterministic rule or a simple semantic threshold, leave it as a proposal for a later maintenance pass.

Independent maintenance thread:

- Use a separate maintenance chat or automation for the library's "sleep" workflow. Do not let deep consolidation interrupt the user's main task thread.
- In the current implementation, maintenance may safely write history events, consolidation artifacts, rollback manifests, candidate scaffolds, and explicit decision traces for ignored observations, rejected candidates, and confidence reviews.
- Do not treat the current tooling as permission to rewrite trusted cards or restructure taxonomy silently inside a main task. Those deeper updates should remain AI-authored follow-up work until the maintenance layer grows beyond candidate-level application.
- A practical active-build cadence is once per day. For calmer periods, two or three times per week is usually enough.

1. Summarize the task in one short sentence.
2. Infer one primary conceptual route such as `work/reporting/ppt` or `engineering/debugging/version-change`.
3. Infer up to three alternative routes when the task may be reachable through more than one conceptual direction.
4. If sub-agents are available and the task is non-trivial, let `kb-scout` handle the initial scan. Otherwise run:
   `python .agents/skills/local-kb-retrieve/scripts/kb_search.py --route-hint "<primary route>" --query "<task summary plus useful keywords>" --top-k 5`
5. Read the returned entries.
6. Prefer entries with stronger route alignment, `status: trusted`, and higher `confidence`.
7. Use retrieved entries as bounded context. Do not overgeneralize beyond the entry scope.
8. If no relevant entries are found, continue without forcing the library into the answer; the absence of hits is still a useful signal.
9. Before finalizing any non-trivial task, run one explicit KB postflight check: did this task expose a reusable lesson, a miss, a route gap, a card weakness, or a KB-process failure?
10. If the answer is yes, let `kb-recorder` append structured feedback so the scheduled AI consolidation flow can process it later. When more than one card materially influenced the task, record all of those entry ids rather than only the top hit.
11. If the answer is no, make that an explicit conclusion rather than silently forgetting to check.
12. If a reusable new lesson emerges during the task, record it into candidates or structured history rather than trying to fully consolidate it inside the active task thread.
13. When a reusable lesson is being recorded, do not stop at a generic summary. Preserve predictive-model evidence: the scenario, the action or condition, the observed result, and how future Codex behavior should use that result.
14. When the task involved a weaker path, mistake, or later correction, preserve both sides of the contrast whenever possible: what the earlier action was, what weaker result it led to, what changed, and what improved afterward. These contrastive observations are often the easiest ones to turn into future card alternatives.
15. Preserve `thread_ref`, `project_ref`, and `workspace_root` whenever they are known. Sleep maintenance should be able to reconstruct same-project chronology and correction episodes rather than reading every observation as an isolated note.
16. Lessons about current model or runtime behavior are valid when they stay bounded and auditable. Preserve the most precise runtime identity that is actually known, and if exact model identity is not surfaced reliably, scope the lesson more conservatively to the active Codex runtime, current environment, or known model family.
17. When such a lesson is likely to become a card later, keep more than one retrieval path in view: a runtime-facing route such as `codex/runtime-behavior/...` plus any prompting, tool-use, workflow, or planning routes that materially shaped the behavior.
18. Lessons about a specific user are also valid when they stay bounded, evidence-based, and behaviorally framed. Record them as task-conditioned private predictions about likely preference, correction, or judgment rather than as personality labels or broad character impressions.

Sleep maintenance checklist:

1. Inspect the explicit taxonomy layer:
   `python .agents/skills/local-kb-retrieve/scripts/kb_taxonomy.py --json`
2. Inspect the smallest undeclared taxonomy routes that are currently implied by observed entries:
   `python .agents/skills/local-kb-retrieve/scripts/kb_taxonomy.py --gaps-only --json`
3. Inspect recent route navigation if the taxonomy view exposes undeclared branches you need to understand:
   `python .agents/skills/local-kb-retrieve/scripts/kb_nav.py --json`
4. Run consolidation in report-only mode first. Keep deterministic repair and semantic repair conceptually separate:
   `python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py --json --apply-mode none`
5. If the grouped history looks clean, allow only the lowest-risk automatic apply path:
   `python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py --json --apply-mode new-candidates`
   Treat broad routes as proposal-only even when they repeat; in the current implementation, current low-risk auto-apply should stay on routes with at least 3 segments.
   Only create candidate cards from observations with concrete future utility: complete predictive evidence plus actionable `operational_use`. Low-confidence seeds are allowed; low-utility observations should stay history-only or be ignored through an explicit maintenance decision.
   For direct entry-link maintenance, `python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py --json --apply-mode related-cards` may update stable `related_cards`.
   For stable alternate-route maintenance, `python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py --json --apply-mode cross-index` may update low-risk `cross_index` routes when repeated route evidence is already strong enough.
6. Restrict automatic apply to deterministic rules or simple thresholded semantic cases. Keep higher-ambiguity semantic changes proposal-only until the support and contradiction thresholds are met.
7. Inspect the per-action proposal stubs for the run:
   `python .agents/skills/local-kb-retrieve/scripts/kb_proposals.py --run-id <run_id> --json`
8. If AI decides a weak observation should stay history-only, a candidate should be rejected, a confidence review should be logged, or a split review should be closed without rewriting the card yet, record that decision explicitly:
   `python .agents/skills/local-kb-retrieve/scripts/kb_maintenance.py --decision-type observation-ignored|candidate-rejected|confidence-reviewed|split-reviewed --action-key <action_key> --resolved-event-ids <csv_event_ids> --reason "<why>" --json`
   For `split-reviewed`, always include the concrete supporting event ids from the review you are closing.
9. If the same trusted card keeps appearing in maintenance output, run a split review before assuming it should be split:
   - a **hub card** still expresses one bounded predictive relation and may stay as the route entry point
   - an **overloaded card** now mixes multiple scenarios, actions, results, or route-specific subcases and should move toward a split proposal, even when those branches still arrive through the same route
10. Review the emitted `snapshot.json`, `proposal.json`, action stub paths, and `apply.json` paths from the consolidation result.
11. If a consolidation run needs recovery, inspect and optionally restore history events:
   `python .agents/skills/local-kb-retrieve/scripts/kb_rollback.py inspect --run-id <run_id> --write-manifest --json`
   `python .agents/skills/local-kb-retrieve/scripts/kb_rollback.py restore --run-id <run_id> --artifact history-events --json`
12. End the maintenance pass with a concise summary:
   run id, created candidates, skipped actions, undeclared taxonomy signals, and the next deeper changes AI should make later.

Output discipline:

- Briefly state which entry ids influenced the answer.
- Treat those entry ids as the cards that materially influenced the work, not merely every card that happened to be retrieved.
- If the entries are weak or ambiguous, say so.
- Do not expose private entry content unless the user is authorized to see it.
- User-specific lessons should default to private handling and should describe what this user is likely to prefer or reject in a concrete task context, not who the user “is” in general.
- Keep sidecar agents scoped: `kb-scout` should be read-mostly and `kb-recorder` should default to history, comments, and candidate writes rather than broad structural edits.
- In a maintenance thread, be explicit about what the tooling actually changed versus what still remains a proposal.
- For non-trivial work, treat the explicit postflight observation check as part of done rather than optional housekeeping.
- After meaningful tasks, prefer recording one structured observation even when the outcome was a workflow or rule clarification. Sleep maintenance depends on accumulated evidence, not only on bug-fix episodes.
- During sleep maintenance, repeated hits are a split-review signal, not an automatic split rule. Keep intact hub cards that still express one predictive relation, and only split overloaded cards that now carry multiple predictive relations.
- Runtime-behavior lessons should be written as predictions about this runtime under concrete conditions, not as vague folklore about “LLMs in general.”
- Cross-index maintenance should only strengthen direct alternate retrieval paths from repeated actual route evidence in low-risk auto-apply. Pruning or broader route cleanup should remain proposal-first until stronger removal evidence exists.
- For search entry compatibility, prefer `--route-hint` in prompts and examples. The local search script still accepts the older `--path-hint` name for backward compatibility.
