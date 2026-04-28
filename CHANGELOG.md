# Changelog

## v0.4.4 - 2026-04-28

- Fixed software update coordination so a failed update cannot be retried automatically by Architect until the user prepares the update again.
- Kept failed updates clickable in the desktop update badge so the user can deliberately re-prepare the same target, while new remote targets return to the available-update state.
- Hardened Dream, Architect, organization contribution, and organization maintenance runners so unexpected exceptions write failed lane status and release maintenance locks immediately.
- Added model-first function-flow artifacts and conformance replay coverage for update retry gates, maintenance lock cleanup, and organization exchange boundaries.

## v0.4.3 - 2026-04-27

- Fixed installer health checks on non-Windows CI runners so Windows-only Codex shell shims are not required when the installer did not create them.
- Added regression coverage for non-Windows partial shell-tool installs while preserving the stricter Windows local-machine check.

## v0.4.2 - 2026-04-27

- Fixed GitHub Actions coverage so retrieval, taxonomy, and desktop UI tests use deterministic fixture KB data instead of depending on ignored local candidate cards.
- Kept release validation reproducible on clean checkouts while preserving the public repository boundary that excludes live `kb/candidates` and `kb/history` data.

## v0.4.1 - 2026-04-27

- Added public repository hygiene files, including the MIT license, contribution guide, and a GitHub Actions workflow that runs tests plus installer and desktop checks.
- Tightened Sleep, Dream, and Architect reporting so maintenance runs expose clearer status, selected work, sandbox-style validation, and final application results.
- Expanded Dream experiment handling with bounded scenario-replay validation and richer execution records.
- Refined organization contribution and maintenance checks for the `imports` / `main` organization-KB layout and direct maintenance audit summaries.
- Clarified README positioning so the project describes its automatic local maintenance rhythm without overstating autonomy.

## v0.4.0 - 2026-04-27

- Added a shared maintenance-agent worldview so Sleep, Dream, Architect, and organization maintenance receive clearer role boundaries, evidence standards, sandbox expectations, and human-review criteria.
- Expanded local Sleep/Dream/Architect behavior with stronger prompt framing, real sandbox experiment handling, Architect sandbox-ready execution packets, rollback-oriented maintenance traces, and broader validation coverage.
- Added core maintenance lane locks so local Sleep, Dream, and Architect wait on one another, while organization contribution and organization maintenance share a separate organization-maintenance lock.
- Upgraded organization contribution and maintenance into a fuller exchange loop: contribution syncs first, avoids re-uploading already exchanged hashes, prepares import branches, and organization maintenance directly applies exact selected Sleep-style cleanup actions with audit records.
- Updated global predictive-KB preflight defaults so long mixed tasks add phase-change KB checkpoints before substantially different work such as edits, packaging, automation, organization-KB work, GitHub publishing, or public release work.
- Refreshed installer checks, repository-managed Skills, organization GitHub workflow checks, and tests so new machines inherit the same maintenance, organization, and preflight behavior after bootstrap.

## v0.3.0 - 2026-04-26

- Added the repository-managed `khaos-brain-update` Skill and installer/check coverage so software updates can be applied through the same Codex Skill distribution path as maintenance and organization skills.
- Added `.local/khaos_brain_update_state.json` software-update coordination, with desktop UI version/update capsules, prepared-update toggling, and launch blocking while an update is in progress.
- Added an Architect update gate that checks remote version state and only invokes `$khaos-brain-update` after the user has prepared the update and the desktop UI is closed.
- Clarified Sleep vs Architect ownership for Skill-use maintenance signals: Sleep keeps card/candidate work, while Skill prompt/workflow changes surface as proposal-only Architect signals.
- Expanded Chinese route labels and tightened desktop UI tests so live KB growth no longer creates false failures in navigation-count checks.

## v0.2.2 - 2026-04-25

- Replaced Sleep/Dream/Architect post-completion cooldown windows with explicit core maintenance lane status checks.
- Restored the default local cadence to Sleep 12:00, Dream 13:00, and Architect 14:00 while preventing overlap when another core lane is still running.
- Removed Dream and Architect cooldown CLI knobs from runner prompts, automation specs, docs, and tests so other machines inherit the same behavior after bootstrap.
- Refreshed installer validation for repository-managed maintenance skills and automations.

## v0.2.1 - 2026-04-24

- Refined the desktop card browser UI with lighter card shadows, subtler gradient surfaces, tighter spacing, and denser card layout.
- Updated the README desktop preview screenshots to show the refreshed overview and detail views.
- Added the organization mode planning document for the future GitHub-backed shared KB direction.
- Clarified Skill and plugin-use evidence capture rules in the project spec and local KB retrieval skill.
- Added Chinese route labels for the new release, desktop UI, branding, icon, and Skill-sharing planning routes.

## v0.2.0 - 2026-04-24

- Renamed and presented the project as `Khaos Brain` with refreshed public README positioning, icon artwork, and English UI screenshots.
- Added the local desktop card viewer as a human-facing way to browse the predictive memory library.
- Added Windows desktop packaging support for `KhaosBrain.exe`, including the icon source, shortcut helper, and UI-opening skill.
- Expanded Sleep/Dream/Architect maintenance behavior, semantic review handling, installer checks, and tests for stronger cross-machine defaults.
- Kept build outputs and live KB data out of source control; the Windows executable is published as a GitHub Release asset instead of committed to the repository.
