# myway

Development workflows, my way — a Claude Code plugin.

One instruction (*"implement this plan"*, *"fix this bug"*, *"bump easytier to
2.4.5"*) produces an issue, a branch off the latest pre-release train,
conventional commits, a verified change request, and a green pipeline. No
approval prompts in between.

It also picks up work you already wrote: *"create an MR"*, *"open a PR"*,
*"push this and raise a merge request"* join the same arc late — commits,
local verification, change request, pipeline escort — instead of a bare
`glab mr create` that nobody watches.

## The arc

```
issue #42                    full plan verbatim — the spec of record
  └─ pre-release/0.3.0       latest train, or created from main with a minor bump
      └─ feat/42-order-router      in .worktrees/42-order-router/
           ├─ feat(router): …      Refs: #42
           ├─ fix(router): …       Refs: #42
           └─ local build + tests  always, CI or not
                └─ change request  → pre-release/0.3.0
                     └─ escort     CODE failure → fix ×3 max
                                   INFRA failure → report, never touch code
                          └─ green, MR open, yours to merge
```

## Design decisions

- **Uniform arc.** `feat`, `fix`, and `chore` all get an issue. The branch
  convention structurally requires an id.
- **The branch name is the version.** Not a tag, not a version file — repos in
  this fleet have zero, one, or two conflicting version sources. See
  [ADR 0001](docs/adr/0001-pre-release-branch-name-is-version-truth.md).
- **Always verify locally.** Most repos have no CI, so this is the only
  definition of "done" that holds everywhere.
- **Escort is infra-aware.** A self-hosted runner going down presents as an
  eternally queued pipeline. Fixing code in response would be fixing the wrong
  thing.
- **Stops before merge.** Merge is the one step that is awkward to undo once
  others branch off the train.
- **Never strands work.** Blocked runs still push and still open a draft change
  request explaining why. If you walked away, the outcome has to be where you
  will look.

## Making it fire

Skill selection is by description match, so the description names the phrases
people actually type — "create an MR", "open a PR", "watch the pipeline" — not
only "implement this". Where the workflow is law, one line in the target
repo's `CLAUDE.md` / `AGENTS.md` removes the remaining guesswork:

> Creating a merge or pull request, or watching a pipeline, always goes
> through the `myway:implement-change` skill.

## Install

**Claude Code**

```
/plugin marketplace add Molin-L/myway
/plugin install myway
```

**OpenAI Codex** — the skills follow the same [Agent Skills](https://agentskills.io)
standard, and Codex follows symlinked skill folders. Clone this repo, then link
each skill into your user scope:

```sh
git clone https://github.com/Molin-L/myway
for s in myway/plugins/myway/skills/*/; do
  ln -s "$(cd "$s" && pwd)" ~/.agents/skills/"$(basename "$s")"
done
```

(Working *inside* this repo needs no install — Codex picks the skills up from
the committed `.agents/skills/` symlinks.)

## Configuration

None required. `.myway.toml` at a repo root resolves the two things that cannot
be inferred safely — which version file to write, and how to build and test.
See [config reference](plugins/myway/skills/implement-change/references/config.md).

## Contents

| Path | |
|---|---|
| [`plugins/myway/skills/implement-change/SKILL.md`](plugins/myway/skills/implement-change/SKILL.md) | The workflow |
| [`references/`](plugins/myway/skills/implement-change/references/) | Forge commands, versioning, commits, escort, config |
| [`CONTEXT.md`](CONTEXT.md) | Glossary |
| [`docs/adr/`](docs/adr/) | Decision records |

This repo is a marketplace: further workflows land as additional skills under
`plugins/myway/skills/`, or as sibling plugins under `plugins/`.
