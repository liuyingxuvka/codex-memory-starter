# Sleep Maintenance Runbook

This runbook is for the independent `kb-sleeper` maintenance pass. It is operational on purpose: use the current file-based tools, keep every change logged, emit snapshots before risky steps, and prefer reversible updates.

`PROJECT_SPEC.md` remains the canonical source for repository rules and thresholds. This runbook describes how to operate the current tooling safely. If the runbook and the spec disagree, follow the spec and then simplify the runbook.

The repository installer is expected to provision a repo-managed `KB Sleep` cron automation under `$CODEX_HOME/automations/`. Re-running `python scripts/install_codex_kb.py --json` on another machine should refresh that schedule automatically. The automation spec should keep model selection policy-based: strongest available model plus deepest supported reasoning, resolved during install rather than pinned to a specific model version.

## Rule Discipline

- Keep the mathematical rules simple and explicit. Prefer additive scores, counts, and fixed thresholds over adaptive or opaque heuristics.
- Start with a visible sleep execution plan. The maintenance agent should write a concrete checkpoint plan before the first stateful maintenance command and keep each checkpoint marked pending, in progress, completed, skipped with reason, or blocked with a concrete blocker.
- Do not stop after a short proposal or one successful command when a natural next checkpoint remains. Continue through all safe maintenance checkpoints before finalizing.
- If a command exposes a low-risk issue that current tooling supports, attempt the supported repair and rerun the relevant validation. If it is outside the current apply boundary, record it as proposal-only or as a maintenance observation and keep moving through remaining safe checkpoints.
- Run a sleep self-preflight before maintenance changes. The sleep pass is itself a KB task, so it should recall prior maintenance lessons before consolidation or apply work.
- Separate online-path survival from sleep-time repair. The active retrieval path should stay small, stable, and non-mutating; sleep maintenance is where cleanup and repair belong.
- Keep sleep separate from dream exploration. Consolidation and exploration should not share the same live maintenance window or mutate the same repository state concurrently.
- Keep sleep separate from Architect mechanism maintenance. Sleep owns card and memory-surface maintenance; Architect owns prompts, runbooks, automation, install checks, validation, rollback, and proposal-queue governance.
- Treat `confidence` and `status` as reranking terms, not as stand-alone evidence that can create a hit without route or lexical support.
- Every auto-apply rule should answer four questions clearly: what inputs it reads, what condition it checks, what file change it makes, and how it is validated or rolled back.
- Semantic auto-apply should preserve AI agency but limit blast radius: AI decides the card outcome, while tooling requires cited evidence, risk, utility assessment, expected retrieval effect, rollback notes, and a maximum of 3 trusted-card modifications per run.
- End every non-empty sleep pass with an explicit postflight check. If the pass exposed a reusable process lesson, card weakness, route gap, split signal, translation gap, or apply hazard, append one structured observation before finalizing.
- After that final sleep postflight observation is written, stop the pass. Do not immediately run consolidation again on the observation that was just appended.

## Repair Lanes

- `deterministic repair`
  - Purpose: fix low-ambiguity hygiene issues such as malformed fields, canonical formatting, path normalization, and other repairs that can be described by fixed rules.
  - Apply rule shape: exact condition sets, no fuzzy judgment, mechanical validation after apply.
