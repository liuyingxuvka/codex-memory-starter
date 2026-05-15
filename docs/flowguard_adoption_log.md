# Flowguard Adoption Log

## 2026-04-28 - Khaos Brain Architecture Review

- Task: use `model-first-function-flow` to review stateful maintenance, organization exchange, and software update architecture.
- Trigger: repeated scheduled workflows, locks, idempotency-sensitive exchange hashes, organization import/main movement, and update side effects.
- Model files:
  - `.flowguard/khaos_brain_function_flow.py`
  - `.flowguard/run_khaos_brain_conformance.py`
- Skipped step: formal `flowguard` package execution, because the Python module is not installed in this workspace.
- Fallback: project-local standard-library executable model plus production conformance replay.
- Commands:
  - `python .flowguard/khaos_brain_function_flow.py`: failed the intended correct model on `update_apply_gate`; the broken duplicate-upload variant failed as expected.
  - `python .flowguard/run_khaos_brain_conformance.py`: passed representative production replay checks.
  - `python -m unittest tests.test_maintenance_lanes tests.test_org_sources tests.test_software_update tests.test_org_automation`: 26 tests passed.
- Finding: after an update is marked failed, the state can still keep `update_available=true` and `user_requested=true`; the next Architect update check can directly mark it `upgrading` again without a fresh user action.
- Finding: long-running maintenance lanes release locks on normal return paths, but the full run bodies are not wrapped in `try/finally`; unexpected exceptions rely on stale-lock recovery.
- Next action: decide whether failed updates should require a fresh user prepare action before retry, and consider finally-based lock release/status handling for maintenance lanes.

## 2026-04-28 - Stateful Maintenance Fixes

- Task: implement the failed-update retry gate and finally-based maintenance lock release.
- Trigger: the previous model-first review found one concrete update-state counterexample and one lock-release reliability gap.
- Model files:
  - `.flowguard/khaos_brain_function_flow.py`
  - `.flowguard/run_khaos_brain_conformance.py`
- Skipped step: formal `flowguard` package execution, because the Python module is not installed in this workspace and the user asked not to handle that tooling gap in this fix.
- Implementation:
  - Failed updates for the same remote target now stay in `failed`, clear `user_requested`, and wait for a fresh user prepare action.
  - A newly discovered remote target after a failure becomes `available`, but still requires a fresh user prepare action before upgrade.
  - Dream, Architect, organization contribution, and organization maintenance now write failed lane status and release the active lane lock from a `finally` path on unexpected exceptions.
- Commands:
  - `python .flowguard\khaos_brain_function_flow.py`: passed the corrected model across 55,770 explored paths; the intentionally broken duplicate-upload variant still failed as expected.
  - `python .flowguard\run_khaos_brain_conformance.py`: passed production conformance replay checks.
  - `python -m unittest tests.test_software_update tests.test_maintenance_lanes tests.test_org_automation tests.test_kb_dream tests.test_kb_architect`: 44 focused tests passed.
  - `python -m unittest discover -s tests`: 218 tests passed.
  - `python scripts\kb_desktop.py --repo-root . --check`: passed with 138 entries.
  - `python scripts\install_codex_kb.py --check --json`: passed the install health checklist.
  - `git diff --check`: no whitespace errors; PowerShell reported expected CRLF normalization warnings for touched files.
- Friction point: a first mechanical attempt to wrap large maintenance functions matched the first `return` rather than the full function body. `py_compile` caught it, and the implementation was redone with function-boundary-aware wrapping.
- Next action: keep the formal flowguard package/toolchain gap as a separate follow-up.

## 2026-04-29 - Card i18n Flow Review

- Task: model card creation surfaces and zh-CN display translation cleanup.
- Trigger: the user asked whether all cards should be created only by Sleep and whether missing Chinese display text means the Sleep i18n cleanup did not run.
- Model files:
  - `.flowguard/card_i18n_flow.py`
- Commands:
  - `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"`: passed with schema version `1.0`.
  - `python .flowguard\card_i18n_flow.py`: passed the expected meta-check; strict Sleep-only creation failed, ideal Sleep with i18n cleanup passed, and the observed workflow exposed missing-i18n paths.
  - `python -m py_compile .flowguard\card_i18n_flow.py`: passed.
  - `python -m unittest tests.test_kb_i18n`: 9 tests passed.
- Finding: the current system has legitimate non-Sleep card creation surfaces, including manual candidate capture, Dream candidate creation, and organization adoption.
- Finding: Sleep candidate creation plus an applied i18n cleanup closes the zh-CN display gap in the model.
- Counterexample: `card_created_by_sleep -> sleep_i18n_cleanup_skipped -> sleep_finalized_with_missing_i18n` shows that a Sleep pass can leave English-only cards if it finalizes without applying the translation plan.
- Skipped step: production conformance replay, because this was read-only diagnosis and did not change production card or i18n code.
- Next action: treat missing zh-CN on current cards as an i18n follow-up gap, and consider making Sleep finalization/reporting fail loudly when `review-i18n` actions remain after candidate creation or semantic text changes.

## 2026-04-29 - Card Visual Merge Flow

- Status: `completed`.
- Task: model the accepted sandbox card visual refresh before merging it into the production desktop UI.
- Trigger: the user approved the sandbox card-color, title-ring, diagonal-gradient, and detail-header treatment and asked to simulate risk before landing it in the official UI.
- Model files:
  - `.flowguard/card_visual_merge_flow.py`
- Preflight command:
  - `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"`: passed with schema version `1.0`.
