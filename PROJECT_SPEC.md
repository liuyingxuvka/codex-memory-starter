# Project Specification: Khaos Brain

## Status

This document is the authoritative implementation brief for Khaos Brain in this repository.

Implement **v0.1 only**. Optimize for clarity, maintainability, and explicit review. Do not jump ahead to vector databases, autonomous memory growth, embeddings, MCP services, or subagent orchestration unless a later task explicitly asks for them.

## 1. Objective

Build a **local, file-based predictive knowledge library** that Codex can consult before solving tasks.

The library is meant to store reusable local experience in a structured way. It is not a general encyclopedia and not a hidden global memory. Its role is narrower:

- preserve reusable patterns
- preserve user-specific preferences when appropriate
- preserve domain heuristics and lessons learned
- help Codex predict likely outcomes under known contexts
- help Codex choose better actions before answering or editing code

The first version should be simple enough that a human can inspect every file, understand every score, and review every update.

## 2. Core Concept

### 2.1 Each entry is a local predictive model card

Every knowledge entry in this repository should be treated as a **bounded predictive model**, not merely a loose note and not a universal truth.

A model card answers the following questions:

1. **In what scenario does this apply?**
2. **What action, input, or condition is under consideration?**
3. **What result is expected or likely?**
4. **What should Codex do with that prediction?**
5. **How confident are we, and where did this come from?**

This means even a preference can be expressed predictively.

Example:

- Scenario: work email drafting
- Action/input: no language explicitly requested
- Predicted result: English is the preferred output
- Operational use: draft in English unless the user overrides it

This also applies to **user-specific interaction patterns** when they are written as bounded predictive models rather than vague impressions.

Example:

- Scenario: public GitHub release presentation for this user
- Action/input: hide version visibility and place developer-oriented setup before the user entry
- Predicted result: review friction is more likely and the page is less likely to match the user's preferred presentation order
- Operational use: keep these cards private by default and adapt release presentation to visible versioning, clear user entry, and the user's preferred ordering when the evidence is stable

Likewise, a debugging heuristic can also be predictive.

Example:

- Scenario: behavior changed after dependency upgrade
- Action/input: skip release notes and start deep debugging immediately
- Predicted result: investigation cost likely increases and obvious causes may be missed
- Operational use: check version, changelog, and release notes first

### 2.2 Local, partial, and conditional

Each model card is intentionally **local** and **conditional**. It is not meant to cover every situation.

A card should only claim what it can justify within a defined scope. A card may include case splits when outcomes differ across conditions.

### 2.3 Human-auditable over clever

The system should remain understandable without hidden model behavior. If a human cannot explain why a card was retrieved or why it was trusted, the design is too opaque for v0.1.

## 3. Design Principles

1. **Local-first**  
   The first implementation runs entirely on local files.

2. **Path-first retrieval**  
   Retrieval should not depend on flat keyword matching alone. It should first locate the relevant direction of thought.

3. **Predictive representation**  
   Store expectation structures, not only descriptive notes.

4. **Multi-index memory palace**  
   Entries should be reachable through a main route and additional cross routes.

5. **Candidate-first capture with AI-driven consolidation**  
   New experience should land in `kb/candidates/` or structured history first, then be consolidated during scheduled AI maintenance.

6. **Public/private separation**  
   User-specific or sensitive knowledge stays private by default.

7. **AI-driven maintenance with file-based tooling**  
   Maintenance decisions may be made automatically by AI, but the tooling around those decisions should remain file-based, logged, inspectable, and reversible.

8. **Simple scoring**  
   Use explainable scoring heuristics instead of opaque retrieval models.

## 4. Retrieval Philosophy: Hierarchical Navigation Before Keyword Matching

The user intent for this project is not “search by isolated keywords only.” The intended behavior is closer to a **memory palace with multiple indexes**.

Codex should first determine the **direction** of the task, then progressively narrow to a sub-direction.

### 4.1 Main route

Each entry should have a `domain_path`, for example:

- `work / reporting / ppt`
- `engineering / debugging / version-change`
- `work / communication / email`
- `research / literature / summarization`
- `codex / runtime-behavior / tool-use`
- `codex / runtime-behavior / prompt-following`

This is the primary route through which the entry should be found.

The primary route should normally describe the reusable function or direction of the lesson, not the project where the evidence happened. Project, repository, and product names belong in provenance, tags, trigger keywords, or explanatory text unless the card is intentionally project-specific.

### 4.2 Cross routes

Each entry may also define `cross_index`, for example:

- `design/presentation/aesthetics`
- `communication/slides/visual-quality`
- `troubleshooting/dependency/regression`
- `ai/runtime/gpt-family`
- `prompting/constraint-following`
- `codex/workflow/planning`

These routes let one entry be discoverable from several conceptual directions without duplicating the file.

### 4.3 Retrieval order

The retrieval logic for v0.1 should follow this order:

1. Infer the **primary route** from the current task.
2. Infer up to **three secondary routes**.
3. Search for entries whose `domain_path` matches the primary route prefix.
4. Expand to entries whose `cross_index` overlaps with the primary or secondary routes.
5. Apply lexical matching on title, tags, trigger keywords, and body.
6. Re-rank by confidence and trust status.

