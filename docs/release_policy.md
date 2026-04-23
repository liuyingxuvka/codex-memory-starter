# Release Policy

This repository should not create a new version number every time GitHub is touched.

The correct default is:

1. run a **release audit**
2. decide whether the change is release-worthy
3. only then decide whether a new version is justified

## 1. Release audit first

Before publishing, inspect all of these together:

- current `HEAD`
- latest tag and the commit it points to
- latest GitHub Release
- visible versioning in `VERSION`
- visible versioning in `README.md`

Do not treat any single one of those surfaces as authoritative by itself.

## 2. What counts as a release-worthy public delta

Create a new version only when the repository has a meaningful public-facing delta since the last tagged commit, for example:

- shipped code changed
- installer or bootstrap behavior changed
- installed global skill or automation behavior changed
- public template behavior changed
- public usage docs changed in a way that materially affects how another machine installs or uses the system
- packaging or release behavior changed in a way another user would need

Do **not** create a new version just because one of these happened:

- `kb/history/` changed
- private cards or candidates changed
- release notes wording changed for an already-correct release
- GitHub Release body needs cleanup
- a release page needs a title or formatting fix
- the same commit is being republished after an avoidable workflow mistake

Those cases should usually be treated as repair, reuse, or branch-only sync.

## 3. Same-commit duplicate guard

One source commit should normally correspond to one public version.

Before creating a new version:

- check whether `HEAD` already matches an existing tag
- check whether another existing tag already points to the intended commit

If the intended source commit is already tagged, do **not** create another patch number for the same source just to repair release metadata or presentation.

Instead:

- update the existing GitHub Release body if possible
- repair missing assets on the existing Release if the code boundary still matches
- or push the branch only when no new release object is needed

## 4. Repair vs new version

Use **repair existing release** when:

- the code boundary is still correct
- the tag already points at the intended commit
- only the GitHub Release object, release notes, or attached assets are incomplete

Use **new version** when:

- code changed since the last tag
- installer or packaging logic changed
- visible public version files must describe new source, not just repaired metadata
- the previous tag points at the wrong commit and you are not going to rewrite history

## 5. Sequence stateful steps strictly

The release sequence must be:

1. prepare release files
2. create the release commit
3. verify `HEAD`
4. create the annotated tag
5. verify the tag target locally
6. push branch
7. push tag
8. verify the remote tag target
9. create or update the GitHub Release

Do **not** create the commit and tag in parallel.

## 6. Small-change batching

Do not cut a fresh patch version for every tiny maintenance tweak when the public behavior is effectively unchanged.

Bias toward batching small publishable maintenance work into the next meaningful patch release, especially when:

- several tiny documentation or workflow adjustments are happening close together
- the public-facing user experience has not materially changed yet
- the only reason to publish would be “GitHub should be up to date”

In those cases, prefer:

- branch sync without new tag
- or waiting until the next real release-worthy delta accumulates

## 7. Version bump heuristics

- `patch`: real bug fix, installer fix, packaging fix, public workflow fix, or materially useful doc fix
- `minor`: meaningful capability expansion
- `major`: breaking or incompatible change

If unsure between “no release” and `patch`, choose **no release** unless another machine or a normal user would meaningfully notice the new behavior.