- `semantic repair`
  - Purpose: update meaning-bearing structures such as candidate promotion, card rewrite, merge, split, deprecation, or taxonomy change.
  - Apply rule shape: AI-authored decisions over evidence packets, not pure thresholds. Repeated evidence is review pressure; it should not replace AI judgment.
  - Current trusted-card budget: at most 3 trusted cards may be automatically modified in one semantic-review apply run.
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
2. Write a visible sleep execution plan for this run and keep checkpoint statuses current until the final report.
3. Run a sleep self-preflight search with route hint `system/knowledge-library/maintenance`; treat hits as bounded context for this maintenance pass.
4. If the last task did not already do it, append missing observations with `kb_feedback.py`.
5. Classify the work into `deterministic repair` or `semantic repair` before any apply decision.
6. Run consolidation in proposal mode first and inspect the grouped actions.
7. If the grouped actions are low-risk and fit a deterministic rule or a simple semantic threshold, rerun consolidation with one of the low-risk apply modes:
   - `--apply-mode new-candidates` for route-grouped candidate scaffolds
   - `--apply-mode related-cards` for direct related-card maintenance
   - `--apply-mode cross-index` for stable alternate-route maintenance on `cross_index`
   - `--apply-mode i18n-zh-CN --i18n-plan <path>` for AI-authored Chinese display translations
   - `--apply-mode semantic-review --semantic-review-plan <path>` for AI-authored keep/rewrite/confidence/promotion/demotion/deprecation decisions
   - `review-route-i18n` actions are not auto-applied; patch the route display-label map manually and keep canonical routes unchanged
   - `new-candidates` requires concrete future utility: complete predictive evidence plus an actionable `operational_use`; low-confidence seeds are allowed, low-utility observations stay history-only
   - after any candidate/card creation pass, inspect `apply_summary.i18n_followup`; if it says translations are required, treat i18n as the final cleanup stage for that sleep pass
   - after any candidate/card creation or review pass, inspect route quality; prefer functional, reusable `domain_path` routes and keep project/repository/product names as provenance or tags unless the card is truly project-specific
8. Inspect per-action proposal stubs with `kb_proposals.py`.
   - When a grouped route action includes explicit contrastive evidence, prefer candidate scaffolds whose main `predict.expected_result` reflects the stronger revised path and whose `predict.alternatives` preserves the weaker earlier branch.
9. When a semantic card change is justified, author a local semantic review plan. The plan must cite current action `evidence_event_ids`, set `apply: true`, include `rationale`, `risk`, `utility_assessment`, `expected_retrieval_effect`, and `rollback_note`, and respect the trusted-card budget of 3. Use `utility_assessment.judgment: useful` for `keep`, `rewrite`, `adjust-confidence`, or `promote`; use a non-useful judgment such as `low-utility`, `obsolete`, `misleading`, `unclear`, or `insufficient-evidence` for `demote` or `deprecate`.
10. If a weak observation should be ignored, a candidate should be rejected, a confidence review should be logged, or a split review should be closed without rewriting the trusted card yet, append that decision with `kb_maintenance.py`.
11. For cards that recur in maintenance output, run a split review:
   - keep a hub card intact when it still expresses one bounded predictive relation
   - propose a split when the card has become overloaded with multiple scenarios, actions, results, or route-specific branches, even if those branches are still appearing through one route
   - allow split children to remain under the same route and cross-reference a lighter hub card when that improves navigation
12. Inspect emitted artifacts under `kb/history/consolidation/<run-id>/`.
13. If needed, generate a rollback manifest with `kb_rollback.py inspect --write-manifest`.
14. If the pass produced a bad low-risk apply, restore `history-events` from the snapshot.
15. Rerun or inspect the relevant validation after any repair or apply lane before advancing the plan.
16. Run a final sleep postflight check and append one structured maintenance observation when the pass exposed a reusable lesson, miss, process weakness, route gap, card weakness, split signal, translation gap, or apply hazard.
17. After writing that final maintenance observation, stop the current pass rather than immediately processing the new event.
18. Leave higher-risk work that is not represented as a supported semantic-review decision as proposal-only for a later AI maintenance pass.

## Commands To Run Now

Run the sleep self-preflight before maintenance changes:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_search.py `
  --path-hint system/knowledge-library/maintenance `
  --query "sleep maintenance consolidation i18n route labels split review postflight" `
  --top-k 5 `
  --json