### 4.4 Why this matters

This structure is important because many useful entries do not share the same surface words. A flat keyword search can miss conceptually related entries, while a route-based search can preserve conceptual structure.

### 4.5 Navigation should stay structurally simple

As this library grows, retrieval should become **more navigable**, not more opaque.

The intended direction is:

- keep the library structure explicit and hierarchical
- let Codex narrow the search one route level at a time
- prefer deterministic structural choices over hidden synonym expansion
- keep the retrieval rules simple enough that a human can predict what the next step will return

In practice, this means the system should be able to support a navigation pattern such as:

1. list the top-level route choices
2. choose one or more route indices
3. return the next level under those routes
4. continue narrowing until the relevant cards are found

This style is compatible with multi-turn AI use:

- Codex can inspect the current route layer
- Codex can choose one branch or several branches in parallel
- Codex can quickly confirm that a branch is irrelevant and back out
- Codex does not need a large hidden synonym system if the route tree is clear

For this reason, future retrieval improvements should favor:

- route tree enumeration
- deterministic branch selection
- optional parallel expansion of multiple branches
- narrow, inspectable rules

They should not default to:

- large alias tables
- opaque query rewriting
- hidden semantic expansion that a human cannot audit easily

This is an architectural principle for the library. The storage format should remain simple so that most adaptation happens during lookup, with Codex following clear navigation rules over explicit route structure.

## 5. v0.1 Scope

### 5.1 In scope

- YAML-based local storage
- public / private / candidate separation
- hierarchical `domain_path`
- `cross_index` support
- explainable scoring
- explicit taxonomy inspection
- one retrieval skill
- Codex-oriented sidecar sub-agent workflow guidance
- one candidate-capture script
- history or feedback logs
- AI-driven scheduled consolidation / “sleep” maintenance
- optional bounded “dream” exploration maintenance that writes only to history or candidates
- example entries
- small evaluation cases
- documentation for Codex

### 5.2 Explicitly out of scope for v0.1

- embeddings or vector search
- external databases
- opaque autonomous promotion without AI-authored rationale or logged criteria
- hidden autonomous write-back without snapshots or rollback
- free-form autonomous capability growth or direct trusted-card mutation from dream-only evidence
- MCP-backed knowledge services
- opaque or mandatory subagent orchestration without fallback behavior
- probabilistic calibration infrastructure
- graph databases

Subagents are available in current Codex releases, but they are more expensive and only run when explicitly requested. For this repository they are optional, and are most useful as sidecar helpers for scout, recorder, or scheduled maintenance workflows.

## 6. Repository Architecture

The repository should be organized so the file system itself supports the conceptual hierarchy.

```text
.
├─ AGENTS.md
├─ PROJECT_SPEC.md
├─ README.md
├─ docs/
│  ├─ architecture_runbook.md
│  ├─ dream_runbook.md
│  └─ maintenance_runbook.md
├─ .agents/
│  └─ skills/
│     └─ local-kb-retrieve/
│        ├─ ARCHITECT_PROMPT.md
│        ├─ SKILL.md
│        ├─ DREAM_PROMPT.md
│        ├─ MAINTENANCE_PROMPT.md
│        ├─ agents/openai.yaml
│        └─ scripts/
│           ├─ kb_nav.py
│           ├─ kb_search.py
│           ├─ kb_feedback.py
│           ├─ kb_capture_candidate.py
│           ├─ kb_consolidate.py
│           ├─ kb_dream.py
│           ├─ kb_architect.py
│           ├─ kb_proposals.py
│           ├─ kb_rollback.py
│           └─ kb_taxonomy.py
├─ kb/
│  ├─ history/
│  ├─ taxonomy.yaml
│  ├─ public/
│  ├─ private/
│  └─ candidates/
├─ local_kb/
│  ├─ search.py
│  ├─ routes.py
│  ├─ feedback.py
│  ├─ history.py
│  ├─ architect.py
│  ├─ consolidate.py
│  ├─ proposals.py
│  ├─ snapshots.py
│  └─ taxonomy.py
├─ schemas/
│  └─ kb_entry.example.yaml
└─ tests/
   ├─ eval_cases.yaml
   ├─ test_kb_consolidate_scaffold.py
   ├─ test_kb_rollback_worker2.py
   └─ test_kb_taxonomy_worker1.py
```

Codex currently discovers repository skills from `.agents/skills/...`, and a skill is a directory containing `SKILL.md` plus optional scripts and metadata.

## 7. Knowledge Entry Schema

### 7.1 Required fields for v0.1

Each entry should support the following structure:

- `id`: stable identifier
- `title`: short readable title
- `type`: `model`, `preference`, `heuristic`, or `fact`
- `scope`: `public` or `private`
- `domain_path`: ordered list representing the main conceptual route
- `cross_index`: additional conceptual routes
- `related_cards`: direct related-card ids that are repeatedly used together with this card
- `tags`: lightweight retrieval hints
- `trigger_keywords`: lexical triggers
- `if`: applicability notes / conditions
- `action`: what action or input is being evaluated
- `predict`: expected result and optional case splits
- `use`: how Codex should apply the prediction
- `confidence`: 0 to 1
- `source`: origin metadata
- `status`: `candidate`, `trusted`, or `deprecated`
- `updated_at`: ISO date