- Commands:
  - `python .flowguard\card_visual_merge_flow.py`: passed. The accepted merge reaches a verified state; missing sandbox cleanup is blocked; route mutation, wrapped detail pill, and vertical-gradient variants are rejected; loop and contract checks pass.
  - `python -m py_compile local_kb\desktop_app.py .flowguard\card_visual_merge_flow.py`: passed.
  - `python scripts\kb_desktop.py --repo-root . --check`: passed in English with 139 entries.
  - `python scripts\kb_desktop.py --repo-root . --language zh-CN --check`: passed in Chinese with 139 entries.
  - `python -m unittest tests.test_kb_desktop_ui`: 14 tests passed.
  - `python -m unittest discover -s tests`: 218 tests passed.
  - local screenshot QA: production overview and detail screenshots were captured under `.local/qa` and visually inspected.
  - `git diff --check`: no whitespace errors; PowerShell reported expected CRLF normalization warnings for touched files.
- Findings:
  - The accepted production merge changes only card palette selection, card/detail diagonal gradients, title ring and bold title treatment, and detail header metadata pill fitting.
  - The temporary sandbox script was removed after porting the accepted behavior into production.
  - Source body metadata in the detail window remains unchanged; only the header pill uses a compact one-line source form.
- Counterexamples:
  - Missing `remove_sandbox` before `production_check` fails to reach `production_check_passed`.
  - `bad_route_mutation` is rejected by `no_data_or_route_mutation`.
  - `bad_detail_wrap` is rejected by `accepted_detail_visual_when_merged`.
  - `bad_vertical_gradient` is rejected by `accepted_grid_visual_when_merged`.
- Skipped step: a pixel-perfect production conformance replay adapter was not created because this visual-only Tkinter change is better verified by the executable architectural model, existing UI payload checks, focused tests, and real screenshots.
- Friction point: the repository already had unrelated local flowguard/i18n and candidate-adoption files, so release staging must stay scoped.
- Next action: update README screenshots using public-safe fixture data, then perform the release audit before publishing.


## khaos-brain-software-flowguard-check-2026-04-29 - Use model-first-function-flow to inspect current Khaos Brain software without production code changes

- Project: Khaos-Brain
- Trigger reason: The user explicitly requested the updated model-first-function-flow skill; the repository has stateful retrieval, maintenance, organization exchange, i18n cleanup, software update, and UI workflows.
- Status: completed
- Skill decision: used_flowguard
- Started: 2026-04-29T21:22:42+00:00
- Ended: 2026-04-29T21:22:42+00:00
- Duration seconds: 0.000
- Commands OK: True

### Model Files
- .flowguard/khaos_brain_function_flow.py
- .flowguard/card_i18n_flow.py
- .flowguard/card_visual_merge_flow.py
- .flowguard/run_khaos_brain_conformance.py

### Commands
- OK (0.000s): `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"` - flowguard schema version 1.0 is importable.
- OK (0.000s): `python .flowguard\khaos_brain_function_flow.py` - Correct model passed 55,770 explored paths; intentionally broken duplicate-upload variant failed as expected, but the report still says flowguard_package_available=false.
- OK (0.000s): `python .flowguard\card_i18n_flow.py` - Ideal Sleep i18n cleanup passed; observed workflow still exposes missing-i18n paths when cleanup is skipped.
- OK (0.000s): `python .flowguard\card_visual_merge_flow.py` - Accepted visual merge path, loop review, and contract checks passed; known bad variants were rejected.
- OK (0.000s): `python .flowguard\run_khaos_brain_conformance.py` - Production replay passed lane lock, organization main-only download, and update gate expectations.
- OK (0.000s): `python -m py_compile .flowguard\khaos_brain_function_flow.py .flowguard\card_i18n_flow.py .flowguard\card_visual_merge_flow.py .flowguard\run_khaos_brain_conformance.py` - Flowguard model and replay files compiled.
- OK (0.000s): `python -m unittest tests.test_kb_i18n tests.test_maintenance_lanes tests.test_org_sources tests.test_software_update tests.test_org_automation tests.test_kb_desktop_ui` - 56 focused tests passed.
- OK (0.000s): `python scripts\install_codex_kb.py --check --json` - Install health checklist passed.
- OK (0.000s): `python scripts\kb_desktop.py --repo-root . --check` - Desktop data check passed in English with 139 entries.
- OK (0.000s): `python scripts\kb_desktop.py --repo-root . --language zh-CN --check` - Desktop data check passed in Chinese with 139 entries.
- OK (0.000s): `current i18n gap inventory` - All 139 entries have complete zh-CN card fields; 16 route segments lack zh-CN display labels.
- OK (0.000s): `python -m unittest discover -s tests` - 218 tests passed.
- OK (0.000s): `git diff --check` - No whitespace errors; Git reported existing CRLF-normalization warnings for flowguard logs.

### Findings
- No immediate production regression was found in tests, install health, desktop payload checks, or existing conformance replay.
- The main stateful architecture model is stale relative to the updated skill: flowguard is now importable, but .flowguard/khaos_brain_function_flow.py still uses a custom standard-library explorer and reports flowguard_package_available=false.
- The i18n model still shows a future Sleep workflow risk: a Sleep pass can finalize after card creation or semantic text changes without applying the zh-CN cleanup plan.
- Current card text i18n is clean, but 16 route segments still rely on English fallback in zh-CN display labels.

