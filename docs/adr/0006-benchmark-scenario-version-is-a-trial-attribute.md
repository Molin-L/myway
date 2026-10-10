# A benchmark scenario's version is an attribute of the trial

The `bench` skill compares designs and implementations, not parameter values,
on several factors at once, and the comparison has to survive the benchmark
growing: new scenarios, changed workloads, more variants. Numbers measured
against a workload that later changed are not comparable, and the usual way
this breaks is silently: someone edits the workload and the old results sit
next to the new ones.

We decided that **a scenario is an explicit spec whose version and content sha
are recorded on every trial, and results are partitioned by scenario id only.**
The version is never a path segment. Comparable means equal `scenario_sha`;
`version` is the human label for it.

## Consequences

- A new scenario adds `results/<id>/` and touches nothing else. A new version
  of a scenario writes to the same directory, told apart by the trial's
  attributes.
- With no directory boundary between versions, the reader enforces it:
  `evaluate` reads only the versions a suite pins, and refuses a version with
  more than one sha.
- The sha leaves out `version`, `description`, `notes`, and `supersedes`, so a
  descriptive edit does not split comparable trials, and any change to what is
  measured does. `run` refuses and `check` errors when a spec changed without a
  bump.
- Each spec a trial ran is snapshotted at `scenarios/.snapshots/<sha>.json`, so
  the exact workload behind any number is one file away, not a git search.
- The four records stay separate: scenario, variant (pinned to one commit,
  tagged with design factors), trial (raw reps, append-only), and evaluation
  profile (gates, objectives, weights). "Best" is computed at read time, so a
  new priority re-scores old data without a re-run.
- Specs are JSON, not YAML: the skill's script is standard library only, like
  the other skills here, and the target machines have Python 3.9 without a YAML
  or TOML parser.