```

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

Record the final sleep postflight observation when the pass exposed a reusable maintenance lesson:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_feedback.py `
  --task-summary "Sleep maintenance run <run_id> exposed a reusable maintenance lesson" `
  --route-hint "system/knowledge-library/maintenance" `
  --entry-ids "<entry_ids_that_influenced_the_pass>" `
  --hit-quality hit `
  --outcome "<what the sleep pass changed or learned>" `
  --comment "<why this should inform future maintenance>" `
  --scenario "<when future sleep maintenance should apply this>" `
  --action-taken "<what this sleep pass did>" `
  --observed-result "<what happened>" `
  --operational-use "<how future sleep runs should adapt>" `
  --reuse-judgment "<why this is reusable or one-off>" `
  --suggested-action update-card `
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

Apply AI-authored semantic card decisions:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py `
  --run-id daily-maintenance-semantic `
  --emit-files `
  --apply-mode semantic-review `
  --semantic-review-plan kb/history/consolidation/daily-maintenance-semantic/semantic_review_plan.yaml `
  --json
```

The semantic review plan should be a local YAML file authored by the maintenance AI:

```yaml
kind: local-kb-semantic-review-plan
trusted_card_limit: 3
decisions:
  - action_key: review-entry-update::entry::model-004
    entry_id: model-004
    apply: true
    decision: rewrite
    risk: medium
    utility_assessment:
      judgment: useful
      reason: The card remains useful for future retrieval but needs a narrower operational surface.
    evidence_event_ids:
      - obs-123
    rationale: The cited evidence shows the card remains useful but needs a narrower predictive claim.
    expected_retrieval_effect: Future retrieval should surface a more specific guidance surface for the same route.
    rollback_note: Restore the previous entry payload from the semantic-review apply report if the rewrite performs worse.
    updated_fields:
      title: More specific predictive title
      use:
        guidance: Updated operational guidance.
```

Apply AI-authored zh-CN display translations:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_consolidate.py `
  --run-id daily-maintenance-i18n `
  --emit-files `
  --apply-mode i18n-zh-CN `
  --i18n-plan kb/history/consolidation/daily-maintenance-i18n/i18n_zh-CN_plan.yaml `
  --json
```

The i18n plan should be a local YAML file authored by the maintenance AI:

```yaml
language: zh-CN
translations:
  model-004:
    title: 中文标题
    if:
      notes: 中文适用场景
    action:
      description: 中文动作或条件
    predict:
      expected_result: 中文预测结果
      alternatives:
        - when: 中文分支条件
          result: 中文分支结果
    use:
      guidance: 中文使用方式
```

Route segment display labels are handled separately from card text translations. If proposal output includes `review-route-i18n`, inspect `signals.missing_route_segment_labels`, then patch the zh-CN route segment display map in code. Do not rename `domain_path`, `cross_index`, taxonomy routes, search hints, or file paths.

Rollback semantic-review entry file changes from the apply report when a semantic apply performs worse:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_rollback.py `
  restore `
  --run-id daily-maintenance-semantic `
  --artifact semantic-review-entries `
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
  - the observations include task summaries
  - at least one supporting observation has future utility: complete predictive evidence plus concrete `operational_use` that can guide later action selection
  - there are at least 2 grouped supporting observations, or exactly 1 supporting observation that already has complete predictive evidence (`scenario`, `action_taken`, and `observed_result`) and future utility
  - single-observation candidates are created as low-confidence retrieval seeds, not as trusted rules or promotion-ready cards
  - if the supporting observations recorded weaker-path versus revised-path evidence, preserve that branch structure in the scaffold instead of flattening it into one success summary
- Auto-apply `review-related-cards` actions only when repeated co-use of actually used `entry_ids` already supports a stable direct related-card set
- Auto-apply `review-cross-index` actions only when repeated route evidence already supports a stable direct `cross_index` update
- Auto-apply `review-i18n` actions only when an AI-authored `zh-CN` translation plan is supplied; English top-level fields remain canonical
- Auto-apply semantic card changes only when an AI-authored semantic review plan is supplied; thresholds may trigger review pressure, but AI must decide the specific `keep`, `rewrite`, `adjust-confidence`, `promote`, `demote`, or `deprecate` action, cite the supporting action event ids, and include `utility_assessment`
- Cap semantic-review trusted-card modifications at 3 per run, including trusted rewrites, trusted confidence changes, deprecations, demotions, and candidate promotions into trusted scope
- Restore `kb/history/events.jsonl` from a consolidation snapshot

