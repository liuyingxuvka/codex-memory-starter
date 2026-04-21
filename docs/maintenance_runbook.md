# Sleep Maintenance Runbook

This runbook is for the independent `kb-sleeper` maintenance pass. It is operational on purpose: use the current file-based tools, keep every change logged, emit snapshots before risky steps, and prefer reversible updates.

`PROJECT_SPEC.md` remains the canonical source for repository rules and thresholds. This runbook describes how to operate the current tooling safely. If the runbook and the spec disagree, follow the spec and then simplify the runbook.

The repository installer is expected to provision a repo-managed `KB Sleep` cron automation under `$CODEX_HOME/automations/`. Re-running `python scripts/install_codex_kb.py --json` on another machine should refresh that schedule automatically.

## Rule Discipline

- Keep the mathematical rules simple and explicit. Prefer additive scores, counts, and fixed thresholds over adaptive or opaque heuristics.
- Separate online-path survival from sleep-time repair. The active retrieval path should stay small, stable, and non-mutating; sleep maintenance is where cleanup and repair belong.
- Keep sleep separate from dream exploration. Consolidation and exploration should not share the same live maintenance window or mutate the same repository state concurrently.
- Treat `confidence` and `status` as reranking terms, not as stand-alone evidence that can create a hit without route or lexical support.
- Every auto-apply rule should answer four questions clearly: what inputs it reads, what condition it checks, what file change it makes, and how it is validated or rolled back.

## Repair Lanes

- `deterministic repair`
  - Purpose: fix low-ambiguity hygiene issues such as malformed fields, canonical formatting, path normalization, and other repairs that can be described by fixed rules.
  - Apply rule shape: exact condition sets, no fuzzy judgment, mechanical validation after apply.
- `semantic repair`
  - Purpose: update meaning-bearing structures such as candidate promotion, card rewrite, merge, split, deprecation, or taxonomy change.
  - Apply rule shape: repeated evidence plus contradiction checks. A simple default is `support_count >= 3` and `contradiction_count == 0`, followed by snapshot, validation, and rollback readiness.
  - For split decisions, repeated hits are only a review trigger. First decide whether the card is still a hub card with one bounded predictive relation or an overloaded card that now carries multiple predictive relations.
- If a problem cannot be expressed as either a deterministic rule or a simple semantic threshold, leave it as proposal-only material for a later maintenance pass.

## When To Run

- Run after active work sessions that produced multiple observations or misses.
- Run at least daily while the repository is evolving quickly.
- Run before changing retrieval behavior or route structure.
- Keep the sleep schedule offset from any dream schedule, and skip the pass if a dream run may still be active or unresolved.
- Do not run inside the main task thread unless the task is blocked by KB drift.

## Roles

- `kb-scout`: read-only preflight before non-trivial work. Finds likely routes and cards.
- `kb-recorder`: post-task logger. Appends observations, misses, and candidate hints.
- `kb-sleeper`: separate maintenance pass. Reviews accumulated history, emits snapshots/proposals, applies only low-risk changes, and prepares the next maintenance queue.

## Maintenance Checklist

1. Confirm the repo root and work from the repository root.
2. If the last task did not already do it, append missing observations with `kb_feedback.py`.
3. Classify the work into `deterministic repair` or `semantic repair` before any apply decision.
4. Run consolidation in proposal mode first and inspect the grouped actions.
5. If the grouped actions are low-risk and fit a deterministic rule or a simple semantic threshold, rerun consolidation with one of the low-risk apply modes:
   - `--apply-mode new-candidates` for route-grouped candidate scaffolds
   - `--apply-mode related-cards` for direct related-card maintenance
   - `--apply-mode cross-index` for stable alternate-route maintenance on `cross_index`
6. Inspect per-action proposal stubs with `kb_proposals.py`.
   - When a grouped route action includes explicit contrastive evidence, prefer candidate scaffolds whose main `predict.expected_result` reflects the stronger revised path and whose `predict.alternatives` preserves the weaker earlier branch.
