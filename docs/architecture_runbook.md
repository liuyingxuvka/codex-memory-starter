# KB Architect Runbook

This runbook defines the `kb-architect` mechanism-maintenance lane. It runs after Sleep and Dream and controls how the KB system improves its own operating machinery without taking over card-content maintenance.

The default local cadence is Sleep at 12:00, Dream at 13:00, and Architect at 14:00. Each core maintenance lane acquires the shared waiting lock before it starts; if another lane is active, it waits and rechecks every five minutes, so scheduled work is serialized rather than skipped.

`PROJECT_SPEC.md` remains authoritative. `docs/maintenance_agent_worldview.md` defines the shared Sleep/Dream/Architect judgment model. If this runbook and the spec disagree, follow the spec and simplify this runbook.

The runner is a planner and queue maintainer, not a direct code editor. It should emit execution packets that tell a follow-on Architect agent which proposal is safe to apply now, which one needs a patch or human pass, and how to mark the result applied or blocked. Architect also owns the system-readable maintenance rollup at `kb/history/architecture/maintenance_rollup.json`, where the system can read Sleep, Dream, Architect, FlowGuard, organization, content-boundary, and install-sync status together.

Before judging proposals, read the shared maintenance-agent worldview. Treat Architect as the mechanism engineer: its job is to make the operating system clearer and more reliable, then verify sandbox-upgrade trials before any real merge.

The repository installer is expected to provision a repo-managed `KB Architect` cron automation under `$CODEX_HOME/automations/`. Re-running `python scripts/install_codex_kb.py --json` on another machine should refresh that schedule automatically. The automation spec should keep model selection policy-based: strongest available model plus deepest supported reasoning, resolved during install rather than pinned to a specific model version.

## Purpose

- `sleep` consolidates real task evidence and maintains memory/card surfaces.
- `dream` runs bounded exploratory checks and writes provisional evidence.
- `architect` maintains the mechanisms that make Sleep, Dream, retrieval, local Skills, installation, validation, rollback, and proposal governance work reliably.

Architect is not a card-content maintainer. It does not rewrite trusted cards, promote candidates, split cards, merge cards, deprecate cards, or tune user-specific knowledge.

## Mandatory Order

Each Architect pass must follow this order and keep the execution plan status current until the end:

1. Confirm repository root and rule files.
2. Run self-preflight against `system/knowledge-library/maintenance`.
3. Run `python scripts/khaos_brain_update.py --architect-check --json`.
4. If the update check returns `apply_ready=true`, use `$khaos-brain-update`, report the update result, and stop the old-version Architect pass so the next run uses the updated code.
5. If the update is available but not prepared, or prepared while the UI is running, leave the state for the UI and continue.
6. Run the Architect runner.
7. Inspect generated artifacts.
8. Inspect the maintained proposal queue.
9. Clean the queue before judging new work: merge duplicate lanes, mark redundant items `superseded`, close already-fixed items, and preserve terminal statuses unless a real regression appears.
10. Review proposals using exactly `Evidence`, `Impact`, and `Safety`.
11. Assign or confirm statuses.
12. Inspect execution packets and `selected_sandbox_trial`. If a packet is selected, run that one narrow sandbox trial or record a concrete blocker before ending; otherwise explain why no packet was selected. Apply only `ready-for-apply` items that are agent-ready inside the narrow prompt/runbook/validation/proposal-queue allowlist.
13. Generate or refine patch plans for `ready-for-patch` items.
14. Preserve `watching` items for long observation, including items whose execution state is blocked.
15. Run the packet validation bundle for any file changes.
16. Write `<planned_sandbox_path>/trial_result.json` with the trial decision, touched paths, validation results, manual checks, and reason, then close the packet with `python .agents/skills/local-kb-retrieve/scripts/kb_architect.py --record-trial-result <planned_sandbox_path>/trial_result.json --json`.
17. Mark successful packets applied through the recorder; mark unsafe or unvalidated packets blocked with a concrete blocker.
18. Confirm or append the final KB postflight observation.
19. Write or inspect `kb/history/architecture/maintenance_rollup.json` and confirm the rollup includes Sleep, Dream, current Architect report, FlowGuard adoption logs, organization maintenance status, content-boundary status, and install-sync status.
20. Report run id, checkpoint statuses, software update gate result, proposal status counts, selected sandbox trial, trial-result decision, execution packet modes, applied changes, blocked execution states, validations, system-readable maintenance rollup status, and remaining watching items.