### 7.2 Schema interpretation

A card is operational, not merely descriptive.

- `if` defines the situation
- `action` defines what is being attempted or observed
- `predict` defines the expected result
- `use` defines what Codex should do because of that prediction
- `related_cards` defines a small direct-navigation surface between cards that are repeatedly used together; it is not a concept graph and should stay short

This keeps the knowledge unit useful for action selection.

Modeling discipline for v0.1:

- A valid model card should encode a directional claim such as: under condition `if`, taking `action` makes `predict.expected_result` more likely.
- Generic advice such as “should”, “avoid”, or “best practice” is not sufficient on its own.
- `use` must remain downstream of `predict`; operational guidance cannot replace the predictive claim itself.
- Titles should preferably name the predicted relation or outcome, not only the recommended behavior.
- Cards about **model or runtime behavior** are allowed when they are still written as bounded predictive models rather than folklore.
- Cards about a **specific user** are also allowed when they stay bounded, evidence-based, and behaviorally framed.
- User-specific cards should be `private` by default unless the user explicitly wants them shared.
- Such cards should describe repeated task-conditioned interaction patterns, preferences, or judgments, not personality labels or broad character summaries.
- A good user-specific card answers: under what conditions, what request style, structure, or omission makes what user reaction or preference more likely.
- Such cards should be scoped to the most precise runtime identity that is actually known.
- If the exact model version is surfaced reliably, the card may name it directly.
- If the exact model version is not surfaced reliably, scope the card more conservatively to the active Codex runtime, current environment, or known model family instead of guessing a precise version.
- These cards should still preserve explicit `if / action -> predicted result -> use` structure and should avoid vague claims about “LLMs in general.”
- These cards often need more than one retrieval entry point. A runtime-focused route may be primary, while workflow, prompting, tool-use, or planning routes remain in `cross_index`.

## 8. Retrieval Algorithm for v0.1

The implementation should remain intentionally simple.

### 8.1 Inputs

The search tool should accept:

- `--query`: free-text task summary
- `--path-hint`: optional route hint such as `work/reporting/ppt`
- `--top-k`: result count

### 8.2 Scoring components

The search score should combine:

- `domain_path` prefix match
- `domain_path` token overlap
- `cross_index` token overlap
- title match
- tag match
- trigger keyword match
- body match
- confidence bonus
- trusted / deprecated status bonus or penalty

A simple explainable formula is preferred. For example:

```text
score =
  8 * path_prefix_len
+ 5 * domain_path_overlap
+ 4 * cross_index_overlap
+ 3 * title_match
+ 5 * tag_match
+ 4 * trigger_match
+ 1 * body_match
+ 2 * confidence
+ trusted_bonus
- deprecated_penalty
```

The exact constants can be adjusted, but the logic should remain easy to inspect.

### 8.3 Retrieval behavior

- If `path-hint` exists, use it strongly.
- If no path hint exists, fall back to lexical search.
- Always return a small ranked list.
- Prefer `trusted` over `candidate` when relevance is similar.
- Never treat retrieval as certainty.

## 9. Skill Behavior

The repository should provide one initial skill: `local-kb-retrieve`.

The skill should do the following:

1. Summarize the task in one short sentence.
2. When sub-agents are available and the task is non-trivial, start a scout-style sidecar agent to handle route scan and retrieval without distracting the primary task thread.
3. Infer one primary `domain_path` and up to three alternative conceptual routes.
4. Run the local search script with both a path hint and a textual query.
5. Review the top results.
6. Prefer entries with stronger path alignment, `trusted` status, and higher confidence.
7. Use retrieved entries as bounded context.
8. At the end of the task, start a recorder-style sidecar agent, or an equivalent inline fallback, to append feedback, misses, and candidate lessons into history.
9. State which entry ids influenced the answer.
   These should be the cards that materially influenced the work, not every card that appeared in retrieval results.
10. When a reusable lesson is specifically about how the current model or runtime behaves, it may still be captured as a valid card if the runtime identity and triggering conditions are explicit enough to audit later.
11. When recording such a lesson, preserve both the runtime-facing route and any workflow or prompting routes that materially shaped the behavior, so later retrieval can find the card from more than one valid direction.
12. When a reusable lesson is specifically about how a user tends to respond, prefer a private predictive card that captures the task condition and likely user preference or reaction, rather than a vague impression about the user's personality.

For non-trivial work, KB postflight should be treated as part of done rather than optional housekeeping. Before a task is considered complete, Codex should explicitly check whether the task exposed:

- a reusable lesson
- a retrieval miss
- a route gap
- a card weakness
- a KB-process failure

If the answer is yes, Codex should append one structured observation before ending the task. If the answer is no, the lack of meaningful signal should still be an explicit conclusion rather than a forgotten check.

