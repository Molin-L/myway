# Forge — detection, issues, change requests

## Detecting the forge

**From `origin`, and only from `origin`:**

```sh
git remote get-url origin
```

| Contains | Forge | CLI |
|---|---|---|
| `github.com` | GitHub | `gh` |
| `gitlab.` (incl. self-hosted) | GitLab | `glab` |

**Never infer the forge from which CI file exists.** A repo can carry a
`.gitlab-ci.yml` while pushing to GitHub — the config is dead, and treating it
as evidence of a GitLab pipeline means waiting forever for a pipeline that
cannot exist. The same project may also be mirrored on both forges; `origin` is
where the work actually goes.

Verify authentication before acting: `gh auth status` / `glab auth status`. If
the relevant CLI is not authenticated, stop and say so — do not fall back to
the other forge.

## Terminology

**Change request** is the canonical term in this skill, because the workflow
spans both forges. Render it as the forge's own word when talking to the user
or writing bodies: **pull request** on GitHub, **merge request** on GitLab.

## Issue numbers

Use the number the forge displays and that `#42` resolves to:

- **GitHub** — the issue number.
- **GitLab** — the **`iid`** (project-scoped), *not* the global `id`. Getting
  this wrong produces branch names that reference an unrelated issue in another
  project.

## Creating the issue

Write the body to a temp file first — it is long and contains markdown that
does not survive shell quoting well.

### GitHub

```sh
gh issue create --title "<title>" --body-file /tmp/issue-body.md
```

Prints the issue URL on success; the trailing path segment is the number:

```sh
url=$(gh issue create --title "$title" --body-file /tmp/issue-body.md)
id=${url##*/}
```

### GitLab

`glab issue create` has no `--body-file`; pass the description inline and skip
the editor and the confirmation prompt.

```sh
url=$(glab issue create --title "$title" --description "$(cat /tmp/issue-body.md)" --no-editor --yes)
id=${url##*/}
```

If the URL parse is ever ambiguous, read the id back from the API instead:

```sh
glab api "projects/:id/issues?state=opened&per_page=1" --jq '.[0].iid'
```

## Creating the change request

Target the **pre-release train**, never the default branch. Push the branch
first (`git push -u origin <branch>`).

### GitHub

```sh
gh pr create \
  --base "pre-release/<version>" \
  --head "<type>/<id>-<brief>" \
  --title "<conventional-style title>" \
  --body-file /tmp/cr-body.md
```

Add `--draft` when the run is blocked (see the failure contract in `SKILL.md`).

### GitLab

```sh
glab mr create \
  --target-branch "pre-release/<version>" \
  --source-branch "<type>/<id>-<brief>" \
  --title "<conventional-style title>" \
  --description "$(cat /tmp/cr-body.md)" \
  --no-editor --yes
```

Add `--draft` when blocked.

## Body template

```md
## Summary
What changed and why, in a few lines.

## Acceptance criteria
- [x] Copied from the issue, ticked as actually met.

## Verification
`ctest --test-dir build` — 41 passed, 0 failed.

Refs: #42
```

`Refs:`, not `Closes:` — see `commits.md`.

## Default branch

Do not assume `main`. Resolve it:

```sh
git symbolic-ref --quiet refs/remotes/origin/HEAD | sed 's|.*/||' \
  || git remote show origin | sed -n 's/.*HEAD branch: //p'
```

Fall back to whichever of `main` or `master` exists on the remote.
