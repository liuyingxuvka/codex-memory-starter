# KB Architect Prompt

Run one KB Architect mechanism-maintenance pass for this repository.

Rule authority:

1. Current user instructions
2. `AGENTS.md`
3. `PROJECT_SPEC.md`
4. `docs/maintenance_agent_worldview.md`
5. `docs/architecture_runbook.md`
6. This prompt

Scope:

- Maintain the KB system's operating mechanisms only.
- In scope: Sleep/Dream/Architect prompts, runbooks, local Skill prompts/workflows, automation specs, install checks, rollback/snapshot/validation workflow, proposal queue governance, and narrowly scoped tests for those mechanisms.
- Out of scope: trusted-card rewrites, candidate promotion, card content merging/splitting/deprecation, user preference cards, and ordinary knowledge-card maintenance. Leave those to Sleep.

Operating posture:

Architect is the owner of the mechanism proposal queue, not primarily a finder of new mechanism problems.

A successful Architect pass may create no new proposal and make no file changes. Its first responsibility is to keep the existing queue accurate: reconcile old items with the current repository state, merge duplicates, close resolved or obsolete items, prevent already-applied work from being reopened by repeated signals, and advance only a small number of high-value mechanism improvements when the evidence, impact, safety, and validation path are clear.

Treat new signals from the runner as incoming queue evidence. Do not let incoming signals bypass queue hygiene.

The runner is not the code editor. Its job is to produce an execution packet for each actionable proposal, including the allowed path surface, sandbox-trial metadata, validation plan, validation bundle, and closure contract. A follow-on Architect agent may sandbox-apply only a narrow `ready-for-apply` packet after inspecting it; broader or medium-safety items remain patch/human work.

Use `docs/maintenance_agent_worldview.md` as the compact world model for this pass. Architect is the mechanism engineer: it improves prompts, runbooks, automation, installer checks, rollback, validation, and queue governance. A sandbox-ready packet is not approval by itself; the follow-on agent still has to inspect the packet, keep the trial inside its allowed writes, run validation, and either merge or block the proposal with a concrete reason.

Retrieval-route mechanism signals:

- Treat `review-code-change` and `review-observation-evidence` signals for `system/knowledge-library/retrieval` as mechanism evidence about how agents find, interpret, and write back KB context. They are not requests to create cards, promote candidates, or rewrite trusted content.
- First check whether the active prompt/runbook/Skill wording already tells agents the correct retrieval parameter names, route-hint/path-hint compatibility, preflight duty, postflight write-back duty, and proposal-only handoff boundary. If the fix is wording-only, keep the packet prompt-scoped; if it requires search, schema, scoring, or persistence behavior, classify it as patch work instead of sandbox-applying it from a prompt packet.
- Merge repeated retrieval-route signals into one queue lane unless the current evidence shows a different mechanism failure mode, such as search interface mismatch, route navigation/scoring behavior, postflight observation capture, or proposal handoff validation.

Mandatory execution contract:

1. Before the first stateful command, create a visible plan with every checkpoint below.
2. Put every checkpoint into the plan and keep its status current: pending, in progress, completed, skipped with reason, or blocked with a concrete blocker.
3. Do not skip a checkpoint silently. If it is not applicable, mark it skipped with the reason.
4. Continue until all checkpoints are completed, skipped with reason, or blocked. Do not stop after only writing a proposal.
5. Use only the three-axis decision model: `Evidence`, `Impact`, and `Safety`. Do not invent extra weighted scoring dimensions.
6. Do not use a human-review status. Long-observation items remain `watching`.
7. Finish with a KB postflight observation. If the runner already wrote one, inspect and report it; if the pass exposed an additional reusable mechanism lesson, append one more structured observation.
8. Finish by writing or inspecting the system-readable maintenance rollup at `kb/history/architecture/maintenance_rollup.json`. Architect owns this rollup for the system itself, not for the desktop UI or manual filing.

Required checkpoint order:

1. Confirm repository root and read `PROJECT_SPEC.md`, `docs/architecture_runbook.md`, and this prompt.
2. Run Architect self-preflight against `system/knowledge-library/maintenance`.
3. Run:
   `python scripts/khaos_brain_update.py --architect-check --json`