If a checkpoint is not applicable, mark it skipped with a reason. Do not silently omit it.

## Decision Axes

Use only three axes. Do not add a large weighted scoring model.

- `Evidence`: how strong and repeated the signal is.
- `Impact`: how much the issue affects the KB system's maintenance mechanisms.
- `Safety`: how narrow, testable, and reversible the proposed change is.

Levels are `low`, `medium`, or `high`.

## Statuses

Allowed proposal statuses:

- `new`
- `watching`
- `ready-for-patch`
- `ready-for-apply`
- `applied`
- `rejected`
- `superseded`

There is no human-review status. High-risk or uncertain items remain under long observation as `watching` until evidence and safety improve.

`blocked` is an execution state, not a proposal status. Use `execution_state.state=blocked` when a packet cannot be executed inside the allowed surface or cannot pass validation. Keep the proposal status `watching` until a later pass has a safe way to clear the blocker.

## Queue Hygiene

Architect should make the proposal queue smaller and clearer when possible. New signals are incoming evidence, not automatic permission to create or advance proposals.

Treat same-category proposals with the same target route, target file, or same mechanism failure as one lane unless the current run shows a genuinely different failure mode. Keep one primary proposal, merge useful source evidence into it, and mark redundant items `superseded` with a pointer to the primary proposal.

Repeated duplicate signals are not extra readiness votes by themselves. First ask whether the mechanism is already represented, already fixed, or already rejected. Do not reopen `applied`, `rejected`, or `superseded` items unless the current run shows a concrete regression or materially new failure mode.

## Status Rules

- `Evidence=high`, `Impact=high|medium`, `Safety=high` -> `ready-for-apply`
- `Evidence=high`, `Safety=medium` -> `ready-for-patch`
- `Evidence=medium`, `Impact=high` -> `watching`
- `Evidence=low`, `Impact=low` -> usually `rejected`
- `Safety=low` -> `watching`, even when Evidence is high

These are decision rules, not hidden math.

## Execution Packets

Every active proposal should carry an execution packet. `ready-for-apply` packets must also carry sandbox-trial metadata so a follow-on Architect agent can try the change in an isolated apply path before deciding whether to merge or block it.

Do not let the queue repeatedly rediscover the same ready packet without movement. Once a packet is sandbox-ready, the next full Architect pass should either run one sandbox trial, mark the packet blocked with a concrete reason, or leave an explicit human-judgment blocker.

- `agent-ready-apply`: narrow prompt, runbook, validation, or proposal-queue work that a follow-on Architect agent may implement immediately after inspection.
- `patch-plan`: credible work that still needs a patch or human pass, usually because safety is medium or the scope touches automation, installer, Skill workflow, or core tooling.
- `watch`: useful queue evidence that is not executable yet.
- `closed-applied`: terminal applied history.
- `blocked`: an attempted packet could not safely close.

The runner itself keeps `runner_direct_write_allowed=false`. A sandbox-ready packet exposes `sandbox_apply.strategy=sandbox-trial`, either `sandbox_path` or `planned_sandbox_path`, `allowed_writes`, `disallowed_writes`, `expected_effect`, validation commands, manual checks, and merge/block decision record fields. A packet can be marked applied only after the sandbox diff stays inside `allowed_writes`, validations pass, manual checks pass, and any needed postflight observation is recorded. If the needed change escapes the allowlist, requires card-content maintenance, or fails validation, record `execution_state.state=blocked` with the concrete blocker.

The queue and report should expose `sandbox_ready_packets` and exactly one `selected_sandbox_trial` when an immediate trial is available. The selected packet is deterministic: prefer the oldest ready packet, then the safest prompt/runbook/validation/proposal-queue category, then proposal id. The follow-on agent should handle the selected packet before considering any other ready packet.

Trial results are structured queue updates, not ad-hoc prose. Write a JSON result under the selected packet's planned sandbox path:

