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

## Weekly goals

`/weekly-goal` asks three questions, one at a time — what to achieve, what it
contributes to, how you will know it is done — dedupes the answer against the
active milestones of your GitLab group, shows the full milestone body, and
creates or updates it on your say-so.

`/weekly-goal-gap` measures the distance. It resolves a window (default: the
trailing 7 days) and the goals in scope, gathers evidence from the milestone's
linked issues first and your own activity second, judges every unchecked
criterion with a citation, ticks the met ones, prints the gap, and opens issues
for the rest in the right projects — linked to the milestone, with
`blocks` / `is_blocked_by` relations where the evidence shows a dependency.

Reads go through `scripts/gitlab_activity.py` (standard library, `glab`
transport); writes go through `glab api`. One-time setup: the goal group, see
[config reference](plugins/myway/skills/weekly-goal/references/config.md).

## Reports

Two skills turn results into one self-contained HTML file. They share the
figure rules (titled axes with units, numbered captions, labelled reference
lines, `null` for missing data) and differ in style and in how much they ask
of the author.

`report` is the everyday page, in the house style: system sans, a floating
outline on the left built from the `h2`–`h4` headings (a drawer on narrow
screens), a light/dark toggle in the top bar, stat tiles, callouts, tables,
and D3 charts drawn through a fixed token palette. `scripts/report.py new`
scaffolds the file and `lint` checks the theme bootstrap, the outline, ids,
heading levels, figure captions and axis units, colour literals, and remote
resources other than the D3 CDN. The reasons:
[ADR 0002](docs/adr/0002-report-tokens-come-from-the-validated-palette.md)
and [ADR 0007](docs/adr/0007-formal-reports-are-a-separate-skill.md).

`formal-report` is the page to share outside the team or keep as a record, in
the research reading style (adapted from numbers.sfinterface.com): a serif
title in a centred column, roman-numbered sections, an "On this page" outline
on the right, a fixed component vocabulary (lede, stats, callouts, timeline,
cards, decisions, footnotes), KaTeX math, Vega-Lite charts themed from the
tokens, and `#12` / `!34` / `~56` references linked to the forge. Inter, KaTeX,
and Vega are vendored and inlined, so it opens offline and in a private
network. Every claim stands on a fact with a checkable source, the prose is
plain, and the body ends with a Method section; `lint` refuses an edited style
or runtime, any remote resource, and colours in chart specs, and warns on a
stat no section backs and on machine-prose tells. The reasons:
[ADR 0003](docs/adr/0003-reports-share-the-research-reading-style.md),
[ADR 0004](docs/adr/0004-reports-load-nothing-from-the-network.md),
[ADR 0005](docs/adr/0005-report-claims-stand-on-facts.md), and
[ADR 0007](docs/adr/0007-formal-reports-are-a-separate-skill.md).

## Benchmarks

`bench` compares designs or implementations, not parameter values, on several
factors, against workloads defined well enough that the answer still holds
after the benchmark grows. Four records stay separate: **scenarios** (explicit
JSON specs, versioned, every input pinned by sha256), **variants** (one commit
each, tagged with the design factors they embody), **trials** (raw reps,
append-only, under `results/<scenario>/`), and **evaluation profiles** (gates,
objectives, weights). The scenario version is an attribute of every trial,
never a path segment; comparable means equal spec sha.
`scripts/bench.py run` checks out each variant, runs warmups, interleaves
reps, and re-runs the baseline every session; `check` refuses a spec edited
without a version bump or a variant re-pointed at new code; `evaluate` applies
gates, then the Pareto front, then the weighted score, then factor effects.
The reasons: [ADR 0006](docs/adr/0006-benchmark-scenario-version-is-a-trial-attribute.md).

## Readiness audits

`repo-readiness-audit` checks one commit of a repo against its PRD and goal. It
answers two questions: can this commit go to staging, and where does the real
system differ from the team's model? It suits an AI-built repo, because it does
not accept the builder's statements as evidence.

Separate agents do the work with limited views: a ledger extractor, an
acceptance test author, forward and reverse tracers, a test integrity auditor,
a readiness auditor, and a cognition reviewer. `scripts/audit.py` records each
test run and derives verification, evidence level (E0 to E4), goal status, and
the verdict for each stage, so that no agent can claim them. A human approves
the ledger and decides each agent choice that the PRD did not specify. The
report is `REPORT.md`: the verdict, a requirement matrix, a gap register, a
reverse trace, a test integrity audit, production readiness, and a Believes /
Decided / Unknown delta. The reasons:
[ADR 0008](docs/adr/0008-audit-status-comes-from-the-script.md).

## Test audits

`test-audit` controls test bloat in an agent-built codebase. It controls two
points. A new test must name the wrong behavior that it rejects. A deleted test
must have evidence that no protection goes with it.

`scripts/test_audit.py` runs each test alone and records its production lines.
`prove` applies a wrong-behavior patch in a temporary worktree: the test must
pass before the patch and fail after it, for the expected reason. `check`
simulates the whole deletion batch. `gate` compares the before and after
snapshots of a test-only commit. It fails on an undeclared loss of coverage, a
removed test with no evidence, an added test with no proof, or a new surviving
mutant. Separate agents discover and judge the candidates, and a human approves
each change to a contract test. It has configs for C++, Go, Rust, and Python.
The reasons: [ADR 0009](docs/adr/0009-test-deletion-needs-evidence.md).

To apply the authoring gate in a target repo, add one line to its `CLAUDE.md` /
`AGENTS.md`:

> Writing, reviewing, or removing tests always goes through the
> `myway:test-audit` skill.

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
| [`plugins/myway/skills/my-ci/SKILL.md`](plugins/myway/skills/my-ci/SKILL.md) | Cross-forge CI scaffolding |
| [`plugins/myway/skills/cog/SKILL.md`](plugins/myway/skills/cog/SKILL.md) | `/cog init` · `/cog update` — cognition docs: your model of a system, kept as `docs/cognition/` |
| [`plugins/myway/skills/weekly-goal/SKILL.md`](plugins/myway/skills/weekly-goal/SKILL.md) | Weekly goals as GitLab group milestones, and the gap check |
| [`plugins/myway/skills/report/SKILL.md`](plugins/myway/skills/report/SKILL.md) | House-style HTML reports: one template, light/dark toggle, D3 charts on a fixed palette |
| [`plugins/myway/skills/formal-report/SKILL.md`](plugins/myway/skills/formal-report/SKILL.md) | Formal HTML reports in the research reading style: claims on sourced facts, KaTeX, Vega-Lite, everything inlined |
| [`plugins/myway/skills/bench/SKILL.md`](plugins/myway/skills/bench/SKILL.md) | Design benchmarks: versioned scenarios, pinned variants, raw trials, gates → Pareto → score |
| [`plugins/myway/skills/repo-readiness-audit/SKILL.md`](plugins/myway/skills/repo-readiness-audit/SKILL.md) | Readiness audits: one commit against its PRD, with evidence levels, stage verdicts, a gap register, and a cognition delta |
| [`plugins/myway/skills/test-audit/SKILL.md`](plugins/myway/skills/test-audit/SKILL.md) | Test audits: an authoring gate for new tests, and evidence-gated removal of low-value tests |
| [`CONTEXT.md`](CONTEXT.md) | Glossary |
| [`docs/adr/`](docs/adr/) | Decision records |

This repo is a marketplace: further workflows land as additional skills under
`plugins/myway/skills/`, or as sibling plugins under `plugins/`.