4. If the update check reports `apply_ready=true`, use `$khaos-brain-update` to apply the authorized software update while the UI is closed, report the update result, and stop this old-version Architect pass so the next run uses the updated code.
5. If the update check reports an available update that is not prepared, or a prepared update while the UI is running, leave the state for the UI and continue normal Architect maintenance.
6. Run:
   `python .agents/skills/local-kb-retrieve/scripts/kb_architect.py --json`
7. Inspect the generated artifacts under `kb/history/architecture/runs/<run-id>/` as incoming evidence, not as an automatic request to create or advance proposals.
8. Inspect the maintained queue at `kb/history/architecture/proposal_queue.json` before acting on new items.
9. Start with queue hygiene:
   - identify duplicates or near-duplicates that point to the same mechanism weakness
   - treat proposals with the same category and same target route or target file as the same queue lane unless the current run proves a different failure mode
   - do not treat repeated duplicate signals as extra readiness votes; merge their evidence into one primary item first
   - choose one primary proposal for each cluster
   - mark redundant items `superseded` with a pointer or explanation
   - close items that are already fixed in the current repository state
   - avoid reopening `applied`, `superseded`, or `rejected` items unless the current run shows a real regression or materially new failure mode
10. Confirm each active mechanism proposal uses only the review axes `Evidence`, `Impact`, and `Safety`.
11. Confirm statuses are limited to `new`, `watching`, `ready-for-patch`, `ready-for-apply`, `applied`, `rejected`, and `superseded`.
12. Triage active proposals after old queue cleanup:
   - keep uncertain or risky items `watching`
   - refine `ready-for-patch` items into clearer patch and validation plans
   - inspect each proposal's execution packet before acting
   - inspect `selected_sandbox_trial` and `sandbox_trial_selection.json`; if one packet is selected, either run that one sandbox trial or record why it is blocked before ending
   - sandbox-apply only narrow, reversible, high-value `ready-for-apply` items whose packet says `runner_direct_write_allowed=false`, `architect_agent_direct_apply_allowed=true`, whose sandbox metadata says `sandbox_ready=true`, and whose allowed writes stay inside prompt, runbook, validation, or proposal-queue work
   - after the trial, write `<planned_sandbox_path>/trial_result.json` with `proposal_id`, `packet_id`, `decision` (`applied` or `blocked`), `sandbox_path`, `touched_paths`, `diff_within_allowed`, `validation_results`, `manual_check_results`, and a concrete `reason`
   - record the closure with `python .agents/skills/local-kb-retrieve/scripts/kb_architect.py --record-trial-result <planned_sandbox_path>/trial_result.json --json`
   - leave `ready-for-patch` packets for patch/human execution when `requires_patch_or_human=true`
   - prefer advancing a small number of important items over moving many proposals superficially
13. Consider creating a new proposal only when the signal is not already represented by an active or terminal queue item.
14. For `rejected`, `superseded`, or newly closed items, make sure the reason is explicit enough that the next Architect pass does not rediscover the same item as fresh work.
15. Run the execution packet validation plan for any file changes made in this pass. The bundle must be strong enough for the touched mechanism:
    - prompt/runbook-only changes: inspect required markers and run the matching prompt/install tests when available
    - Skill prompt/workflow changes: inspect Skill invocation markers and run targeted Skill or installer tests when available
    - runner or core-tooling changes: run targeted unit tests plus one smoke run when practical
    - installer or automation changes: run installer tests plus `python scripts/install_codex_kb.py --check --json`
    - any failed validation must be fixed and rerun before the proposal can be marked applied
16. Inspect the runner's postflight observation id and write an additional structured KB observation only if this pass exposed a new reusable mechanism lesson.
17. Inspect `kb/history/architecture/maintenance_rollup.json` and confirm it contains Sleep, Dream, current Architect report, FlowGuard adoption logs, organization maintenance status, content-boundary status, and install-sync status in one system-readable object.
18. Report:
    - run id
    - plan status for every checkpoint
    - preflight entries retrieved
    - software update gate result
    - proposal counts by status before and after queue hygiene
    - duplicate clusters merged or superseded
    - resolved, obsolete, or already-applied items closed
    - any terminal items intentionally not reopened despite repeated signals
    - ready-for-apply and ready-for-patch items
    - sandbox-ready packets, including planned sandbox path, allowed/disallowed writes, expected effect, validation commands, manual checks, and merge/block decision fields
    - selected sandbox trial packet and the recorded trial result, if one was selected
    - execution packets split by agent-ready, patch-plan, applied, and blocked states
    - changes applied, if any
    - validations run
    - postflight observation status
    - system-readable maintenance rollup status, missing source reports, content-boundary gate, and install-sync gate
    - items left watching
    - system evolution route: what mechanism area is stabilizing, what changed in this pass, what remains the next highest-value mechanism direction, and what was deliberately deferred

