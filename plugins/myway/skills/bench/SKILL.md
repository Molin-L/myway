---
name: bench
description: Benchmark competing designs or implementations against explicit, versioned scenarios, and pick the best one on several factors. Scenarios are fixed specs whose version and content sha are recorded on every trial; variants are pinned to commits and tagged with their design factors; results are raw reps, partitioned by scenario, never edited; "best" is a separate, versioned evaluation profile (gates, then Pareto front, then weighted score, then factor effects). Use when the user says "benchmark", "bench", "compare these designs/implementations", "which approach is faster/better", "run the benchmark", "add a scenario", "add a variant", "rank the variants", or wants performance or quality numbers that must stay comparable over time. Do NOT use for tuning a parameter sweep of one design, for a one-off `time` of a command, or for profiling a single hot path.
---

# Bench

A benchmark here answers one question: **which design or implementation is best, on workloads defined well enough that the answer still holds next month.** It keeps four records apart, because they change at different speeds:

| Record | Answers | Changes |
|---|---|---|
| **Scenario** | Under what workload? | Rarely, and only by bumping its `version` |
| **Variant** | Which design? | Each new idea; a variant is pinned to one commit |
| **Trial** | What happened when variant V ran scenario S in session X? | Only appended |
| **Evaluation profile** | What does "best" mean? | When priorities change; re-scores old data |

The full model, the file formats, and the invariants are in [references/model.md](references/model.md). Read it before the first benchmark in a repo.

Paths are relative to this skill directory. Under Claude Code that is `${CLAUDE_PLUGIN_ROOT}/skills/bench/`.

| File | Contents |
|---|---|
| `scripts/bench.py` | `init`, `sha`, `run`, `check`, `coverage`, `evaluate` (standard library only) |
| [references/model.md](references/model.md) | Session, trial, rep; every file's schema; versioning rules |
| [references/running.md](references/running.md) | The harness contract, noise control, backfill, provisional runs |
| [references/evaluation.md](references/evaluation.md) | Profiles and suites; gates, normalization, Pareto, score, factor effects; reading the output |

## The arc

### 0. Locate or initialise

Look for `bench/bench.json` at the repo root. If it is missing, run `scripts/bench.py init`, then settle with the user, one question at a time and only for what the repo does not tell you:

- **The harness**: the command that runs one rep and prints one JSON object of metrics as its last stdout line. Put it under `bench/` in the current tree, not in the variant's code, so old commits can run new scenarios ([running.md](references/running.md#the-harness-lives-outside-the-variants)).
- **The build** for a variant checkout, if any.
- **The baseline variant**: the reference every session re-runs. Usually the current design.

### 1. Define or change a scenario

A scenario is `bench/scenarios/<id>.json`: id, version, params, pinned inputs (path plus sha256), seed, warmup, reps, timeout, and the metrics with units. Everything the workload depends on goes in the spec; a workload that can drift is not a scenario.

- **New scenario**: `version: 1`. Nothing else in the tree moves; its results get their own `results/<id>/` directory.
- **Changed workload** (params, inputs, reps, metrics, seed): bump `version`. Never edit a spec that has trials without bumping; `run` refuses and `check` errors.
- **Descriptive edit only** (`description`, `notes`): no bump. Those fields are outside the sha.

Run `scripts/bench.py sha <id>` to see the version and sha the next trials will carry.

### 2. Register variants

Add each design to `bench/variants.json` with its commit and its **factors**: the design decisions it embodies (`{"storage": "lsm", "io": "mmap"}`). Factors are what make the comparison explainable later; ask the user for them if the variant names do not make them obvious. Use the same factor names and levels across variants.

A variant id names one commit forever. New code is a new id. `"commit": null` runs the working tree and marks every result provisional; use it only while iterating, and register a pinned variant before drawing conclusions.

### 3. Run a session

```sh
scripts/bench.py run --variants A,B,C --scenarios X,Y --dry-run   # show the plan and env
scripts/bench.py run --variants A,B,C --scenarios X,Y
```

The baseline is added automatically. `run` checks each spec against prior trials, verifies input hashes, checks out each pinned variant into `.bench/worktrees/<id>`, builds it, writes the session manifest, snapshots each spec by sha, runs the warmups, then interleaves reps (rotating the variant order each round) and appends one line per rep as it finishes. Before a long run, go over the noise checklist in [running.md](references/running.md#noise) with the user.

### 4. Check

```sh
scripts/bench.py check
scripts/bench.py coverage [--suite S]
```

Fix every error before evaluating. `coverage` shows the reps per variant and scenario version; a gap is filled by running that variant on that scenario (a backfill), never by estimating.

### 5. Evaluate

A suite (`bench/suites/<id>.json`) pins which scenario versions are ranked together. A profile (`bench/eval/<id>.json`) names the suite and says what "best" means. Agree the profile with the user before reading results, so the definition of "best" is not fitted to the data.

```sh
scripts/bench.py evaluate --profile P --json reports/bench-<profile>.json
```

The order is fixed: gates disqualify; the Pareto front shows the real trade-offs; the weighted score orders them; factor effects say which decisions mattered. Read [evaluation.md](references/evaluation.md#reading-the-result) before you explain a result.

### 6. Report

Tell the user, in this order: the profile and suite (with the scenario versions), the excluded variants and why, the Pareto front, the ranking with its scores, the factor effects, and anything provisional, single-session, or within noise. For a shareable page, hand the `--json` output to the `report` skill (kicker `Benchmark`); its Method section takes the session manifests (host, env probes, commits) and the scenario shas.

## Rules

- **Never edit a result line, a snapshot, or a session manifest.** A bad session is excluded by deleting its files in a commit that says why, not by changing numbers.
- **Never change a scenario in place.** Bump `version`. Comparable means equal `scenario_sha`.
- **Never re-point a variant id at new code.** New code, new id.
- **Never fill a missing cell.** No zero, no average, no estimate. Run it, or rank with `require_full_coverage: false` and say so.
- **Never tune the profile to the outcome.** A new priority is a new profile version, and the report names the profile it used.
- **Never override reps or warmup on the command line.** They are part of the scenario.