```json
{
  "proposal_id": "<proposal_id>",
  "packet_id": "<packet_id>",
  "decision": "applied",
  "sandbox_path": "<planned_sandbox_path>",
  "touched_paths": [".agents/skills/local-kb-retrieve/ARCHITECT_PROMPT.md"],
  "diff_within_allowed": true,
  "validation_results": [{"command": "python -m unittest tests.test_kb_architect", "status": "passed"}],
  "manual_check_results": [{"check": "Confirm the diff stays inside the execution packet allowed_paths.", "status": "passed"}],
  "reason": "The sandbox trial stayed inside allowed writes and validation passed."
}
```

Then record it:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_architect.py `
  --record-trial-result <planned_sandbox_path>/trial_result.json `
  --json
```

Use `decision: "blocked"` with a concrete `reason` when the trial escapes allowed paths, fails validation, cannot be run, or needs card-content/taxonomy/human judgment. Do not mark a packet applied by editing `proposal_queue.json` directly.

## In Scope

- Sleep prompt and runbook quality
- Dream prompt and runbook quality
- Architect prompt and runbook quality
- local Skill prompt and workflow quality when repeated Skill-use evidence shows the instruction should change
- automation specs and cadence
- installer and install-check coverage
- validation bundles and test coverage for maintenance mechanisms
- rollback and snapshot workflow
- proposal queue lifecycle and duplicate clustering
- process hazards in preflight and postflight behavior

## Out Of Scope

- trusted-card rewrites
- candidate promotion
- card merge/split/deprecation
- card confidence changes
- user preference card maintenance
- taxonomy route rename/move
- dependency installation
- lockfile churn
- repo-wide formatting
- broad refactors

Out-of-scope signals should not be deleted. Architect can record that they belong to Sleep or long observation, but it must not act on them directly.

## Current Tooling Path

Run one Architect pass manually:

```powershell
python .agents/skills/local-kb-retrieve/scripts/kb_architect.py --json
```

The runner writes:

- `kb/history/architecture/runs/<run-id>/plan.json`
- `kb/history/architecture/runs/<run-id>/preflight.json`
- `kb/history/architecture/runs/<run-id>/signals.json`
- `kb/history/architecture/runs/<run-id>/proposals.json`
- `kb/history/architecture/runs/<run-id>/decisions.json`
- `kb/history/architecture/runs/<run-id>/execution_plan.json`
- `kb/history/architecture/runs/<run-id>/report.json`
- `kb/history/architecture/maintenance_rollup.json`
- `kb/history/architecture/proposal_queue.json`

The runner also appends one structured Architect observation to `kb/history/events.jsonl`.

## Suggested Architect Prompt

Use this as the opening prompt for an independent Architect automation:

```text
Run one KB Architect mechanism-maintenance pass for this repository.

Goals:
1. Maintain a visible execution plan with every required checkpoint.
2. Run self-preflight against system/knowledge-library/maintenance.
3. Run `python scripts/khaos_brain_update.py --architect-check --json`.
4. If apply_ready is true, use $khaos-brain-update, report, and stop this old-version run.
5. Otherwise run kb_architect.py and inspect all generated artifacts.
6. Maintain the mechanism proposal queue.
7. Start with queue hygiene: merge duplicate lanes, mark redundant items superseded, and preserve terminal items unless there is a real regression.
8. Use only Evidence, Impact, and Safety.
9. Do not use a human-review status; long-observation items stay watching.
10. Keep scope limited to system mechanisms, not card content.
11. Apply only high-evidence, high-impact or medium-impact, high-safety mechanism changes inside the narrow allowlist.
12. Use execution packets to distinguish agent-ready prompt/runbook/validation/proposal-queue work from patch/human work.
13. Generate patch plans for medium-safety changes, including local Skill prompt/workflow patches.
14. Run a validation bundle after any file changes and mark packets applied or blocked.
15. Confirm or append the final KB postflight observation.

Report:
- run id
- plan status for every checkpoint
- preflight entries retrieved
- software update gate result
- proposal status counts
- ready-for-apply and ready-for-patch proposals
- execution packet modes and blocked execution states
- changes applied
- validations run
- postflight observation status
- watching items left for long observation
```

## Validation Bundle

Architect changes are not complete after a single token check. Each applied or patched change needs enough validation for the touched mechanism:

- prompt or runbook changes: inspect required markers and run matching prompt/install tests when available
- runner or core-tooling changes: run targeted unit tests plus one smoke run when practical
- installer or automation changes: run installer tests plus `python scripts/install_codex_kb.py --check --json`
- failed validations must be fixed and rerun before a proposal can move to `applied`