## Still Proposal-Only

- Updating existing cards without an AI-authored semantic review plan
- Promoting candidates into `kb/public/` or `kb/private/` without an AI-authored semantic review plan
- Taxonomy changes, including route add/rename/move/split/merge
- Code-change suggestions from history
- Candidate creation when the observation lacks complete predictive evidence or concrete future utility
- Any rollback beyond `history-events` and semantic-review entry-file restore from `apply.json`
- Split/merge restructuring unless represented as concrete supported semantic-review rewrites
- Any semantic repair that does not cite evidence, risk, expected retrieval effect, and rollback notes

This list is about the current implementation boundary, not the long-term architecture. The architecture may later allow broader AI maintenance, but until the tooling supports those writes cleanly, keep them proposal-only.

## Suggested Maintenance Thread Prompt

Use this as the opening prompt for an independent maintenance chat or future automation:

```text
Run a local KB sleep-maintenance pass for this repository.

Goals:
1. Write a visible sleep execution plan before the first stateful command and keep checkpoint statuses current.
2. Run a sleep self-preflight search against system/knowledge-library/maintenance before consolidation.
3. Read recent observation history and keep the run file-based, logged, and reversible.
4. Classify findings into deterministic repair or semantic repair before applying anything.
5. Use kb_consolidate.py in proposal mode first.
6. Only use --apply-mode new-candidates if the grouped actions are clearly low-risk and eligible.
7. For semantic card changes, let AI judge the card content and author a semantic-review plan; do not let raw thresholds directly decide rewrite, promotion, demotion, or deprecation.
8. Apply semantic-review only with evidence ids, risk, utility assessment, expected retrieval effect, rollback note, and the trusted-card modification cap of 3.
9. After any candidate/card creation or semantic-review text change, inspect missing zh-CN display translations, author an i18n plan for missing fields, and run --apply-mode i18n-zh-CN as the final cleanup stage.
10. Review candidate routes: prefer functional, reusable domain paths; keep project names as provenance or tags unless the card is truly project-specific.
11. Keep deterministic rules simple, but do not replace AI semantic judgment with raw thresholds.
12. Inspect snapshot/proposal/apply artifacts for the run.
13. If a supported low-risk issue appears, attempt the repair, rerun the relevant validation, and update the execution plan instead of stopping early.
14. If a weak observation should be ignored, a candidate should be rejected, a confidence review should be recorded, or a split review should be closed without rewriting the card yet, use kb_maintenance.py to append the decision trace.
15. If the apply looks wrong, prepare or execute kb_rollback.py restore for history-events or semantic-review entry files.
16. Do not rewrite trusted cards or taxonomy directly unless the current semantic-review tooling supports the change and the plan satisfies the safety fields; otherwise leave those as proposal-only notes.
17. If a trusted card keeps recurring, decide whether it is a hub card or an overloaded card before proposing a split. Repeated hits alone are not enough.
18. Before finalizing, run a sleep postflight check and append one structured observation if this maintenance pass exposed a reusable lesson, route gap, card weakness, or process hazard.
19. After writing that final observation, stop; do not immediately rerun consolidation on the just-written event.

Report:
- run id used
- sleep execution plan status for every checkpoint
- self-preflight entries considered
- observation count reviewed
- candidates created, if any
- semantic-review decisions applied, reviewed, or skipped
- zh-CN translations updated or still missing
- maintenance decisions recorded, if any
- validations run and whether failed checks were repaired or left proposal-only
- final sleep postflight observation recorded, or why none was recorded
- actions left proposal-only
- whether rollback inspection was generated
- which cards were reviewed as hub vs overloaded
- concrete next maintenance targets
```