Skills are the reusable workflow layer in Codex, while plugins are the installable distribution unit. This is the right reason to keep the workflow local first and package later only when stable.

For Codex specifically, a good operating pattern is:

- `kb-scout` sidecar before the main task for route scan and card retrieval
- primary task agent stays focused on the user request
- `kb-recorder` sidecar after the main task for comments, misses, and candidate capture
- independent scheduled maintenance thread or automation for deeper “sleep” consolidation

This keeps memory interaction from derailing the main task while still letting the system improve itself continuously.

## 10. Update and Governance Rules

### 10.1 Promotion policy

All new knowledge should enter `kb/candidates/` or structured history first.

Architecturally, promotion to `kb/public/` or `kb/private/` may eventually happen automatically during scheduled AI maintenance if the repository's safety rails are satisfied. The deciding step should come from AI judgment over the stored history, while the resulting update should still be logged, snapshotted, and reversible.

The semantic maintenance boundary should preserve AI agency without allowing uncontrolled churn:

- thresholds, repeated reviews, and weak-hit counts are review triggers, not final decisions
- AI should decide whether a card should be kept, rewritten, promoted, demoted, deprecated, split, or merged after reading the card and supporting evidence
- tooling should require an explicit semantic-review plan with evidence ids, rationale, risk level, expected retrieval effect, and rollback notes before applying meaning-bearing changes
- each semantic-review apply run should modify at most 3 trusted cards, including trusted rewrites, confidence changes, deprecations, demotions, and candidate promotions into trusted scope
- candidate and trusted-card text changes should trigger display-translation cleanup before the sleep pass is considered complete

For the current implementation, keep the operational boundary simpler:

- active task threads should prefer `kb/candidates/` or structured history writes
- trusted-scope rewrites and promotions should be treated as dedicated semantic maintenance work
- if the current tooling does not yet implement a specific semantic change cleanly, leave that change proposal-only instead of implying that the path already exists

### 10.2 Conflict handling

Priority order:

1. direct user instruction in the current conversation
2. explicit repository instructions
3. trusted KB entry
4. candidate KB entry

### 10.3 Privacy

- user-specific preferences go to `private`
- general engineering heuristics may go to `public`
- private content should stay out of public commits by default

### 10.4 Deprecation

Entries should never be silently deleted when they become weak or obsolete. Prefer `status: deprecated` with an updated note if needed.

### 10.5 Weak evidence, rejection, and forgetting

The repository should distinguish between:

- evidence that is not yet strong enough to become a card
- candidate cards that were reviewed and rejected
- trusted cards that later become weak or obsolete

The correct handling is different for each case:

- **weak or one-off observations** should usually be forgotten by the retrieval surface but retained in history
- **complete single observations** may create low-confidence candidate scaffolds when the route is specific, the task summary is present, and the observation already states scenario, action, and observed result; these are retrieval seeds, not trusted rules
- **rejected candidates** should leave a rejection trace in history and should not remain in the active candidate queue
- **obsolete trusted cards** should usually become `deprecated`, not silently deleted

In practice, this means:

- if an observation is clearly one-off, generic, noisy, or not reusable, scheduled maintenance may mark it as ignored or non-reusable and leave it in history only
- if a candidate is reviewed and not promoted, maintenance should record that rejection, including why it was rejected and which evidence supported the decision
- if a trusted card is no longer reliable, maintenance should prefer `status: deprecated` plus updated notes over deletion

The guiding principle is:

- the **retrieval layer may forget**
- the **history layer should remember**

This keeps the active memory surface clean without erasing the evidence trail behind prior decisions.

For v0.1, the simplest acceptable implementation is:

- weak observations stay in `kb/history/events.jsonl`
- rejected candidates leave a history event such as candidate rejection or ignored evidence
- active retrieval should prefer trusted cards, then viable candidates, and should ignore rejected or one-off evidence

An archive directory for rejected candidates is optional. It is acceptable to remove a rejected candidate from the active candidate area as long as the rejection reason remains in history.

### 10.6 Confidence rise, weakening, and review

The repository should not introduce a separate “execution score” in v0.1. The existing `confidence` field is the simple operational proxy for how strongly Codex should rely on a card during normal work.

This means:

- `confidence` may rise when repeated use supports the model
- `confidence` may fall when observations show weak hits, contradictions, misleading outcomes, or narrower scope than the current card claims
- lowering confidence is a normal maintenance action, not a failure state

The intended behavior is:

- one contradictory or weak observation should usually lower confidence or trigger watchful review, not force an immediate rewrite
- repeated contradictory evidence should trigger an `update-card` or `deprecated` review
- if the model still looks directionally right but less universal than before, prefer narrowing scope and lowering confidence over deleting the card

For v0.1, a simple review interpretation is enough:

- `confidence >= 0.75`: normal trusted use
- `0.50 <= confidence < 0.75`: still usable, but maintenance should review the card if weakening evidence continues
- `confidence < 0.50`: the card should be revised, narrowed, split, or deprecated before continued normal reliance

The exact numeric thresholds may be adjusted later, but the behavior should stay simple:

