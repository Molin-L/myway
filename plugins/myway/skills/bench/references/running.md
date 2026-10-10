# Running a session

## The harness contract

The harness runs **one rep** of one scenario against one variant checkout and prints **one JSON object of metrics as its last line on stdout**. Anything before that line is ignored, so build logs and progress output are fine. A non-zero exit records the rep as `error` with the stderr tail; running past `timeout_s` records it as `timeout`.

It reads the workload from the snapshot path (`{scenario}`), not from `scenarios/<id>.json`: the snapshot is the exact spec the trial is recorded against. It must report every metric the scenario lists, in the scenario's units.

Measure inside the harness, around the work, not around process start-up, unless start-up is what the scenario measures. Report latency percentiles from the samples the rep collected, not an average.

### The harness lives outside the variants

Keep the harness in `bench/` in the current tree, and have it drive the variant through `{workdir}` (run its binary, import its module, call its API). Then an old variant can run a scenario added after its commit: that is a backfill, and it needs no change to the variant. A harness inside each variant's code forks with every variant and cannot run anything newer than the variant.

If the variants expose different entry points, the harness adapts to each one; the scenario does not.

## Noise

Go over these with the user before a session whose numbers will decide something:

- **Same machine, quiet machine.** Close heavy apps, stop indexing and sync, plug in a laptop, and keep it at a steady temperature. The manifest records the load average at the start; a high one is a reason to discard.
- **Warmup is in the spec**, not chosen per run: caches, JIT, page cache, connection pools.
- **Interleaving is automatic.** Each round runs every variant once, rotating the order, so drift (thermal, background jobs) spreads across variants instead of landing on one.
- **The baseline runs every session.** Normalising each variant to the baseline from the same session cancels machine and day effects. Comparing absolute numbers across sessions is only safe on one quiet machine.
- **Enough reps.** If the interquartile ranges of two variants overlap, the difference is not established. Raise `reps` (a new scenario version) rather than reading the medians harder.
- **One session is one sample of the machine.** For a decision that matters, run two sessions on different days and check the ranking holds.

## Backfill

When a scenario or a new version arrives, older variants have no trials on it; `coverage` shows the gaps. Run them:

```sh
scripts/bench.py run --variants old-a,old-b --scenarios new-scenario
```

The baseline joins automatically, so the backfill is normalised in its own session. Never copy, scale, or estimate a number into a gap.

## Provisional runs

A variant with `"commit": null` runs the working tree. Its results carry the real HEAD and a dirty flag, and `evaluate` marks it `(provisional)`. Use it to iterate quickly. Before a result is reported as a finding, commit the code, register a pinned variant, and run that.

A pinned variant whose worktree is dirty (someone edited `.bench/worktrees/<id>`) is provisional too.

## Discarding a session

Bad sessions happen (a backup kicked in, the build was wrong). Delete the session's manifest and its result files in one commit whose message says why. Never edit the lines.