### Counterexamples
- card_created_by_sleep -> sleep_i18n_cleanup_skipped -> sleep_finalized_with_missing_i18n remains a modeled risk path.
- Strict all-card-creation-by-Sleep is false because manual candidate capture, Dream candidate creation, and organization adoption are legitimate card creation surfaces.

### Friction Points
- The updated skill correctly requires real flowguard import preflight, but the older Khaos main model still contains stale fallback wording and metadata from before flowguard was installed.
- The skill is very broad for read-only inspection: it says to start an in_progress adoption log before modeling, but real review often discovers whether a new model/log is needed only after inspecting existing local models.
- Scenario exact-sequence reports expose ok as null in some compact summaries, so reporting has to rely on labels unless the skill or helper offers a normalized scenario status wrapper.

### Skipped Steps
- No production code was changed because the user asked for inspection and discussion before fixes.
- No new production conformance replay adapter was added for route-segment i18n labels because this was a read-only review and the gap is already surfaced by current i18n maintenance tooling.

### Next Actions
- Discuss whether to migrate .flowguard/khaos_brain_function_flow.py from the custom fallback explorer to the real flowguard Workflow/Explorer API now that schema 1.0 is available.
- Consider making Sleep completion mark the run incomplete or failed-loudly when review-i18n actions remain after candidate creation or semantic text changes.
- Add zh-CN display labels for the 16 missing route segments or leave them as a normal proposal-only maintenance target.


## khaos-brain-planned-maintenance-flow-simulation-2026-04-29 - Simulate the planned Sleep final i18n cleanup, Architect report rollup, content-boundary, and install-sync changes before production edits

- Project: Khaos-Brain
- Trigger reason: The planned KB-system changes affect Sleep finalization, route/card display i18n, Architect rollup, release boundaries, and installed-skill synchronization.
- Status: completed
- Skill decision: used_flowguard
- Started: 2026-04-29T21:46:28+00:00
- Ended: 2026-04-29T21:46:28+00:00
- Duration seconds: 0.000
- Commands OK: True

### Model Files
- .flowguard/khaos_brain_planned_maintenance_flow.py
- .flowguard/card_i18n_flow.py

### Commands
- OK (0.000s): `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"` - flowguard schema version 1.0 is importable.
- OK (0.000s): `python .flowguard\khaos_brain_planned_maintenance_flow.py` - Accepted plan reached clean release readiness; missing final i18n, legacy duplicate i18n, incomplete Architect rollup, stale install, and missing boundary variants were blocked or rejected.
- OK (0.000s): `python -m py_compile .flowguard\khaos_brain_planned_maintenance_flow.py` - Plan simulation model compiled.
- OK (0.000s): `python .flowguard\card_i18n_flow.py` - Existing i18n model still exposes the old missing-final-cleanup risk; the ideal cleanup path passes.
- OK (0.000s): `python -m unittest tests.test_kb_i18n tests.test_kb_architect tests.test_codex_install tests.test_kb_consolidate_apply_worker1` - 36 focused tests passed.
- OK (0.000s): `git diff --check` - No whitespace errors; Git reported existing CRLF-normalization warnings for flowguard logs.

### Findings
- The planned flow is internally consistent when Sleep owns one final AI zh-CN cleanup pass for both card text and route display text.
- The old separate translation step should be disabled rather than duplicated; the model rejects a variant where legacy i18n still applies translations mid-run.
- Architect can safely own the system-readable maintenance rollup if it refuses to mark the rollup complete until Sleep, Dream, FlowGuard, organization, and install reports are present.
- Release/update readiness should remain blocked until content boundaries are reviewed and repository-managed skill changes have been installed and checked.

### Counterexamples
- sleep_content_change -> sleep_finish is blocked as sleep_finish_blocked_missing_i18n.
- bad_legacy_i18n_duplicate violates no_duplicate_translation_work.
- bad_architect_summary_without_sources violates architect_complete_requires_sources.
- bad_release_without_boundary violates release_requires_all_gates.

### Friction Points
- Long complete workflows should be verified with exact sequences; bounded exhaustive exploration should only require labels reachable in short paths to avoid false reachability failures.

### Skipped Steps
- No production code was changed; this task was simulation-only before implementation.

### Next Actions
- Implement the plan in small batches: Sleep final cleanup first, then Architect rollup, then content-boundary/install-sync hardening.
- Keep the new plan model as a regression guard while implementing the production changes.


## kb-architect-20260501-lock-aware-maintenance-pass - Run KB Architect maintenance with lock-aware runner recovery and queue hygiene

- Project: Khaos-Brain
- Trigger reason: KB Architect is a stateful maintenance lane with shared locks, update gates, proposal queue state, and system rollup side effects.
- Status: completed
- Skill decision: used_flowguard
- Started: 2026-05-01T12:44:08+00:00
- Ended: 2026-05-01T12:44:08+00:00
- Duration seconds: 0.000
- Commands OK: True

### Model Files
- .flowguard/run_khaos_brain_conformance.py

### Commands
- OK (0.000s): `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"`
- OK (0.000s): `python .flowguard\run_khaos_brain_conformance.py`
- OK (0.000s): `python -m unittest tests.test_kb_architect`
- OK (0.000s): `python -m unittest tests.test_maintenance_lanes`

### Findings
- The live runner initially self-blocked because an outer lock used a different run id than kb_architect.py; rerunning with the same run id made lock acquisition reentrant.
- The maintained queue had no sandbox-ready ready-for-apply packet; seven medium-safety proposals remain ready-for-patch.

### Counterexamples
- outer lock run_id A -> runner generated run_id B -> same-lane lock wait loop until timeout