- confidence can go up
- confidence can go down
- lower confidence means weaker reliance
- sufficiently low confidence triggers review

Every confidence change should leave a history trace that records:

- the previous confidence
- the new confidence
- why it changed
- which observations or maintenance pass motivated the change

### 10.7 Card splitting during sleep maintenance

Repeated hits on the same card should not automatically trigger a split.

Instead, repeated hits are a **split review signal**:

- sometimes they mean the card is the correct high-level entry point
- sometimes they mean the card has become overloaded and is no longer one bounded predictive model

Maintenance should therefore distinguish between:

- a **hub card**
  - still expresses one bounded predictive relation
  - is frequently retrieved because many tasks naturally pass through that route
  - should usually stay intact, even if it remains a common first hit
- an **overloaded card**
  - has started to carry multiple scenarios, actions, predicted results, or route-specific case branches
  - is no longer acting as one bounded predictive model
  - should usually move toward a split proposal

The intended maintenance rule is:

- high hit count alone is not enough to split a card
- split review should look for predictive overload, not raw popularity
- if the card still expresses one stable predictive relation, keep it as a hub card
- if the card now mixes several predictive relations, split it into smaller sibling cards

When a split is needed:

- the split cards may remain under the same main `domain_path`
- a lighter hub card may stay in place as the route entry point
- the related cards may cross-reference each other if that improves navigation and reviewability

Every split or split-rejection should leave a history trace describing:

- which card was reviewed
- why it was kept as a hub or marked as overloaded
- what child or sibling cards were proposed or created
- which observations triggered the review

### 10.8 Current state, history, and consolidation

The library should distinguish between:

- the **current merged card**, which represents the latest consolidated operational version of the model
- the **history of that card**, which preserves how the card reached its current form

The current merged card is the surface that Codex should retrieve and use during normal work. It should stay concise, stable, and directly actionable.

The history layer should preserve the evidence trail behind the card, including items such as:

- usage records
- feedback after retrieval or application
- comments about when the model did or did not hold
- score changes, confidence changes, or importance changes
- reasons for narrowing or expanding scope
- reasons for modifying the main card text
- timestamps for these events

Every meaningful memory mutation should leave a timeline trace. This includes:

- card creation
- card updates
- confidence or importance changes
- comments and feedback writes
- candidate promotion or rejection
- taxonomy changes
- merges, splits, moves, and deprecations

Each such event should preserve enough information to answer:

- what changed
- when it changed
- why it changed
- which prior state it came from
- what source observation, feedback, or maintenance pass triggered it

This history matters because the library should not only store the latest conclusion. It should also preserve why that conclusion changed over time.

As the repository evolves, it is reasonable to add a consolidation or “sleep” layer in which AI periodically reviews this history and applies updates automatically. That layer should:

- read accumulated feedback and usage history
- identify cards that need clarification, scope adjustment, splitting, merging, re-scoring, or deprecation
- let AI decide the needed card and taxonomy updates
- use tooling to apply the chosen updates to cards and taxonomy
- write snapshots and change reasons before finalizing updates
- preserve enough state to support rollback
- cap each automated semantic-review pass to a small trusted-card budget; the current default is 3 trusted cards per run

It may update trusted cards during scheduled consolidation, but those updates should never be opaque. Every automatic merge should leave an audit trail that captures what AI changed and why.

In other words:

- the main card stores the current consolidated state
- the history preserves the reasoning and evidence trail
- AI-driven consolidation evaluates accumulated history
- tooling applies the AI-selected merge to produce the new main card state
- snapshots and rollback preserve recoverability

This repository is therefore allowed to maintain itself automatically, but the maintenance intelligence should live in AI rather than in a brittle hard-coded rule engine. The goal is not human-in-the-loop maintenance by default. The goal is AI-driven autonomous maintenance that remains inspectable after the fact.

This principle is compatible with the file-based design of the repository. The exact storage layout for history can remain simple, but the distinction between current state and historical record should remain clear. Code in this repository should provide the memory substrate, navigation, logging, snapshots, and patch application; AI should provide the maintenance judgment.

The scheduled maintenance flow should preferably run in an independent thread, chat, or automation so that deep memory upkeep does not interrupt the main task thread. A daily or periodic maintenance conversation is a valid operating model for this repository.

The sleep flow is itself a KB task. Each sleep pass should therefore begin with a
small route-first retrieval against prior maintenance lessons, usually under
`system/knowledge-library/maintenance`, before it inspects taxonomy, proposals, or
apply actions. Retrieved maintenance cards are bounded context, not authority over
the current repository state.

Each sleep pass should also create and maintain a visible execution plan before
stateful maintenance work begins. The plan should list the concrete checkpoints for
the pass and track each item as pending, in progress, completed, skipped with a
reason, or blocked with a concrete blocker. A sleep pass should not stop after a
short proposal or one successful command while safe required checkpoints remain.
If a command exposes a supported low-risk repair, the maintenance agent should try
that repair and rerun the relevant validation before finalizing. Unsupported or
higher-risk issues should be recorded as proposal-only or as a final observation,
then the pass should continue through remaining safe checkpoints.

