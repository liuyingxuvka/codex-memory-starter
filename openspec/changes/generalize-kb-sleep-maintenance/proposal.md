## Why

Sleep maintenance already preserves project/thread provenance and can rewrite existing cards, but the generalization rule is still mostly advisory. This lets project-specific evidence leak into card routes or card wording, and it leaves older project-flavored cards without a required path to become reusable capability cards.

This change makes generalization an explicit Sleep decision: Sleep must use project and time provenance to interpret evidence, then decide whether the resulting card should stay project-local, become a single-project generalizable rule, or be treated as cross-project general evidence.

## What Changes

- Add a formal Sleep generalization review step before candidate creation or semantic card updates.
- Require Sleep to classify evidence scope as `project-local`, `skill-specific`, `single-project-generalizable`, or `cross-project-general`.
- Make new candidate scaffolds expose provenance, chronology, and scope assessment so project names become evidence metadata rather than default rule wording.
- Extend existing-card review so older project-flavored cards can be rewritten, narrowed, split, or kept project-local based on supporting observations.
- Require applied semantic review decisions to include a scope assessment for surface-retaining or card-changing actions.
- Add tests covering new candidate generation, existing-card generalization review, project-local preservation, and semantic-review validation.
- Update the Sleep runbook, maintenance prompt, and project spec so the behavior is auditable and repeatable.

## Capabilities

### New Capabilities
- `kb-sleep-generalization`: Sleep maintenance classifies evidence scope and uses that classification when creating candidates or reviewing existing cards.

### Modified Capabilities

## Impact

- Affected docs: `PROJECT_SPEC.md`, `docs/maintenance_runbook.md`, `.agents/skills/local-kb-retrieve/MAINTENANCE_PROMPT.md`
- Affected implementation: `local_kb/consolidate_suggestions.py`, `local_kb/consolidate_apply.py`, `local_kb/semantic_review.py`
- Affected tests: consolidation proposal/action tests, semantic review validation tests, apply-mode tests
- No new external dependencies are expected.
