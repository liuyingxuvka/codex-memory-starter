---
name: kb-sleep-maintenance
description: Run the repository-managed local KB Sleep maintenance pass. Use only when a user or automation explicitly asks for KB Sleep, sleep maintenance, local KB consolidation, or the scheduled KB Sleep automation; do not use for ordinary task preflight or active-task KB writes.
---

# KB Sleep Maintenance

Run one dedicated Sleep maintenance pass for this predictive KB repository.

Sleep is the experience-library editor, not a candidate factory. Optimize for accuracy, clarity, future usability, and logical route structure, not for fewer cards or more generated candidates.

## Authority

Work from the repository root. Treat these files as authoritative and read them before stateful maintenance:

- `PROJECT_SPEC.md`
- `docs/maintenance_agent_worldview.md`
- `docs/maintenance_runbook.md`
- `.agents/skills/local-kb-retrieve/MAINTENANCE_PROMPT.md`

Current user instructions still override repository files.

## Execution Contract

1. Before the first stateful command, run `python .agents/skills/local-kb-retrieve/scripts/kb_lane_status.py --lane kb-sleep --status running --wait-clear --poll-seconds 300 --json`. If another core maintenance lane is running, wait and recheck every 5 minutes until the lane is free; do not skip merely because another lane is active.
2. Write a visible execution plan before the first stateful command after the lane guard, with checkpoint statuses.
3. Read the shared maintenance-agent worldview and use it as the judgment model for accuracy, clarity, usefulness, evidence strength, and human-reviewable output quality.
4. Run the sleep self-preflight search against `system/knowledge-library/maintenance`.
5. Inspect taxonomy, route gaps, route navigation when needed, and proposal-mode consolidation output.
6. Track the current maintenance run id from the consolidation output or chosen `--run-id`; reuse that same run id in the final lane status completion command.
7. Before choosing any apply lane, summarize high-volume proposal output as a compact editorial sample pack: action counts, apply eligibility, top route clusters, duplicate candidate clusters, strong examples, weak/noisy examples, Architect-only items, Dream-only items, low-risk navigation examples, and hub-card review examples. Use that map before deep-reading large raw JSON.
8. Treat candidate backlog as a maintenance object: decide what should be kept, rewritten, merged, rejected, watched, or left proposal-only before adding more candidates.
9. Treat mechanical apply eligibility as capability only. Do not run a broad apply mode over every eligible action; keep the pass proposal-only unless a compact reviewed set of action keys is explicitly selected.
10. Run the mandatory similar-card merge checkpoint. Inspect cards surfaced by maintenance output for overlapping scenario, action, prediction, route, or evidence. Decide whether to merge, propose a merge, or skip application with a concrete reason.
11. Run the mandatory overloaded-card split checkpoint. Inspect recurrent, broad, or `split_review_suggestion` cards and decide whether each one is still a hub card, should move toward a split proposal, or should skip application with a concrete reason.
12. Run the organization Skill bundle consolidation checkpoint. For imported read-only organization Skills, group by `bundle_id`, keep only the latest approved version by `version_time`, preserve source-card references, and keep all local cards pointing at the same `bundle_id`.
13. Do not skip the merge, split, or Skill bundle consolidation checkpoint itself. It is acceptable to skip applying a merge, split, or Skill replacement when evidence, safety, tooling, or scope is insufficient, but the inspection and recorded decision must still happen.
14. Prefer functional, reusable domain paths over project-name route roots when reviewing candidates.
15. Continue through every safe checkpoint instead of stopping after a short proposal.
16. Apply only clearly eligible low-risk lanes supported by current tooling: new-candidates, related-cards, cross-index, AI-authored semantic-review, and AI-authored zh-CN i18n. Tool eligibility is not editorial approval; compare the whole eligible set with the editorial map before applying.
17. Do not create new candidates merely because the tooling can; use new-candidates only when backlog triage shows the scaffold would improve future retrieval.
18. If an apply mode contains both approved and unapproved actions, use selected action keys instead of skipping the whole lane: `--action-key <approved-action-key>` may be repeated. Skip only when the approved set cannot be named by exact action key.
19. Limit semantic-review to at most 3 trusted-card modifications per run.
20. Run exactly one final AI-authored zh-CN display completion checkpoint after candidate/card creation, semantic text changes, and route review are done. This single checkpoint covers card display fields and route/path display labels, writes missing route labels through the i18n plan, and replaces separate mid-run translation cleanup.
21. Keep taxonomy rewrites proposal-only unless current tooling cleanly supports the exact change.
22. Inspect rollback artifacts when needed, including history-events, related-card-entries, cross-index-entries, and semantic-review-entries when present.
23. Attempt supported low-risk repairs and rerun the relevant validation when a command exposes a fixable issue.
24. Run a final sleep postflight check.
25. Append one structured maintenance observation when the pass exposed a reusable lesson, route gap, card weakness, merge signal, split signal, Skill bundle update, or process hazard.
26. Run `python .agents/skills/local-kb-retrieve/scripts/kb_lane_status.py --lane kb-sleep --status completed --run-id <run_id> --json`.
27. Stop after that final observation. Do not immediately consolidate the observation just written.

## Report

Report the run id, checkpoint status, self-preflight entries, what became more accurate, clearer, or easier to retrieve, observation counts reviewed, candidates created or deliberately not created, weak/noisy material rejected or kept history-only, route adjustments or concerns, similar-card merge checkpoint decisions, overloaded-card split checkpoint decisions, organization Skill bundle consolidation decisions, semantic-review decisions applied or skipped, final zh-CN display completion status for cards and routes, translations updated or still missing, validations run, repaired or proposal-only issues, maintenance decisions, postflight observation status, undeclared taxonomy gaps, hub-vs-overloaded card reviews, and next proposal-only targets.