Each non-empty sleep pass should also end with an explicit postflight check. If the
pass exposed a reusable maintenance lesson, route gap, card weakness, split signal,
translation gap, process weakness, or apply hazard, the pass should append one
structured observation to history before finalizing. That final observation is a
record for a future maintenance pass; it should not trigger an immediate recursive
consolidation loop in the same pass.

#### Related-card links

The library may maintain a small direct `related_cards` field on cards when repeated observation history shows that the same cards are materially used together.

This field should stay intentionally simple:

- it stores direct card ids, not weighted graph state
- it should be derived from repeated co-use of actually used `entry_ids` in observations
- it should not be populated from mere retrieval visibility
- it should avoid recursive expansion
- it should usually keep no more than 3 related cards per entry

The maintenance layer may keep richer support counts, ratios, decay, or ranking logic in history and proposal artifacts, but the card surface should remain only the current consolidated result.

#### Display-language translations

The canonical card text should stay in English in the top-level fields. Human-facing translations may be stored under an optional `i18n` block.

For v0.1, the supported display translation is:

- `i18n.zh-CN`

Localizable fields are limited to the human text surfaces:

- `title`
- `if.notes`
- `action.description`
- `predict.expected_result`
- `predict.alternatives[].when`
- `predict.alternatives[].result`
- `use.guidance`

Route values are not localizable source fields. `domain_path`, `cross_index`, taxonomy
routes, search hints, and file paths should remain canonical English route segments.
Human-facing UIs may render those route segments through a display-label map such as
`zh-CN`, but that display layer must not rename the stored route or change retrieval
behavior.

Retrieval and maintenance should treat the English top-level fields as the source of truth. The UI may render `i18n.zh-CN` when the user chooses Chinese, but it must fall back to the English field whenever a translation is missing.

Chinese text should normally be filled during sleep maintenance, not opportunistically during every active task. The maintenance pattern is:

- detect which cards are missing zh-CN display fields
- detect which route segments are missing zh-CN display labels
- ask AI maintenance to produce an auditable translation plan
- apply that plan with file-based tooling
- write an `i18n-updated` history event that records the plan path and remaining missing fields

For route segment display labels, the current low-risk output is a review action that asks
AI maintenance to patch the display-label map. It should not auto-translate unknown
segments at runtime and should not rewrite canonical route fields.

The code should not use an external translation service, embedding model, vector database, or hidden remote process. AI provides the translation judgment; the repository tooling only applies and logs the selected text.

### 10.9 Observation-first card creation

New cards should not be generated mechanically from every conversation or every project summary.

The preferred unit of memory capture is an **episode** or **task observation**:

- a non-trivial task or task fragment finishes
- Codex can describe the scenario, action, and observed result
- Codex can say whether an existing card helped, failed, or was missing
- Codex can judge whether the observation looks reusable beyond the immediate moment

During normal work, the system should prefer recording structured observations first, rather than immediately committing a new durable card.

An observation may include fields such as:

- task or episode summary
- inferred route or route hint
- scenario / condition
- action taken
- observed result
- operational use implied by the result
- whether an existing card was hit
- whether the hit was useful, weak, or misleading
- whether a missing card was exposed
- whether the user corrected or reinforced the outcome
- why the observation may or may not be reusable
- timestamp and source context

The source context should preserve provenance when available, such as:

- which agent or maintenance sidecar recorded the observation
- which thread or conversation it came from
- which project or repository produced the evidence
- which workspace root or local path context it came from

This provenance should explain where the evidence came from, but it should not automatically become the card's main retrieval route during sleep consolidation.

During sleep maintenance, this provenance should not be treated as passive metadata only. Timestamps plus `project_ref`, `thread_ref`, and `workspace_root` should let AI reconstruct **chronological episodes** inside the same project or workflow, so maintenance can see that one path was tried earlier and a better path emerged later.

When an observation is intended to support a future card, it should preserve predictive-model clues rather than stopping at a generic retrospective. In practice, the evidence should make it possible to reconstruct:

- the scenario or condition
- the action or input under consideration
- the observed or expected result
- the operational use implied by that result

When the task included a mistake, weak path, or later correction, the strongest observation is often **contrastive evidence** rather than a single-path summary. In that case, preserve both:

- the earlier action or condition that produced the weaker result
- the weaker or failed result that followed
- the revised action or condition
- the improved result after the revision

This style is especially valuable because later card creation can often map it directly into `predict.expected_result` plus one or more `predict.alternatives` branches, instead of forcing maintenance to infer the negative branch from vague prose.

Observations that only say “should”, “avoid”, or “best practice” without a clear scenario-action-result relation should be treated as weak evidence until AI rewrites or splits them into a proper predictive model hypothesis.

Observations about **model/runtime behavior** should follow the same rule. They are valid when they answer:

- which runtime or model identity was actually in use
- under what concrete conditions or prompts the behavior appeared
- what behavior became more likely
- how Codex should operationally adapt because of that result

If the runtime identity is uncertain, the observation should explicitly scope itself to the known environment level rather than claiming an exact model version.

