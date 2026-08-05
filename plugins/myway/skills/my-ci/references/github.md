# GitHub specifics

## Files to place

| Template | Destination |
|---|---|
| `templates/github/ci.yml` | `.github/workflows/ci.yml` |
| `templates/github/release.yml` | `.github/workflows/release.yml` |
| `scripts/*.sh` | `ci/scripts/` (committed executable) |

## Concept mapping (GitLab → GitHub)

| GitLab | GitHub equivalent |
|---|---|
| MR pipeline (`merge_request_event`) | `on: pull_request` |
| "ship on merge into release/*" via merge-commit title | `pull_request: types: [closed]` + `if: merged == true` — native and exact |
| workflow rule blocking `X.Y.Z` tag pipelines | structural: tags pushed with `GITHUB_TOKEN` never fire workflows |
| `artifacts` + `needs` | `upload-artifact` / `download-artifact` + `needs:` |
| dotenv report | `source ./release.env` between steps (same job) |
| `allow_failure: true` | `continue-on-error: true` |
| CI/CD variables | repo secrets (`MYCI_NOTIFY_WEBHOOK`) and variables (`MYCI_NOTIFY_STYLE`) |
| `MYCI_PUSH_TOKEN` | not needed — `GITHUB_TOKEN` with `permissions: contents: write, pull-requests: write` |

## Required setup (cannot be scaffolded — tell the user)

- **Workflow permissions**: the templates declare `permissions:` inline; if the
  org restricts `GITHUB_TOKEN` to read-only, that inline block still wins for
  these workflows. If "Allow GitHub Actions to create and approve pull
  requests" is disabled org-wide, the back-merge PR creation will be refused —
  enable it or accept the warning-and-skip behavior.
- **Branch protection**: protect `main`/`master`, `pre-release/*`, and
  `release/*` with "require PR before merging" + the `build` and `test` checks.
  The merge permission on `release/*` is the deploy gate.
- **Auto-merge**: enable "Allow auto-merge" in repo settings, or the back-merge
  PR stays open unmerged (backmerge.sh warns and continues).
- **Optional secrets/variables**: `MYCI_NOTIFY_WEBHOOK` (secret),
  `MYCI_NOTIFY_STYLE` (variable).

## Sharp edges encoded in the template

- **Synthetic PR refs**: on `pull_request` events `GITHUB_REF_NAME` is
  `<n>/merge`, not a branch. `release.yml` therefore passes
  `MYCI_BRANCH: ${{ github.event.pull_request.base.ref }}` explicitly and
  checks out `base.ref` — lib.sh treats a pre-set `MYCI_BRANCH` as
  authoritative.
- **`fetch-depth: 0` everywhere**: tag discovery, changelog ranges, and
  back-merge diffs all need full history; the default shallow clone breaks
  them silently.
- **Tag filters are globs, not regex**: `'[0-9]*.[0-9]*.[0-9]*-*'` approximates
  the dev-tag pattern. It is deliberately loose — the strict check lives in the
  scripts, which is another reason logic stays out of YAML.
- **No double build**: `create_release_tag.sh` pushes tag `X.Y.Z` with the
  checkout's `GITHUB_TOKEN` credentials, and GITHUB_TOKEN-triggered events do
  not start workflows. Do not "fix" the tag push to use a PAT — that would
  re-introduce the double build.
- **Dev-tag artifacts**: `development_release` rebuilds via `build.sh` rather
  than handing off the `check` job's artifact — a simplicity trade-off (two
  small jobs, one workflow). If the build is expensive, convert it to
  upload/download-artifact like ci.yml does.