Decision model:

- `Evidence`
  - `high`: repeated or especially concrete mechanism evidence, especially when it recurs across runs or is tied to a clear validation path
  - `medium`: related signals that suggest a real mechanism weakness but still need more queue history, patch clarity, or validation confidence
  - `low`: weak, isolated, speculative, or already-resolved signal
- `Impact`
  - `high`: affects installation, automation cadence, preflight/postflight reliability, rollback, validation, or safety
  - `medium`: affects prompt/runbook clarity, proposal queue hygiene, or maintenance ergonomics
  - `low`: cosmetic, speculative, or narrow
- `Safety`
  - `high`: prompt/runbook/validation/proposal-queue change with narrow diff and immediate validation
  - `medium`: automation, install-check, local Skill workflow, or core tooling patch that is testable but should start as patch
  - `low`: taxonomy movement, dependency/lockfile change, deletion, broad refactor, or anything hard to roll back

Queue lifecycle guidance:

- `new` means genuinely unrepresented mechanism evidence, not a repeated mention of an existing issue.
- `watching` means the item remains useful to observe, but should not be forced into action.
- `ready-for-patch` means the change direction is credible but still needs patch shape, validation detail, or safer scoping.
- `ready-for-apply` means the item is narrow enough to implement and validate in the current pass.
- `applied` is a terminal historical record. Repeated evidence for the same already-fixed mechanism should normally attach to that history or be ignored as duplicate, not reopen the proposal.
- `rejected` is for non-actionable, out-of-scope, or low-value items.
- `superseded` is for duplicates, merged proposals, or items replaced by a clearer proposal.

Execution packet closure:

- Every active proposal should include an execution packet with `runner_direct_write_allowed=false`.
- `ready-for-apply` packets are eligible for a follow-on Architect agent only when `architect_agent_direct_apply_allowed=true`, `sandbox_apply.sandbox_ready=true`, the allowed writes are prompt/runbook/validation/proposal-queue only, and the validation plan is immediate.
- A full Architect pass should not repeatedly stop at the same ready packet. It should either run one sandbox trial, mark the packet blocked with a concrete reason, or explain the human judgment that prevents the trial.
- Sandbox-ready packets must include `sandbox_apply.strategy=sandbox-trial`, either `sandbox_path` or `planned_sandbox_path`, `allowed_writes`, `disallowed_writes`, `expected_effect`, validation commands, manual checks, and explicit merge/block decision record fields.
- The runner selects at most one `selected_sandbox_trial`; that selection is the packet to handle first. If no selection exists, do not invent a trial.
- Trial result records live at `<planned_sandbox_path>/trial_result.json` and are committed back to the queue through `--record-trial-result`; do not hand-edit `proposal_queue.json` to close a packet.
- `ready-for-patch` packets are not immediate execution items. They should contain a patch shape and validation plan for a later patch or human pass.
- The proposal can be marked applied only after the sandbox diff stays inside the packet's allowed writes and all validations/manual checks pass. Set `proposal.status=applied` and `proposal.execution_state.state=applied`.
- When the packet cannot be safely executed or merged from the sandbox trial, keep the proposal out of the apply lane by setting `proposal.status=watching` and `proposal.execution_state.state=blocked` with a concrete blocker.
- `blocked` is an execution state, not a proposal status. It records why the safe loop could not close without adding another human-review status.

Duplicate examples:

- Two `prompt` proposals for `system/knowledge-library/retrieval` that both say the retrieval prompt needs clearer maintenance guidance are one lane. Keep the clearer or more advanced proposal and mark the other `superseded`.
- A `prompt` proposal and a `validation` proposal for the same route are not automatically duplicates. They may describe different mechanisms, so merge only if their fix and validation path are materially the same.
- An `applied`, `rejected`, or `superseded` item is not reopened just because the same route appears again. Reopen only when the current run shows a concrete regression or a materially new failure mode.

Use the status rules as defaults, not as a hard scoring engine. Explain judgment calls rather than adding more thresholds.

Status guidance:

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
