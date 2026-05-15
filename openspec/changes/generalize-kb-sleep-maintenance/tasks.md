## 1. Model And Documentation

- [x] 1.1 Add a FlowGuard model for the Sleep generalization decision flow and record the adoption note.
- [x] 1.2 Update the project spec, Sleep runbook, and maintenance prompt with the new generalization review rules.

## 2. Proposal Signals

- [x] 2.1 Add scope-assessment helpers for provenance, same-project chronology, cross-project evidence, project-local signals, and skill-specific signals.
- [x] 2.2 Include scope assessment and generalization guidance in new candidate scaffold previews.
- [x] 2.3 Include existing-card generalization recommendations on `review-entry-update` actions.

## 3. Semantic Review Apply

- [x] 3.1 Require `scope_assessment` for applied semantic review decisions.
- [x] 3.2 Carry accepted scope assessment into semantic-review apply reports and maintenance decision metadata.

## 4. Verification

- [x] 4.1 Add focused tests for new candidate scaffolds, same-project chronology, old-card generalization review, project-local preservation, and semantic-review validation.
- [x] 4.2 Run FlowGuard checks and focused test suites; start broader regression checks in the background when useful.
- [x] 4.3 Run install sync and install check after repository changes.

## 5. Release

- [x] 5.1 Perform release audit across version files, changelog, tags, and GitHub Release state.
- [x] 5.2 Update version/changelog for the selected release version.
- [ ] 5.3 Commit all requested local work, including compatible peer-agent changes present in the worktree.
- [ ] 5.4 Push the branch and tag, create the GitHub Release, and verify release alignment.
