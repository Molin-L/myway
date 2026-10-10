# Evaluation

Evaluation is computed from raw reps at read time and never stored in the results. Changing what "best" means re-scores existing data; it never needs a re-run.

## Suite

`bench/suites/<id>.json` pins the scenario versions that are ranked together:

```json
{"id": "core", "version": 2, "scenarios": {"burst-write": 2, "steady-read": 1, "cold-start": 1}}
```

Adding a scenario to the ranking, or moving to a new scenario version, is a new suite `version`. The old suite definition stays in git history and its leaderboard stays reproducible.

## Profile

`bench/eval/<id>.json`:

```json
{
  "id": "latency-first",
  "version": 1,
  "suite": "core",
  "normalize": "baseline",
  "require_full_coverage": true,
  "gates": {
    "failures": {"max": 0},
    "peak_rss_mb": {"max": 512}
  },
  "objectives": {
    "p99_ms": {"direction": "min", "weight": 0.5},
    "throughput_ops": {"direction": "max", "weight": 0.3},
    "peak_rss_mb": {"direction": "min", "weight": 0.2}
  }
}
```

- `gates`: hard limits. `failures` counts error and timeout reps; any other key is a metric whose median is checked per scenario. A variant that fails any gate on any scenario is excluded, however fast it is.
- `objectives`: what to optimise, with `direction` and `weight`. Weights are normalised to sum to 1.
- `normalize`: `baseline` (default) or `none`. See below.
- `require_full_coverage`: `true` (default) excludes a variant with no trials on any suite scenario. `false` ranks it on the scenarios it has, and the report must say so.

Write the profile before looking at results. A different priority is a new profile, or a new `version` of this one, and the report names the one it used.

## The computation

1. **Per trial**, the median of each metric over its ok, non-warmup reps.
2. **Normalisation** (`baseline`): divide each trial's median by the baseline's median **from the same session**. A variant that ran several sessions gets the geometric mean of its per-session ratios. A trial whose session has no baseline trial for that scenario gives no ratio.
3. **Orientation**: each ratio is turned so that greater than 1 is better than the baseline (a `min` objective takes the inverse).
4. **Across the suite**: geometric mean over scenarios, per objective. The geometric mean keeps a large scenario from outweighing a small one, and is the only mean for ratios.
5. **Gates**, on raw medians per scenario.
6. **Pareto front**: among qualified variants, those no other variant beats on every objective.
7. **Score**: the weighted geometric mean of the objective ratios. The baseline scores 1.
8. **Factor effects**: for each factor with more than one level among qualified variants, the geometric mean score of the variants at each level, with `n`.

With `normalize: none`, the per-objective value is the pooled raw median, the score is not relative to anything, and `evaluate` warns if the data spans hosts. Use it only for single-machine, single-session comparisons.

## Reading the result

- **The Pareto front first.** If more than one variant is on it, the weights decided the winner, and the report says which trade-off the weights chose (for example "btree-direct wins on p99 at the cost of 30% throughput"). A single-variant front means a winner under any weights.
- **A score difference under the noise is not a ranking.** Compare the interquartile ranges in `cells` (`p25`, `p75`) of the variants involved; if they overlap on the deciding objective, say the two are not separated, and suggest more reps or a second session.
- **Factor effects are associations, not causes**, unless the variants form a factorial design (every combination of levels present). With a handful of hand-picked variants, a factor level can look strong only because the variant that has it is good for another reason. Say how many variants back each level.
- **Excluded is a result.** Report every excluded variant with the gate or the missing scenario that excluded it.
- **Provisional is a caveat.** A provisional variant may lead the table; it is not a finding until a pinned variant reproduces it.

## Output

`evaluate` prints the ranking, exclusions, and factor effects as Markdown tables. `--json OUT` writes the same plus `cells`: one row per scenario and variant with the version, sha, session count, failures, and for each metric `median`, `p25`, `p75`, `n`, and `vs_baseline`. That file is the input for a `report`.