Observations about a **specific user** should also stay predictive and bounded. They are strongest when they answer:

- in what task or interaction context the behavior appeared
- what structure, omission, or request style preceded the reaction
- what user preference, correction, or judgment became more likely
- how Codex should adapt next time

These observations should avoid personality summaries and should default to `private` handling unless the user explicitly asks for them to be shared.

When later card creation is likely, Codex should preserve enough route context that the resulting card can be found from more than one valid direction. Runtime-behavior cards are usually strongest when they are reachable from both:

- a runtime-focused route such as `codex/runtime-behavior/...` or `ai/runtime/...`
- a task-facing route such as `prompting/...`, `codex/workflow/...`, or another route that captures the condition that exposed the behavior

Card creation should then happen mainly during scheduled AI consolidation:

- ignore weak or one-off observations
- append supporting history to an existing card
- update an existing card
- add a new candidate card
- merge several related observations into one stronger card
- split an existing card if repeated observations reveal case splits

This means observation capture should not rely on memory alone. During normal work, Codex should perform an explicit postflight question before finishing the task:

- did this task produce meaningful evidence for the KB?

If yes, write one structured observation.
If no, end the KB flow explicitly.

The goal is to prevent the common failure mode where preflight recall happens but useful new evidence is never written back.

This means the repository should optimize for collecting good evidence during active work, not for producing a large number of new cards during every dialogue.

In short:

- active task flow should capture observations
- scheduled maintenance should synthesize cards from observations
- durable cards should represent consolidated reusable experience, not raw task residue

### 10.10 Separate dream exploration maintenance

The repository may also support a separate **dream** lane, but it must remain distinct from sleep maintenance.

The purpose of sleep is consolidation:

- review accumulated real observations
- repair, merge, split, rerank, or deprecate memory surfaces
- keep the active retrieval layer clean and auditable

The purpose of dream is exploration:

- generate bounded hypotheses from existing cards, misses, and route gaps
- run small validation attempts on things that have not yet been tried enough in normal work
- discover whether an adjacent route, workflow, or capability is worth later real-world use

This distinction matters because the repository should not treat speculative exploration as if it were already trusted experience.

The required operating rules are:

- dream and sleep must run in separate automations, threads, or maintenance sessions
- they must not run concurrently on the same repository state
- dream should not duplicate route-candidate creation that current sleep consolidation already marks as eligible
- dream should write only to history, proposal artifacts, or `kb/candidates/`
- dream should never directly rewrite `kb/public/` or `kb/private/`
- dream-derived evidence should preserve explicit provenance so later maintenance can tell it apart from normal task evidence
- dream-derived evidence alone is not enough to promote or strongly raise confidence on a trusted card
- user-specific predictions discovered during dream mode should stay especially conservative; they should not become trusted private cards without later confirmation in live interaction

Dream mode should stay grounded in existing evidence. Eligible inputs are things such as:

- repeated retrieval misses
- repeated weak hits
- low-confidence candidates that need a narrow validation attempt
- proposal-only maintenance actions that still need evidence
- taxonomy gaps that repeatedly appear in observed routes
- explicit user-supplied hypotheses such as “maybe the system could learn X this way”

Each dream run should create a bounded experiment record before acting. That record should say:

- which route or card cluster the exploration is about
- what hypothesis is being tested
- what the maximum allowed action surface is
- what success, failure, or inconclusive result would look like
- what write-back is permitted afterward

For v0.1, dream mode should prefer:

- read-only inspection
- local dry-runs
- retrieval experiments
- proposal generation
- candidate scaffolding
- evaluation against explicit tests or route checks

It should avoid:

- repo-wide formatting
- dependency installs
- lockfile churn
- destructive changes
- broad refactors
- silent trusted-card rewrites
- open-ended “try anything interesting” behavior

The simplest acceptable write-back policy is:

- every dream run appends an explicit observation or maintenance event to history
- if the run produced a reusable hypothesis, it may also create or update a candidate scaffold
- if the result was noisy, one-off, or failed to generalize, keep it in history only
- sleep maintenance may later review these dream outputs, but trusted promotion should still depend on later grounded evidence from real tasks or repeated low-risk confirmation

Dream mode is therefore not a second consolidation pass. It is a bounded hypothesis-generation and validation lane whose outputs remain provisional until later evidence supports them.

### 10.11 Separate Architect mechanism maintenance

The repository may also support a third scheduled **Architect** lane, but it must stay narrower than general self-refactoring.

The purpose of Architect is mechanism maintenance:

- review Sleep, Dream, Architect, retrieval, installation, validation, rollback, and proposal-governance signals
- maintain a mechanism proposal queue
- cluster duplicate proposals
- decide whether mechanism proposals are watching, ready for patch, ready for apply, applied, rejected, or superseded
- apply only narrow, high-evidence, high-safety mechanism changes with immediate validation

Architect must not maintain card content. These remain Sleep responsibilities:

- trusted-card rewrites
- candidate promotion
- card merge, split, deprecation, or deletion
- card confidence changes
- user-specific knowledge maintenance

