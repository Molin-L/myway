# The pipeline model

Distilled from a production GitLab pipeline (afe, BYCI-based) and generalized
to run on both GitLab CI and GitHub Actions. The branching model is the same
release-flow the `implement-change` skill drives, so the two skills compose:
`implement-change` produces the branches and requests; `my-ci` is the pipeline
that checks and ships them.

## The flow

```
feature/*  ──MR/PR──▶  pre-release/X.Y.Z        checks (the pre-merge gate)
pre-release/X.Y.Z ──promote MR/PR──▶ release/X.Y.Z    same checks, on the promote request
release/X.Y.Z   branch creation                 NOTHING (an empty cut must not ship)
release/X.Y.Z   promote request MERGES          SHIP: tag X.Y.Z → package → release → back-merge
X.Y.Z           tag (CI-created)                NOTHING (already built on the ship push)
X.Y.Z-<suffix>  tag (pushed by a human)         checks inline, then ship as a pre-release
dev / develop   push                            checks only, never publish
release/X.Y.Z ──back-merge MR/PR──▶ default     checks (it is just another MR/PR)
```

The version lives in the branch name (`release/X.Y.Z` → tag `X.Y.Z`), per ADR
0001: no version file needs to exist for the pipeline to ship correctly.
Production tags are **plain semver with no leading `v`** — the tag namespace
regex still tolerates `v?` so legacy tags stay blocked from re-building.

## Principles

**Build once.** The pipeline compiles exactly once (`build:check` / `build`),
and everything downstream consumes that artifact via `artifacts` + `needs`
(GitLab) or `upload-artifact`/`download-artifact` (GitHub). A job that rebuilds
is a bug: it wastes runners and can ship something other than what was tested.

**Checks are pre-merge; the ship path only ships.** Every check runs on the
request that *feeds* a branch, never on the branch after the merge. By the time
content reaches `release/X.Y.Z` it has passed the gate twice (feature MR, then
the promote MR), so the ship pipeline carries zero check jobs — it tags,
packages, releases, back-merges. The one exception is the dev-release tag: no
request precedes a pushed tag, so its checks run inline and gate the ship
through `needs`. **Every check job that runs on a dev tag must be listed in
`development_release`'s needs** — a missing entry lets the release ship before
that check finishes (this exact incident happened upstream).

**Ship on merge-in, not on branch events.** A release branch being created, or
directly pushed to, must ship nothing. GitLab cannot express "merged into"
directly, so the workflow rules key on the merge-commit *title* (`... into
'release/X.Y.Z'`) — not `CI_COMMIT_BEFORE_SHA`, which is all-zeros on first
pushes and MR pipelines. GitHub has the native primitive: `pull_request:
types: [closed]` + `merged == true`.

**Production tags are CI-managed and never rebuild.** The ship pipeline creates
tag `X.Y.Z` itself. On GitLab, the workflow rules explicitly block plain-semver
tag pipelines (no double build). On GitHub the same guarantee is structural:
events triggered with `GITHUB_TOKEN` don't fire workflows.

**Idempotent ship scripts.** A retried CI job must not fail on its own earlier
progress: tag creation, release creation, and the back-merge all treat
"already exists" as success.

**Back-merge is best-effort, and gated on the tag.** After a production ship,
an MR/PR syncs `release/X.Y.Z` back into the default branch. Every non-happy
path (no diff, already open, conflicts, missing token) warns and exits 0, and
the job additionally carries `allow_failure` / `continue-on-error` — a green
release pipeline never goes red because of the back-merge.

It runs in its own job, and that job runs even when the ship job failed
(`when: always` in the `sync` stage on GitLab, `!cancelled()` on GitHub). A
ship is not atomic: by the time `publish.sh` runs, `create_release_tag.sh` has
pushed `X.Y.Z` and the forge release exists. That history is permanent, so a
registry refusing an artifact afterwards must not leave the default branch
behind a released tag. `backmerge.sh` makes the actual decision — it skips
unless the release tag exists, so a ship that failed *before* tagging syncs
nothing.

On GitHub, where the native auto-merge queue needs `allow_auto_merge` plus a
protection rule or ruleset that a free private repo cannot have, `lib.sh`
watches the back-merge PR's own checks and merges it when they are green,
rather than leaving it open for a human.

**Notifications are optional and never gate.** `notify.sh` no-ops without
`MYCI_NOTIFY_WEBHOOK` and always exits 0; it sits inside `cmd || (notify;
exit 1)` handlers so the real failure status is preserved.

## The script layer

All logic lives in `ci/scripts/*.sh`; the YAML on both forges is thin glue
calling the same scripts. `lib.sh` normalizes the two CI environments into
`MYCI_*` variables and dispatches forge-specific operations (tag push, release
creation, merged-request lookup, back-merge, publish) on `MYCI_FORGE` — which
is what makes one script set serve both forges, plus plain local execution for
debugging.

| Script | Role | Customize? |
|---|---|---|
| `lib.sh` | forge compat layer + helpers | no |
| `build.sh` | the one build; output under `build/` | **yes** |
| `test.sh` | tests against `build/`; emits `junit.xml` | **yes** |
| `package.sh` | assemble `release/` | **yes** |
| `publish.sh` | upload `release/` (forge-native default) | if artifacts live elsewhere |
| `gen_changelog.sh` | conventional-commit changelog | no |
| `create_release_tag.sh` | version from branch → tag + changelog + dotenv | no |
| `create_release.sh` | forge release from tag + notes | no |
| `backmerge.sh` | release → default sync request, merged when green | no |
| `notify.sh` | optional webhook (generic/feishu/slack) | no |

Version/data flow on the production path:
`create_release_tag.sh` writes `release.env` (`RELEASE_VERSION`, `RELEASE_TAG`)
→ GitLab carries it as a dotenv report through `needs` (dotenv does **not**
flow by stage order); GitHub jobs `source ./release.env` between steps.