### Friction Points
- none recorded

### Skipped Steps
- No new FlowGuard model was created because the existing conformance replay covers lane mutual exclusion and update-gate expectations for this maintenance pass.

### Next Actions
- Architect automation should pass the acquired lock run id to the runner or let the runner own lock acquisition to avoid self-lock stalls.


## kb-architect-20260502-lock-aware-maintenance-pass - Run KB Architect maintenance with lock-aware runner ownership, queue hygiene, and rollup validation

- Project: Khaos-Brain
- Trigger reason: KB Architect is a stateful maintenance lane with shared locks, update gates, proposal queue state, postflight observations, and system rollup side effects.
- Status: attention-needed
- Skill decision: used_flowguard
- Started: 2026-05-02T12:02:47+00:00
- Ended: 2026-05-02T12:05:02+00:00
- Duration seconds: 0.000
- Commands OK: False

### Model Files
- .flowguard/run_khaos_brain_conformance.py

### Commands
- OK (0.000s): `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"` - flowguard schema version 1.0 is importable.
- OK (0.000s): `python .flowguard\run_khaos_brain_conformance.py` - Conformance replay passed local-lane mutual exclusion, organization-lane independence, organization download boundary, update apply gate, and failed-update no-auto-retry expectations.
- OK (0.000s): `python -m unittest tests.test_kb_architect` - 10 Architect tests passed.
- OK (0.000s): `python -m unittest tests.test_maintenance_lanes` - 7 maintenance-lane tests passed.
- FAIL (0.000s): `python scripts/install_codex_kb.py --check --json` - Install check failed because kb-org-contribute and kb-org-maintenance automations are not active/policy-complete.

### Findings
- The Architect runner owned the local-maintenance lock directly, avoiding the prior same-lane self-lock mismatch.
- No sandbox-ready ready-for-apply packet was available; nine medium-safety proposals remain ready-for-patch.
- The system rollup contains the required source reports but remains attention-needed because content-boundary review is required and install_sync_ok is false for organization automations.

### Counterexamples
- none recorded

### Friction Points
- The installer check exposes organization automation spec drift, but this Architect pass had no selected apply packet and should leave the fix as patch-plan work.

### Skipped Steps
- No new FlowGuard model was created because the existing conformance replay still covers the lock and update-gate risks exercised by this pass.
- No production mechanism files were edited and no sandbox trial was selected.

### Next Actions
- Address organization automation install-sync drift through the existing ready-for-patch organization automation lane rather than ad-hoc direct edits.


## kb-architect-20260504-lock-aware-maintenance-pass - Run KB Architect mechanism maintenance with update gate, queue hygiene, rollup validation, and no sandbox trial

- Project: Khaos-Brain
- Trigger reason: KB Architect is a stateful maintenance lane with shared locks, update gates, proposal queue state, sandbox closure, postflight observations, and system rollup side effects.
- Status: attention-needed
- Skill decision: used_flowguard
- Started: 2026-05-04T12:04:40Z
- Ended: 2026-05-04T12:08:53Z
- Commands OK: False

### Model Files
- .flowguard/run_khaos_brain_conformance.py

### Commands
- OK: `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"` - flowguard schema version 1.0 is importable.
- OK: `python .flowguard\run_khaos_brain_conformance.py` - local-lane locks, organization independence, organization download boundary, update apply gate, and failed-update no-auto-retry expectations passed.
- OK: `python -m unittest tests.test_kb_architect tests.test_maintenance_lanes` - 17 focused tests passed after queue and rollup updates.
- FAIL: `python scripts\install_codex_kb.py --check --json` - automation TOML policy metadata is still missing for core and organization automations.

### Findings
- The Architect runner acquired and released the shared local-maintenance lock directly; Sleep and Dream were completed.
- Software update gate returned `no-update` with `apply_ready=false`.
- Queue hygiene maintained 37 proposals: 2 applied, 11 ready-for-patch, 8 superseded, 8 watching, and 8 rejected.
- No ready-for-apply or sandbox-ready packet was selected.
- The rollup includes Sleep, Dream, Architect, FlowGuard, organization, content-boundary, and install-sync sources, but remains attention-needed because content-boundary review is required and install_sync_ok=false.

### Counterexamples
- none recorded

### Friction Points
- Installer check now flags policy metadata drift across core and organization automation specs; this pass left it as patch-plan/watch work because no selected apply packet authorized direct automation edits.

### Skipped Steps
- No new FlowGuard model was created because the existing conformance replay covers this pass's lock and update-gate risks.
- No sandbox trial was run because `sandbox_trial_selection.json` reported no sandbox-ready ready-for-apply packet.
- `git diff --check` was run separately and reported only existing CRLF normalization warnings.

### Next Actions
- Address automation policy metadata drift through the existing ready-for-patch install/automation lanes instead of ad-hoc direct edits.
- Continue leaving broad Skill and automation mechanism work as patch-plan until a packet becomes sandbox-ready with explicit write boundaries.

## kb-org-maintenance-20260504-lane-status-completion-fix - Run organization KB maintenance and fix stale organization lane status

- Project: Khaos-Brain
- Trigger reason: Organization maintenance is a stateful automation lane; post-run validation found stale running status despite lock release.
- Status: completed
- Skill decision: used_flowguard
- Started: 2026-05-04T13:37:06Z
- Ended: 2026-05-04T13:43:39Z

### Model Files
- .flowguard/khaos_brain_function_flow.py
- .flowguard/run_khaos_brain_conformance.py

