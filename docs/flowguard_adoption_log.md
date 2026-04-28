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