Each Architect pass is itself a KB task. It must begin with route-first retrieval against prior maintenance lessons, usually under `system/knowledge-library/maintenance`, and it must end with an explicit KB postflight observation.

Architect uses only three review axes:

- `Evidence`: whether the mechanism signal is repeated and grounded
- `Impact`: how much it affects KB operating reliability
- `Safety`: how narrow, testable, and reversible the change is

Do not replace these with a large weighted scoring system. The point is to keep autonomous maintenance auditable.

Allowed statuses are:

- `new`
- `watching`
- `ready-for-patch`
- `ready-for-apply`
- `applied`
- `rejected`
- `superseded`

There is no human-review status. High-risk or uncertain proposals remain under long observation as `watching` until evidence and safety improve.

The daily Architect pass should not be forced to invent a new proposal. It must maintain the queue every day, which can mean creating, merging, upgrading, applying, rejecting, superseding, or explicitly doing nothing when no signal crosses the threshold.

The default cadence is after Sleep and Dream, for example:

- `KB Sleep`: 12:00
- `KB Dream`: 13:00
- `KB Architect`: 14:00

The installer should provision all three repository-managed automations, and the install check should verify all three.

## 11. Implementation Plan for Codex

Codex should treat the following as the implementation sequence.

### Phase 1 — Align the schema with the predictive model concept

Tasks:

1. Update `schemas/kb_entry.example.yaml`.
2. Update sample entries so they use `domain_path`, `cross_index`, `action`, `predict`, and `use`.
3. Keep backward compatibility where practical.

### Phase 2 — Refactor retrieval toward hierarchical routing

Tasks:

1. Update `kb_search.py` to accept `--path-hint`.
2. Add scoring for `domain_path` and `cross_index`.
3. Improve rendering so results show:
   - id
   - title
   - domain path
   - predicted result
   - operational guidance
   - score
4. Keep the logic file-based and deterministic.

### Phase 3 — Refactor candidate capture

Tasks:

1. Update `kb_capture_candidate.py` so it can write predictive model fields.
2. Support `domain_path`, `cross_index`, `action`, `expected_result`, and `guidance`.
3. Continue writing to `kb/candidates/` only.

### Phase 4 — Update the skill and repository guidance

Tasks:

1. Update `SKILL.md` to instruct path-first retrieval.
2. Keep `AGENTS.md` short and routing-focused.
3. Ensure `AGENTS.md` tells Codex to read this specification before architectural changes.

Codex reads `AGENTS.md` before work and merges project guidance by directory depth, so repository-level instructions should stay small and stable while deeper documents carry the full plan.

### Phase 5 — Add minimal evaluation coverage

Tasks:

1. Expand `tests/eval_cases.yaml`.
2. Include route-based examples, not only keyword examples.
3. Verify that relevant entries rank near the top for representative tasks.

### Phase 6 — Add optional dream-mode scaffolding

Tasks:

1. Add a dedicated runbook that keeps dream-mode separate from sleep maintenance.
2. Store dream run artifacts under a distinct history location such as `kb/history/dream/<run-id>/` when a dedicated tool does not yet exist.
3. Reuse current file-based tools such as `kb_search.py`, `kb_feedback.py`, `kb_capture_candidate.py`, and proposal artifacts instead of introducing opaque autonomous machinery.
4. Keep dream write-back candidate-only or history-only until later real-task evidence confirms the result.
5. Add a small evaluation set that checks the system can distinguish consolidation work from exploration work.

## 12. Definition of Done for v0.1

The first version is done when all of the following are true:

- repository contains the predictive schema documentation
- repository contains at least two example model cards
- search script supports `--path-hint`
- search output exposes domain path, predicted result, and guidance
- capture script can write predictive candidate entries
- skill instructions reflect route-first retrieval
- `AGENTS.md` points Codex to this design brief
- evaluation cases exist for at least a few representative tasks
- no embeddings, no opaque AI-driven promotion, and no external services are required

## 13. GitHub Publication Plan

Do not publish immediately.

First stabilize locally.

Only after local usage confirms the structure is helpful should the repository be prepared for sharing. At that point:

1. remove or exclude private examples
2. keep only public examples and generic templates
3. add a concise public README
4. document the schema and workflow clearly
5. include a small evaluation set
6. keep the project opinionated but narrow

The shared repository should distribute the **workflow and schema**, not private memory.

## 14. Non-Goals and Anti-Patterns

Do not let the first version drift into these patterns:

- a generic note-taking pile
- a memory system that rewrites itself without logs, thresholds, snapshots, or rollback
- a vector-search project before there is enough data
- a graph database project before there is enough operational value
- a fully autonomous self-belief system
- a tool that treats weak hypotheses as durable truth

## 15. Operational Reminder for Codex

When modifying this repository:

- prefer the simplest working implementation
- preserve human readability
- make scoring explainable
- make automatic maintenance explainable and reversible
- do not silently introduce heavy dependencies
- do not expand scope beyond v0.1
- keep changes incremental and reviewable

The purpose of this repository is not to simulate a perfect mind. The purpose is to build a practical local scaffold that helps Codex retrieve reusable predictive experience in a controlled way.