### Commands
- OK: `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"` - flowguard schema version 1.0 is importable.
- OK: `python .flowguard\run_khaos_brain_conformance.py` - conformance replay passed lane, organization-download, and update-gate expectations.
- OK: `python .flowguard\khaos_brain_function_flow.py` - correct model passed 55,770 traces with released-lock status invariant; broken duplicate-upload variant failed.
- OK: `python -m unittest tests.test_org_automation tests.test_org_sources tests.test_maintenance_lanes` - focused org/lane tests passed.
- OK: `python scripts\kb_org_maintainer.py --automation` - rerun completed, selected no actions, recorded postflight, released lock, and left lane status completed.
- OK: `python -m unittest discover -s tests` - 220 tests passed.
- OK: `git diff --check` - no whitespace errors; CRLF normalization warnings only.
- OK: `python scripts\kb_org_check.py --org-root .local\organization_sources\khaos-org-kb-sandbox` - organization checker passed with no errors or warnings.

### Findings
- Successful organization contribution and maintenance paths wrote `running` status but did not write `completed` before returning.
- The fix writes `completed` or `failed` before lock release on non-exception organization automation paths.
- The stateful model now checks that released locks do not leave `running` status.
- The older model metadata now reports the installed flowguard schema version while keeping its project-local explorer.

### Counterexamples
- `successful organization maintenance -> lock released -> lane status remains running` was observed in the first live pass and resolved by the patch.

### Skipped Steps
- No maintenance branch or PR was created because the organization Sleep decision set selected no apply actions.

### Next Actions
- Keep lane-status checks in future maintenance finalization alongside lock-release checks.
- Consider a later migration of `.flowguard/khaos_brain_function_flow.py` to the real flowguard Workflow/Explorer API.


## kb-architect-20260505-lock-aware-maintenance-pass - Run KB Architect mechanism maintenance with update gate, queue hygiene, rollup validation, and no sandbox trial

- Project: Khaos-Brain
- Trigger reason: KB Architect is a stateful maintenance lane with shared locks, update gates, proposal queue state, sandbox closure, postflight observations, and system rollup side effects.
- Status: completed
- Skill decision: used_flowguard
- Started: 2026-05-05T12:08:06+00:00
- Ended: 2026-05-05T12:08:06+00:00
- Duration seconds: 0.000
- Commands OK: False

### Model Files
- .flowguard/run_khaos_brain_conformance.py

### Commands
- OK (0.000s): `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"`
- OK (0.000s): `python .flowguard\run_khaos_brain_conformance.py`
- OK (0.000s): `python -m unittest tests.test_kb_architect`
- FAIL (0.000s): `python scripts\install_codex_kb.py --check --json`

### Findings
- The Architect runner acquired and released the shared local-maintenance lock directly; Sleep and Dream were completed and no blocking lane was active.
- Software update gate returned no-update with apply_ready=false.
- Queue hygiene maintained 37 proposals with 0 ready-for-apply and 0 sandbox-ready packets; 11 medium-safety proposals remain ready-for-patch.
- The maintenance rollup contains Sleep, Dream, Architect, FlowGuard, organization, content-boundary, and install-sync sources, but stays attention-needed because content-boundary review is required and install_sync_ok=false.

### Counterexamples
- none recorded

### Friction Points
- Installer check still flags automation policy metadata drift; Architect left it as patch-plan work because no selected apply packet authorized direct automation edits.

### Skipped Steps
- No new FlowGuard model was created because existing conformance replay covers the lock and update-gate risks for this pass.
- No sandbox trial was run because sandbox_trial_selection.json reported no sandbox-ready ready-for-apply packet.

### Next Actions
- Address automation policy metadata drift through existing ready-for-patch install/automation lanes instead of ad-hoc direct edits.


## kb-architect-20260506-lock-aware-maintenance-pass - Run KB Architect mechanism maintenance with update gate, queue hygiene, rollup validation, and no sandbox trial

- Project: Khaos-Brain
- Trigger reason: KB Architect is a stateful maintenance lane with shared locks, update gates, proposal queue state, sandbox closure, postflight observations, and system rollup side effects.
- Status: attention-needed
- Skill decision: used_flowguard
- Started: 2026-05-06T14:04:26+02:00
- Ended: 2026-05-06T14:07:58+02:00
- Commands OK: False

### Model Files
- .flowguard/run_khaos_brain_conformance.py

### Commands
- OK: `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"` - flowguard schema version 1.0 is importable.
- OK: `python .flowguard\run_khaos_brain_conformance.py` - conformance replay passed lane, organization-download, and update-gate expectations.
- OK: `python -m unittest tests.test_kb_architect` - 10 focused Architect tests passed.
- FAIL: `python scripts\install_codex_kb.py --check --json` - install sync remains attention-needed because automation metadata/policy checks fail.
- OK: `git diff --check` - no whitespace errors; CRLF normalization warnings only on already-dirty tracked files.
- OK: `python -m unittest tests.test_codex_install` - 9 installer tests passed.

### Findings
- The Architect runner acquired and released the shared local-maintenance lock; Sleep and Dream were completed and no blocking lane was active.
- Software update gate returned no-update with `apply_ready=false` and no UI process running.
- Queue hygiene maintained 38 proposals: 2 applied, 12 ready-for-patch, 8 superseded, 8 watching, and 8 rejected.
- No ready-for-apply or sandbox-ready packet was selected, so no source mechanism patch or sandbox merge was applied.
- The maintenance rollup contains Sleep, Dream, Architect, FlowGuard, organization, content-boundary, and install-sync surfaces, but stays attention-needed because content-boundary review is required, `install_sync_ok=false`, and organization contribute remains running.

