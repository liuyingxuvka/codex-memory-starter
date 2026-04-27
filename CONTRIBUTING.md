# Contributing to Khaos Brain

Thank you for considering a contribution to Khaos Brain.

Khaos Brain is a local-first, file-based predictive knowledge library for Codex and other AI coding agents. Contributions should preserve the core design goals: auditable files, explicit retrieval logic, local-first operation, privacy boundaries, and reversible maintenance.

## Development setup

Use Python 3.11 or newer when possible.

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests
```

For Codex integration checks on a machine where Codex is installed, run:

```bash
python scripts/install_codex_kb.py --check --json
```

For the desktop viewer smoke check, run:

```bash
python scripts/kb_desktop.py --repo-root . --check
```

## Contribution scope

Good contributions include:

- clearer documentation and examples;
- schema, retrieval, taxonomy, rollback, and maintenance improvements;
- tests for existing behavior;
- privacy and safety hardening;
- desktop viewer usability improvements;
- Codex skill, installer, and workflow refinements that remain auditable.

Avoid large architectural jumps unless they are discussed first. In particular, do not add vector databases, embeddings, MCP services, opaque autonomous memory growth, or graph databases unless the project explicitly moves in that direction.

## Privacy and safety rules

Do not commit:

- credentials, tokens, API keys, cookies, or secrets;
- private user memories, personal preferences, or live private cards;
- real `kb/history` logs unless they are deliberately sanitized examples;
- real `kb/candidates` data unless it is deliberately public-safe demo content;
- customer, employer, or project-confidential information;
- raw local absolute paths, machine identifiers, or private Git remotes;
- build outputs such as `dist/` artifacts unless they are intentionally published through a release process.

Public examples should be synthetic, sanitized, and safe if copied outside the repository.

## Pull request checklist

Before opening a pull request, check that:

1. The change is consistent with `PROJECT_SPEC.md`.
2. Tests pass with `python -m unittest discover -s tests`.
3. Any new behavior has either tests or a clear manual validation note.
4. No private KB content, credentials, local paths, or machine-specific data were added.
5. Documentation was updated when user-facing behavior changed.

## Card and memory changes

Trusted cards should not be rewritten casually. New lessons should normally enter candidates or structured history first, then be consolidated by the maintenance workflow.

When adding example cards, preserve the predictive structure:

- scenario or condition;
- action or input being evaluated;
- expected or observed result;
- operational use for the agent;
- confidence, status, and source information.

## Reporting issues

When reporting a bug, include:

- operating system;
- Python version;
- command run;
- expected behavior;
- actual behavior;
- relevant traceback or JSON output.

Remove secrets and private KB content before sharing logs.
