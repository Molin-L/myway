# Versioning — pre-release trains

## The rule

**The pre-release branch name is the version source of truth.** Not a tag, not
a version file. ADR 0001 in the plugin's own repo records why.

Branch names carry a **plain semver core** — `pre-release/1.3.0`. No `v`
prefix, no `-alpha` suffix: the branch *is* the pre-release, so encoding
pre-release-ness in the version string would be saying it twice, and it breaks
`sort -V` ordering.

## Finding the latest train

```sh
git fetch --prune origin
git ls-remote --heads origin 'refs/heads/pre-release/*' \
  | sed 's|.*refs/heads/pre-release/||' \
  | sort -V | tail -1
```

`sort -V` is required, not `sort`. Lexically, `1.9.0` beats `1.10.0` — which
would silently branch off a stale train.

Read from **`origin`**, never from local branches; a local `pre-release/*` can
be arbitrarily old.

## When no train exists

Create one from the default branch with a **minor** bump.

1. Resolve the current version, first match wins:
   1. highest `origin/pre-release/*` *(none, by definition, in this branch of the logic)*
   2. latest semver tag — `git tag --sort=-v:refname | head -1`
   3. a version file, **only if exactly one exists** (see below)
   4. otherwise `0.1.0`
2. Take the semver core — `1.1.4-alpha.6` → `1.1.4`.
3. Bump minor — `1.1.4` → `1.2.0`, `0.2.0` → `0.3.0`.
4. `git push origin origin/<default>:refs/heads/pre-release/<bumped>`

**Always minor**, regardless of whether the triggering change is a feat, fix, or
chore. A train is named before its cargo is known: a type-derived rule gets
invalidated the moment a feature lands in a train named for a patch, and
renaming means retargeting every open change request.

## Version files

**Do not write version files by default.** Repos are inconsistent — some have
none, some have one, some have two that can drift. Guessing produces a wrong
version in a build.

Only sync when `.myway.toml` declares one:

```toml
[version]
file = "version.txt"
```

Then, as the first commit on the new train branch:

```
chore(release): bump to 0.3.0
```

When reading a version file for step 1.3 above, accept it only if the repo has
**exactly one** identifiable version source. If two disagree, or if the version
is computed rather than literal, fall through to `0.1.0` and note it.

## Why this survives inconsistent repos

| Situation | Behaviour |
|---|---|
| Version in a plain file | Read as fallback; written back only if declared in `.myway.toml` |
| Version hardcoded in a build file | Read as fallback; never rewritten |
| Two version sources that can drift | Neither trusted, neither written |
| No version anywhere | Train starts at `pre-release/0.1.0` |