7. If a weak observation should be ignored, a candidate should be rejected, a confidence review should be logged, or a split review should be closed without rewriting the trusted card yet, append that decision with `kb_maintenance.py`.
8. For cards that recur in maintenance output, run a split review:
   - keep a hub card intact when it still expresses one bounded predictive relation
   - propose a split when the card has become overloaded with multiple scenarios, actions, results, or route-specific branches, even if those branches are still appearing through one route
   - allow split children to remain under the same route and cross-reference a lighter hub card when that improves navigation
9. Inspect emitted artifacts under `kb/history/consolidation/<run-id>/`.
10. If needed, generate a rollback manifest with `kb_rollback.py inspect --write-manifest`.
11. If the pass produced a bad low-risk apply, restore `history-events` from the snapshot.
12. Leave higher-risk work as proposal-only for a later AI maintenance pass.

## Commands To Run Now

Record an observation after a task:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_feedback.py `
  --task-summary "Adjusted local KB maintenance workflow" `
  --route-hint "system/knowledge-library/retrieval" `
  --entry-ids "model-004" `
  --hit-quality hit `
  --outcome "Workflow stayed aligned with current repo tooling" `
  --comment "Maintenance pass needs a reusable runbook" `
  --suggested-action new-candidate `
  --json
```

Inspect consolidation without applying changes:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py `
  --run-id daily-maintenance `
  --emit-files `
  --apply-mode none `
  --json
```

Apply low-risk candidate scaffolds:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py `
  --run-id daily-maintenance `
  --emit-files `
  --apply-mode new-candidates `
  --json
```

Apply low-risk related-card maintenance:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py `
  --run-id daily-maintenance `
  --emit-files `
  --apply-mode related-cards `
  --json
```

Apply low-risk cross-index maintenance:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py `
  --run-id daily-maintenance `
  --emit-files `
  --apply-mode cross-index `
  --json
```

Inspect per-action proposal stubs for the maintenance run:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_proposals.py `
  --run-id daily-maintenance `
  --json
```

Record an explicit maintenance decision without rewriting a trusted card yet:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_maintenance.py `
  --decision-type confidence-reviewed `
  --action-key "review-confidence::entry::model-004" `
  --resolved-event-ids "event-1,event-2" `
  --entry-id "model-004" `
  --review-state "watch-and-review" `
  --previous-confidence "0.96" `
  --new-confidence "0.74" `
  --reason "Weakening evidence was reviewed during maintenance; keep the card active but under watch." `
  --json
```

Record a split-review outcome after deciding to keep a card as a hub or to revisit a future split later:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_maintenance.py `
  --decision-type split-reviewed `
  --action-key "review-entry-update::entry::model-004" `
  --resolved-event-ids "event-3,event-4" `
  --entry-id "model-004" `
  --decision-summary "keep-as-hub-for-now" `
  --reason "Repeated same-route hits were reviewed and the card remains the right hub entry for now." `
  --json
```

`split-reviewed` decisions should always reference the concrete supporting event ids from the review that was just closed. Do not use an empty `--resolved-event-ids`, or the action may be suppressed too broadly.

Inspect restorable artifacts for a consolidation run:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_rollback.py inspect `
  --run-id daily-maintenance `
  --write-manifest `
  --json
```

Dry-run or execute the current low-risk restore path:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_rollback.py restore `
  --run-id daily-maintenance `
  --artifact history-events `
  --dry-run `
  --json
```

Inspect the explicit taxonomy tree:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_taxonomy.py `
  --json
```

Inspect the smallest undeclared taxonomy routes currently implied by entries:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_taxonomy.py `
  --gaps-only `
  --json
```

## Outputs To Inspect

- `kb_feedback.py --json`
  - confirm `event.event_id`, `event.event_type`, `event.created_at`, and `history_path`
- `kb_consolidate.py --json`
  - inspect `candidate_action_count`
  - inspect each action's `action_type`, `target`, `signals`, `apply_eligibility`, and `recommended_next_step`
  - inspect `apply_summary` and `artifact_paths`
- `kb/history/consolidation/<run-id>/snapshot.json`
  - confirms which history events were included in the pass
