# Repository expectations

## Bootstrap

- If the user asks to install, enable, deploy, bootstrap, or set up this predictive KB system on any machine, your default first action is to run `python scripts/install_codex_kb.py --json` from the repository root.
- Immediately after installation, run `python scripts/install_codex_kb.py --check --json` and confirm the install is healthy before doing anything else.
- Treat the installer as idempotent. If the system may already be installed, rerun the installer anyway rather than asking the user to verify it manually.
- If this repository was moved to a new path or re-cloned, rerun the installer from the new clone so the Codex-side manifest points at the current KB root.
- The installed global preflight skill must enable implicit invocation and must remind Codex to record KB postflight observations after meaningful work. Treat either missing behavior as an installation defect and fix it.
- The installer must also refresh the repository-managed `KB Sleep` and `KB Dream` cron automations under `$CODEX_HOME/automations` so another machine inherits the same maintenance cadence after bootstrap.

## Start here

- Read `PROJECT_SPEC.md` before making architectural changes.
- Treat `PROJECT_SPEC.md` as the authoritative v0.1 design brief.
- Keep `AGENTS.md` short; put detailed design rationale in `PROJECT_SPEC.md`.

## Purpose

This repository stores a local predictive knowledge library that Codex can consult before solving tasks.

## GitHub publish default

- When the user asks to update or sync GitHub for this repository, default to a release-style publish flow rather than a branch-only push.
- Inspect `VERSION`, visible README versioning, git tags, and GitHub Release state together before publishing.
- If repository content changed since the last tagged commit, choose the next version, update visible version files, create a new annotated tag, and push the branch plus tag unless the user explicitly asks for branch-only sync.
- Do not move an existing tag unless the user explicitly asks for it.

## How to use the library

- Run `python scripts/install_codex_kb.py` once per machine to install the global Codex preflight skill and launcher.
- When the task is machine setup for this system, do not wait for extra confirmation or extra explanation. Run the installer and check commands as the default bootstrap path.
- When a task may depend on user preference, recurring workflow, domain heuristics, or prior lessons, invoke `$local-kb-retrieve` first.
- Infer a primary conceptual route before retrieval. Do not rely on flat keywords alone when a route is apparent.
- Treat KB entries as bounded context, not unquestionable truth.
- Prefer entries with `status: trusted`.
- If an entry conflicts with direct user instructions in the current conversation, follow the current user instruction.

## Update rules

- Do not write directly into `kb/public/` or `kb/private/` from an active task thread.
- In the current implementation, new lessons should normally land in `kb/candidates/` or structured history first. Treat trusted-scope rewrites and promotions as maintenance work, not as default inline edits.
- New lessons should first be proposed into `kb/candidates/`.
- Keep private data out of commits unless the user explicitly wants it versioned.
- Do not add embeddings, vector databases, MCP services, or subagent orchestration in v0.1 unless explicitly requested.

## Validation

- Before changing retrieval logic, run a quick manual search test.
- Keep the skill description narrow so it does not trigger on trivial tasks.
- Keep scoring logic explainable and easy to inspect.
