# The pre-release branch name is the version source of truth

Repos in this fleet disagree about where a version lives: some keep it in a
plain file read by the build, some hardcode it in a build file, one keeps it in
*two* places that can drift, and several have no version anywhere. No tags
exist. A workflow that had to read a version file before it could branch would
therefore need per-repo configuration everywhere before it could act at all.

We decided that **`pre-release/<version>` — the branch name — is the record of
what version is being cooked.** Current version resolves as: highest
`origin/pre-release/*` → latest semver tag → a sole unambiguous version file →
otherwise `0.1.0`. Version files are written only when a repo opts in via
`.myway.toml`.

## Consequences

- The workflow runs zero-config on every repo, including ones with no version
  and ones with two that disagree.
- Branch names carry a plain semver core (`pre-release/1.3.0`) so `sort -V`
  orders them correctly. No `v` prefix, no `-alpha` suffix — the branch already
  *is* the pre-release.
- A repo's version file may lag behind its train until release, unless it opts
  in. This is deliberate: a stale literal is less harmful than a guessed one
  written into a build.
- Deleting a pre-release branch destroys the record. Trains should be merged
  and tagged at release, not pruned.