### Counterexamples
- none recorded

### Friction Points
- Installer check still flags automation policy metadata drift and inactive organization automations; Architect kept this in ready-for-patch/watch lanes because no sandbox-ready apply packet authorized direct automation edits.

### Skipped Steps
- No new FlowGuard model was created because existing conformance replay covers the lock and update-gate risks for this pass.
- No sandbox trial was run because `sandbox_trial_selection.json` reported no sandbox-ready ready-for-apply packet.
- No source mechanism patch was applied because the current run selected no sandbox-ready ready-for-apply packet.

### Next Actions
- Address automation policy metadata drift through existing ready-for-patch install/automation lanes instead of ad-hoc direct edits.
- Resolve stale organization contribute lane status through the appropriate organization maintenance mechanism.


## khaos-brain-governance-minimal-fix-20260507 - Apply minimal governance closure fixes after FlowGuard simulation

- Project: Khaos-Brain
- Trigger reason: The user requested that the upgraded governance FlowGuard model and all existing models accept the minimal fix before code changes, then asked to update the local install, local Git state, and GitHub state.
- Status: completed
- Skill decision: used_flowguard
- Started: 2026-05-07T17:22:40+02:00
- Ended: 2026-05-07T17:55:12+02:00
- Commands OK: True

### Model Files
- .flowguard/khaos_brain_governance_flow.py
- .flowguard/khaos_brain_function_flow.py
- .flowguard/card_i18n_flow.py
- .flowguard/card_visual_merge_flow.py
- .flowguard/khaos_brain_planned_maintenance_flow.py
- .flowguard/run_khaos_brain_conformance.py

### Commands
- OK: `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"` - flowguard schema version 1.0 is importable.
- OK: `python .flowguard\khaos_brain_governance_flow.py --live` - abstract governance checks pass and live projection reports finding_count 0 after the fixes.
- OK: `python .flowguard\card_i18n_flow.py`
- OK: `python .flowguard\card_visual_merge_flow.py`
- OK: `python .flowguard\khaos_brain_function_flow.py`
- OK: `python .flowguard\khaos_brain_planned_maintenance_flow.py`
- OK: `python .flowguard\run_khaos_brain_conformance.py`
- OK: `python scripts\install_codex_kb.py --json`
- OK: `python scripts\install_codex_kb.py --check --json`
- OK: `python -m unittest tests.test_kb_architect tests.test_codex_install tests.test_maintenance_lanes tests.test_software_update tests.test_org_automation tests.test_org_sources tests.test_kb_i18n tests.test_kb_maintenance_decisions tests.test_kb_taxonomy_worker1`
- OK: `python scripts\kb_desktop.py --repo-root . --check`
- OK: `python scripts\kb_desktop.py --repo-root . --language zh-CN --check`
- OK: `python -m unittest discover -s tests` - 224 tests passed.
- OK: `git diff --check`

### Findings
- Sleep now scans the full action surface but exposes a bounded immediate review batch with deferred counts, so observations are not dropped when review throughput is limited.
- Dream scenario-replay handoffs are eligible for Sleep review, closing the strong/moderate Dream-to-Sleep handoff gap.
- Architect ready-for-patch debt is considered closed only when there is an explicit execution outlet, such as a patch packet/application, not by silently deleting the work.
- Route parsing now normalizes known aliases and dotted route families before governance review and card/event routing.
- Installer checks now distinguish user-paused organization automations from real automation drift.
- Stale lane statuses without live locks are reconciled into explicit stale status instead of remaining as misleading running lanes.

### Counterexamples
- The governance model still rejects unreviewed candidate backlog, trusted promotion without review, dropped/unreviewed Dream handoffs, weak Dream promotion, Architect patch debt without outlet, route drift before card creation, real install drift, unexpected organization pause, and stale running lanes.

### Friction Points
- The full test run exposed one compatibility expectation still using the old `predictive-kb` route; the test was updated to assert the canonical `system/knowledge-library` route.

### Skipped Steps
- No KOSpring production code was changed; this repair stayed inside Khaos Brain / FlowGuard / install maintenance mechanisms.

### Next Actions
- Use the live governance projection as the release gate for future KB maintenance mechanism changes.


## khaos-brain-governance-flowguard-model - Add governance closure model for mature KB maintenance risks

- Project: Khaos-Brain
- Trigger reason: The existing models covered lane/update/i18n mechanics, but not candidate backlog closure, Dream/Sleep handoff closure, Architect ready-for-patch execution outlets, route drift, or manual-pause health semantics.
- Status: completed-with-live-findings
- Skill decision: used_flowguard
- Started: 2026-05-07T17:22:40+02:00
- Ended: 2026-05-07T17:22:40+02:00
- Commands OK: False, because the live projection intentionally exits non-zero when current repository reports contain model findings.

### Model Files
- .flowguard/khaos_brain_governance_flow.py

### Commands
- OK: `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"` - flowguard schema version 1.0 is importable.
- OK: `python -m py_compile .flowguard\khaos_brain_governance_flow.py`
- OK: `python .flowguard\khaos_brain_governance_flow.py --abstract-only` - accepted and user-paused organization sequences pass; all modeled bad paths are rejected.
- FINDINGS: `python .flowguard\khaos_brain_governance_flow.py --live` - abstract scenarios pass, but live repository projection reports governance issues.