- `kb/history/consolidation/<run-id>/proposal.json`
  - main review artifact for grouped maintenance actions
- `kb/history/consolidation/<run-id>/actions/*.json`
  - one per-action stub for deeper AI maintenance follow-up
- `kb/history/consolidation/<run-id>/apply.json`
  - present when a low-risk apply mode such as `new-candidates`, `related-cards`, or `cross-index` was used
- `kb/history/consolidation/<run-id>/rollback_manifest.json`
  - present after `kb_rollback.py inspect --write-manifest`
- `kb_proposals.py --run-id <run-id> --json`
  - inspect the per-action stub summary by `action_type` and `suggested_artifact_kind`
- `kb_maintenance.py --json`
  - confirm the decision event type, action key, resolved event ids, and any confidence review metadata appended to history
- `kb_taxonomy.py --json`
  - inspect the declared route layer and current observed coverage counts
- `kb_taxonomy.py --gaps-only --json`
  - inspect undeclared route branches that AI may later turn into taxonomy proposals

## Low-Risk Changes Currently Allowed

- Append new observation events with `kb_feedback.py`
- Create explicit manual candidate cards with `kb_capture_candidate.py`
- Run consolidation in proposal mode
- Record explicit maintenance decisions with `kb_maintenance.py`
- Apply deterministic-repair rules only when the change is low-ambiguity, mechanically validated, and reversible
- Auto-apply grouped `consider-new-candidate` actions only when:
  - the target is a route
  - the route is semantically specific enough to be useful as a scaffold; in the current implementation this means at least 3 route segments, so broad routes remain proposal-only
  - there are at least 2 grouped supporting observations
  - the observations include task summaries
  - if the supporting observations recorded weaker-path versus revised-path evidence, preserve that branch structure in the scaffold instead of flattening it into one success summary
- Auto-apply `review-related-cards` actions only when repeated co-use of actually used `entry_ids` already supports a stable direct related-card set
- Auto-apply `review-cross-index` actions only when repeated route evidence already supports a stable direct `cross_index` update
- Restore `kb/history/events.jsonl` from a consolidation snapshot

## Still Proposal-Only

- Updating existing cards
- Promoting candidates into `kb/public/` or `kb/private/`
- Taxonomy changes, including route add/rename/move/split/merge
- Code-change suggestions from history
- Single-observation candidate creation
- Any rollback beyond `history-events`
- Any semantic repair that does not yet satisfy the agreed fixed thresholds

This list is about the current implementation boundary, not the long-term architecture. The architecture may later allow broader AI maintenance, but until the tooling supports those writes cleanly, keep them proposal-only.

## Suggested Maintenance Thread Prompt

Use this as the opening prompt for an independent maintenance chat or future automation:

```text
Run a local KB sleep-maintenance pass for this repository.

Goals:
1. Read recent observation history and keep the run file-based, logged, and reversible.
2. Classify findings into deterministic repair or semantic repair before applying anything.
3. Use kb_consolidate.py in proposal mode first.
4. Only use --apply-mode new-candidates if the grouped actions are clearly low-risk and eligible.
5. Keep the mathematical rules simple: counts, thresholds, and explicit conditions only.
6. Inspect snapshot/proposal/apply artifacts for the run.
7. If a weak observation should be ignored, a candidate should be rejected, a confidence review should be recorded, or a split review should be closed without rewriting the card yet, use kb_maintenance.py to append the decision trace.
8. If the apply looks wrong, prepare or execute kb_rollback.py restore for history-events.
9. Do not rewrite trusted cards or taxonomy directly unless the fixed semantic thresholds are satisfied; otherwise leave those as proposal-only notes.
10. If a trusted card keeps recurring, decide whether it is a hub card or an overloaded card before proposing a split. Repeated hits alone are not enough.

Report:
- run id used
- observation count reviewed
- candidates created, if any
- maintenance decisions recorded, if any
- actions left proposal-only
- whether rollback inspection was generated
- which cards were reviewed as hub vs overloaded
- concrete next maintenance targets
```
