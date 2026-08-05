---
name: my-ci
description: Scaffold a release-flow CI/CD pipeline into a repo, on GitLab CI or GitHub Actions (or both), from this skill's templates and forge-agnostic scripts. Use when the user asks to set up CI, add a pipeline, scaffold GitHub Actions or a .gitlab-ci.yml, port CI between GitLab and GitHub, or wire up release automation. Do NOT use for debugging an existing pipeline failure, or for one-off workflow edits unrelated to this model.
---

# my-ci — scaffold the pipeline

This skill installs a proven pipeline shape — release-flow with pre-release
trains, distilled from a production GitLab pipeline — into a target repo. It is
the CI counterpart of `implement-change`: that skill drives the branches and
requests; this pipeline checks and ships them.

The model in one line: **checks run pre-merge on every MR/PR; merging the
promote request into `release/X.Y.Z` is the ship event** (tag `X.Y.Z` →
package → forge release → back-merge into the default branch), with dev
releases via `X.Y.Z-<suffix>` tags. Read
[references/pipeline-model.md](references/pipeline-model.md) before scaffolding
— every non-obvious guard in the templates is explained there.

All pipeline logic lives in shell scripts under `ci/scripts/`; the YAML on
both forges is thin glue calling the same scripts. `scripts/lib.sh` normalizes
GitLab CI and GitHub Actions into one `MYCI_*` environment, which is what
makes one script set serve both forges.

## The arc

### 1. Survey the target repo

- Forge(s): from `git remote get-url origin` — GitHub, GitLab (incl.
  self-hosted), or both. When the user says "both", install both template
  sets; the scripts are shared either way.
- Build system: what `build.sh`/`test.sh` inference would pick (CMake, Cargo,
  uv/pytest, npm, Go, Make). Honor `.myway.toml` `[verify]` commands when
  present — CI must agree with local verification.
- Existing CI: if `.gitlab-ci.yml` or `.github/workflows/` already exists,
  **stop and show the user what is there** before overwriting anything.

### 2. Vendor the scripts

Copy every file from this skill's `scripts/` into the repo at `ci/scripts/`,
executable (`chmod +x`). Copy all of them even for a single-forge repo — the
set is one unit, and the second forge becomes a two-file addition later.

### 3. Place the templates

| Forge | From | To |
|---|---|---|
| GitLab | `templates/gitlab/gitlab-ci.yml` | `.gitlab-ci.yml` |
| GitLab | `templates/gitlab/stages/*.yml` | `.gitlab/stages/` |
| GitHub | `templates/github/ci.yml` | `.github/workflows/ci.yml` |
| GitHub | `templates/github/release.yml` | `.github/workflows/release.yml` |

### 4. Customize the marked sections — and only those

Every intended edit point is a `CUSTOMIZE` banner:

- `build.sh`, `test.sh`, `package.sh` — replace inference with the repo's real
  commands when inference would guess wrong. Keep the contracts (build output
  under `build/`, tests emit `junit.xml` when possible, artifacts into
  `release/`).
- `IMAGE` (GitLab) / `runs-on` + optional `container:` (GitHub).
- `publish.sh` only if artifacts must land somewhere other than the
  forge-native store (GitHub release assets / GitLab generic packages).

Do **not** edit the workflow rules, ship-detection guards, or `needs` DAGs
without reading the forge reference — the sharp edges are documented in
[references/gitlab.md](references/gitlab.md) and
[references/github.md](references/github.md). If you add a check job, wire it
into `development_release`'s `needs` (GitLab) — a dev tag can otherwise ship
before the check finishes.

### 5. Verify the scaffold

- `bash -n ci/scripts/*.sh` — every script must parse.
- Lint the YAML with whatever is available (`glab ci lint`, `actionlint`,
  `yq`/`python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))"`).
- Dry-run the customized scripts locally where cheap (`ci/scripts/build.sh`
  and `test.sh` run fine outside CI — `lib.sh` degrades to `MYCI_FORGE=local`).

### 6. Report the forge setup the user must do by hand

Scaffolding cannot set tokens or protections. End by listing, concretely for
their forge, what remains: GitLab → `MYCI_PUSH_TOKEN` + protected
branches/tags; GitHub → branch protection, auto-merge toggle, optional
notification secret. The checklists live in the forge references — copy the
relevant one into your report, don't just link it.

### 7. Land it

If the user asked to commit/ship the scaffold, hand off to the
`implement-change` skill (issue → branch off the pre-release train → CR).
Otherwise leave the files in the working tree and stop.

## References

| File | Contents |
|---|---|
| [references/pipeline-model.md](references/pipeline-model.md) | The flow, the principles (build-once, pre-merge gate, ship-on-merge, idempotency), the script layer |
| [references/gitlab.md](references/gitlab.md) | File placement, required variables/protections, GitLab sharp edges (merge-title guard, dotenv-via-needs, tag block) |
| [references/github.md](references/github.md) | Concept mapping, permissions, GitHub sharp edges (synthetic PR refs, GITHUB_TOKEN no-retrigger, glob tag filters) |