### Findings
- candidate_backlog_pressure: 183 candidate cards versus 2 public and 1 private cards.
- sleep_review_pressure: latest Sleep run `kb-sleep-20260507T100105Z` produced 1446 candidate actions and 480 apply-eligible actions.
- dream_sleep_handoff_open: latest Dream run `kb-dream-20260507T110225Z` has 4 handoffs, 3 review-ready handoffs, and 3 strong/moderate handoffs.
- architect_execution_outlet_gap: 12 ready-for-patch proposals exist, with 0 ready-for-apply and 0 sandbox-ready packets.
- route_drift_pressure: 478 blank-route history events, 12 root-direct cards, 5 dotted card routes, and undeclared families such as `job-hunter`, `flowpilot`, `product`, and `predictive-kb`.
- install_policy_metadata_drift: maintenance rollup install report still has 19 issues.
- stale_running_lane_without_lock: `kb-org-contribute` lane status says running without the corresponding lock.

### Allowed Notes
- User-paused organization automations are explicitly modeled as allowed local operating mode, not as a failure by themselves: `kb-org-contribute` and `kb-org-maintenance`.

### Counterexamples
- Abstract counterexamples are the intended bad-path scenarios: unreviewed candidate backlog, promotion without review, unreviewed or dropped Dream handoffs, weak Dream promotion, Architect ready-for-patch without outlet, route drift before card creation or finalization, release readiness with real health drift, unexpected org pause, and stale lane readiness.

### Friction Points
- FlowGuard invariants are evaluated over intermediate states, so governance-debt invariants needed an explicit terminal state (`finalize_governance` or `mark_release_ready`) to avoid treating normal in-progress debt as failure.

### Skipped Steps
- No Khaos Brain/KOSpring production code was changed.
- Existing older FlowGuard models were not refactored; the new model was added as an isolated governance projection.

### Next Actions
- Use the new governance model as the preflight gate before changing Khaos Brain maintenance mechanics.
- Address model findings through explicit future changes rather than treating live projection failure as a model failure.


## kb-architect-20260507-lock-aware-maintenance-pass - Run KB Architect mechanism maintenance with update gate, queue hygiene, rollup validation, and no sandbox trial

- Project: Khaos-Brain
- Trigger reason: KB Architect is a stateful maintenance lane with shared locks, update gates, proposal queue state, sandbox closure, postflight observations, and system rollup side effects.
- Status: completed
- Skill decision: used_flowguard
- Started: 2026-05-07T12:07:17+00:00
- Ended: 2026-05-07T12:07:17+00:00
- Duration seconds: 0.000
- Commands OK: False

### Model Files
- .flowguard/run_khaos_brain_conformance.py

### Commands
- OK (0.000s): `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"`
- OK (0.000s): `python .flowguard\run_khaos_brain_conformance.py`
- OK (0.000s): `python -m unittest tests.test_kb_architect`
- OK (0.000s): `python -m unittest tests.test_codex_install`
- OK (0.000s): `git diff --check`
- FAIL (0.000s): `python scripts\install_codex_kb.py --check --json`

### Findings
- Architect runner acquired and released the shared local-maintenance lock; Sleep and Dream were completed and no blocking lane was active.
- Software update gate returned no-update with apply_ready=false and UI process count 0.
- Queue hygiene maintained 38 proposals: 2 applied, 12 ready-for-patch, 8 rejected, 8 superseded, and 8 watching; no ready-for-apply or sandbox-ready packet was selected.
- Maintenance rollup contains Sleep, Dream, Architect, FlowGuard, organization, content-boundary, and install-sync surfaces, but remains attention-needed because content-boundary review is required, install_sync_ok=false, and organization contribute remains running.

### Counterexamples
- none recorded

### Friction Points
- Install check still flags automation policy metadata drift and inactive organization automations; Architect kept this in ready-for-patch/watch lanes because no sandbox-ready apply packet authorized direct automation edits.

### Skipped Steps
- No new FlowGuard model was created because existing conformance replay covers the lock and update-gate risks for this pass.
- No sandbox trial was run because sandbox_trial_selection.json reported no sandbox-ready ready-for-apply packet.
- No source mechanism patch was applied because the current run selected no sandbox-ready ready-for-apply packet.

### Next Actions
- Address automation policy metadata drift through existing ready-for-patch install/automation lanes instead of ad-hoc direct edits.
- Resolve stale organization contribute lane status through the appropriate organization maintenance mechanism.

## kb-architect-20260513-lock-aware-maintenance-pass - Run KB Architect mechanism maintenance with update gate, queue hygiene, rollup validation, and no sandbox trial

- Project: Khaos-Brain
- Trigger reason: KB Architect is a stateful maintenance lane with shared locks, update gates, proposal queue state, sandbox closure, postflight observations, and system rollup side effects.
- Status: attention-needed
- Skill decision: used_flowguard
- Started: 2026-05-13T12:05:02Z
- Ended: 2026-05-13T12:09:56Z
- Commands OK: False, because the governance live projection intentionally reported one open Sleep handoff finding.

### Model Files
- .flowguard/run_khaos_brain_conformance.py
- .flowguard/khaos_brain_governance_flow.py

### Commands
- OK: `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"` - flowguard schema version 1.0 is importable.
- OK: `python .flowguard\run_khaos_brain_conformance.py` - conformance replay passed lane lock, organization download boundary, update gate, and failed-update no-auto-retry expectations.
- FINDINGS: `python .flowguard\khaos_brain_governance_flow.py --live` - abstract governance checks passed, but live projection reported one open Dream-to-Sleep handoff finding.
- OK: `python -m unittest tests.test_kb_architect tests.test_maintenance_lanes` - 18 focused tests passed.
- OK: `python scripts\install_codex_kb.py --check --json` - install health checklist passed.
- OK: `git diff --check` - no whitespace errors; Git reported an existing CRLF normalization warning for `DREAM_PROMPT.md`.

