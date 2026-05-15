## ADDED Requirements

### Requirement: Sleep classifies evidence scope before card-surface changes
Sleep maintenance SHALL classify the evidence scope for candidate scaffolds and existing-card semantic review actions using one of `project-local`, `skill-specific`, `single-project-generalizable`, `cross-project-general`, or `insufficient-evidence`.

#### Scenario: Same project evidence is not automatically cross-project evidence
- **WHEN** multiple observations in one action share the same `project_ref` or `workspace_root`
- **THEN** Sleep SHALL treat that repetition as same-project chronology evidence unless another independent project or workspace supports the same rule

#### Scenario: Cross-project evidence is visible
- **WHEN** supporting observations come from more than one project or workspace
- **THEN** Sleep SHALL expose that as cross-project evidence in the action's scope assessment

#### Scenario: Skill-specific evidence keeps the Skill boundary
- **WHEN** supporting observations or routes show that a lesson depends on a named Skill, plugin, connector, or tool capability
- **THEN** Sleep SHALL classify the evidence as `skill-specific` unless stronger evidence shows the rule applies outside that capability

### Requirement: Sleep preserves provenance while writing reusable rules
Sleep maintenance SHALL keep project, repository, product, thread, and workspace names as provenance or explanatory metadata unless the card is explicitly classified as project-local.

#### Scenario: Single-project evidence supports a functional rule
- **WHEN** a candidate scaffold is based on one project's observations but the causal lesson can be written as a reusable functional rule
- **THEN** the scaffold SHALL classify the evidence as `single-project-generalizable` and guide the reviewer to write the card in functional terms while preserving the source project in provenance

#### Scenario: Project-specific mechanism remains bounded
- **WHEN** a card or action depends on a named project's unique mechanism
- **THEN** Sleep SHALL classify it as `project-local` or leave it history-only instead of forcing a generic rule

#### Scenario: Skill-specific mechanism remains bounded
- **WHEN** a card or action depends on how a named Skill, plugin, connector, or tool behaves
- **THEN** Sleep SHALL preserve that skill-specific context in the route, wording, or provenance instead of forcing a capability-independent rule

### Requirement: Sleep reviews old cards for generalization opportunities
Sleep maintenance SHALL include generalization review signals on existing-card update actions so old project-flavored cards can be kept local, rewritten as general rules, split, or left under watch.

#### Scenario: Old card is project-shaped but reusable
- **WHEN** an existing card's title, route, or guidance is project-shaped and supporting evidence describes a reusable functional rule
- **THEN** the review action SHALL recommend rewriting the card as a general rule and moving project-specific details into provenance or notes

#### Scenario: Old card is genuinely project-local
- **WHEN** an existing card depends on a named project's unique workflow, toolchain, or maintenance lane
- **THEN** the review action SHALL recommend keeping the card project-local instead of generalizing it

#### Scenario: Old card is genuinely skill-specific
- **WHEN** an existing card depends on a named Skill, plugin, connector, or tool capability
- **THEN** the review action SHALL recommend keeping the skill boundary rather than rewriting the card as an unconditional general rule

### Requirement: Semantic review apply requires scope assessment
Semantic review apply decisions that keep, rewrite, adjust confidence, promote, demote, or deprecate a candidate or trusted card SHALL include a `scope_assessment` object with a recognized scope and reasoning.

#### Scenario: Missing scope assessment blocks apply
- **WHEN** a semantic review decision attempts to apply a card-surface decision without `scope_assessment`
- **THEN** the semantic review apply step SHALL skip the decision and report that scope assessment is required

#### Scenario: Scope assessment is recorded
- **WHEN** a semantic review decision applies successfully
- **THEN** the apply report SHALL include the accepted scope assessment alongside the decision metadata
