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