### Findings
- The Architect runner acquired and released the shared local-maintenance lock; Sleep and Dream were completed and no blocking lane was active.
- Software update gate returned no-update with `apply_ready=false`, current/latest version `0.4.7`, and UI process count 0.
- Queue hygiene maintained 41 proposals: 3 applied, 12 ready-for-patch, 10 rejected, 8 superseded, and 8 watching; no ready-for-apply or sandbox-ready packet was selected.
- The maintenance rollup contains Sleep, Dream, Architect, FlowGuard, organization, content-boundary, and install-sync surfaces, but remains attention-needed because content-boundary review is required.
- Install sync is now healthy in the rollup; public-release readiness is still blocked by content-boundary review scopes.

### Counterexamples
- none recorded by this Architect pass.

### Friction Points
- Governance live projection still reports open strong/moderate Dream handoffs from `kb-dream-20260513T110320Z`; this is a Sleep-review queue signal, not an Architect mechanism patch authorization.

### Skipped Steps
- No new FlowGuard model was created because existing conformance replay covers lock and update-gate risks for this pass.
- No sandbox trial was run because `sandbox_trial_selection.json` reported no sandbox-ready ready-for-apply packet.
- No source mechanism patch was applied because the current run selected no sandbox-ready packet.

### Next Actions
- Let Sleep review or explicitly watch the three strong/moderate Dream handoffs from the latest Dream run.
- Keep the 12 medium-safety Architect items as patch-plan work until a packet has a narrow execution outlet.


## kb-postflight-priority-20260514 - Prioritize Codex mistakes and corrections in predictive KB postflight prompts

- Project: Khaos-Brain
- Trigger reason: The KB postflight workflow changes prompt and installer behavior; FlowGuard modeled the decision rule so mistake/correction evidence outranks success evidence while success observations remain allowed.
- Status: completed
- Skill decision: used_flowguard
- Started: 2026-05-14T08:25:06+00:00
- Ended: 2026-05-14T08:25:06+00:00
- Duration seconds: 0.000
- Commands OK: True

### Model Files
- .flowguard\kb_postflight_priority_flow.py

### Commands
- OK (0.000s): `python .flowguard\kb_postflight_priority_flow.py`
- OK (0.000s): `python -m py_compile .flowguard\kb_postflight_priority_flow.py local_kb\install.py`
- OK (0.000s): `python -m unittest tests.test_codex_install`
- OK (0.000s): `python scripts\install_codex_kb.py --json`
- OK (0.000s): `python scripts\install_codex_kb.py --check --json`

### Findings
- Mistake, weak-path, missed-instruction, failed-validation, tool/skill-misuse, user-correction, and correction episode evidence is now explicit highest-priority KB postflight evidence.
- Successful reusable observations remain allowed and are not suppressed by mistake-first priority.

### Counterexamples
- none recorded

### Friction Points
- none recorded

### Skipped Steps
- none recorded

### Next Actions
- Keep the mistake-priority install checklist as part of strong_session_defaults for future machine setup.


## kb-sleep-generalization-20260515 - Add scoped generalization review to Sleep maintenance

- Project: Khaos-Brain
- Trigger reason: Sleep maintenance changes card-candidate and semantic-review decision behavior, including same-project chronology, cross-project evidence, project-local boundaries, and skill-specific boundaries.
- Status: completed
- Skill decision: used_flowguard
- Started: 2026-05-15T23:49:32+02:00
- Ended: 2026-05-15T23:55:00+02:00
- Commands OK: True

### Model Files
- .flowguard/kb_sleep_generalization_flow.py

### Commands
- OK: `python -c "import flowguard; print(flowguard.SCHEMA_VERSION)"` - flowguard schema version 1.0 is importable.
- OK: `python .flowguard\kb_sleep_generalization_flow.py` - accepted Sleep generalization sequences passed and bad variants were rejected.
- OK: `python -m py_compile .flowguard\kb_sleep_generalization_flow.py local_kb\consolidate_suggestions.py local_kb\consolidate_apply.py local_kb\semantic_review.py` - model and touched Python modules compiled.
- OK: `python -m unittest tests.test_kb_consolidate_action_stubs_worker1 tests.test_kb_semantic_review tests.test_kb_consolidate_apply_worker1 tests.test_kb_maintenance_decisions` - 31 focused tests passed.

### Findings
- Sleep now models `project-local`, `skill-specific`, `single-project-generalizable`, `cross-project-general`, and `insufficient-evidence` as distinct outcomes.
- Same-project repetition is modeled as chronology evidence, not cross-project proof.
- Skill-specific evidence is modeled as a valid bounded rule and should retain the Skill/plugin/tool boundary when future invocation depends on it.
- Semantic review apply is blocked when a card-surface decision lacks scope assessment.

### Counterexamples
- same-project evidence treated as cross-project evidence
- project-local evidence rewritten as a general rule
- skill-specific evidence rewritten as a capability-independent rule
- old project-shaped reusable card left without a rewrite-as-general-rule review

### Friction Points
- none recorded

### Skipped Steps
- Full regression and install sync are tracked in the OpenSpec task list and release gate rather than this initial model note.

### Next Actions
- Run the broader regression suite and install sync before release.
