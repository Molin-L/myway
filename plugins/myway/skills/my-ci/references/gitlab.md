# GitLab specifics

## Files to place

| Template | Destination |
|---|---|
| `templates/gitlab/gitlab-ci.yml` | `.gitlab-ci.yml` |
| `templates/gitlab/stages/*.yml` | `.gitlab/stages/` |
| `scripts/*.sh` | `ci/scripts/` (committed executable) |

`.gate_rules`, `.release_rules`, and `.myci_setup` live in the root file;
`!reference` resolves across included files because GitLab merges all includes
before resolving, so stage files can use them freely.

## Required setup (cannot be scaffolded — tell the user)

**CI/CD variables** (Settings → CI/CD → Variables, masked):

| Variable | Purpose |
|---|---|
| `MYCI_PUSH_TOKEN` | Project access token. Scopes: `api` + `write_repository`. Its role needs push rights on protected `release/*` branches **and protected `X.Y.Z` tags**, plus merge rights on the default branch (for the back-merge auto-merge). Without it, tag creation falls back to the API with `CI_JOB_TOKEN` and the back-merge is skipped with a warning. |
| `MYCI_NOTIFY_WEBHOOK` | Optional. Notification webhook URL. |
| `MYCI_NOTIFY_STYLE` | Optional. `generic` (default) / `feishu` / `slack`. |

**Protected branches/tags** (Settings → Repository):

- Protect `release/*`: merge = the release-owning role, push = no one (plus
  the token's user). The merge permission on `release/*` **is** the deploy
  gate — that is why `production_release` carries no `environment:`.
- Protect `pre-release/*` and the default branch: merge via MR only.
- Protect tags `*.*.*` so only the CI token can create production tags.

## Sharp edges encoded in the template

- **Ship detection**: `release/*` ships only when `CI_COMMIT_TITLE` matches
  `/ into .release\/X.Y.Z./` — the promote-MR merge commit. Do not "simplify"
  this to `CI_COMMIT_BEFORE_SHA`: it reports all-zeros on a branch's first
  push, on MR pipelines, and permanently on some instances. Squash-merging the
  promote MR rewrites the title GitLab generates — keep the default merge
  commit on promote MRs (squash is fine on feature MRs).
- **Production-tag block**: the first workflow rule blocks `v?X.Y.Z` tag
  pipelines. The tag was created *by* the ship pipeline; building it again
  would be a double build of identical content.
- **dotenv flows only via `needs`**: any job that reads `RELEASE_VERSION`
  must list `create_tag` in `needs` with `artifacts: true`.
- **`needs` cannot point to a later stage**: keep any job that
  `development_release` needs in a stage before `release`.
- **after_script has fresh state**: it re-runs `chmod +x ci/scripts/*.sh`
  because execute bits from `before_script` don't survive into `after_script`
  on all executors.
- **Retry policy**: `retry` on `runner_system_failure` / `stuck_or_timeout`
  only — infrastructure flake retries, code failures don't.
