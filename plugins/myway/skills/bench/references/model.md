# The record model

## Terms

- **Session**: one sitting on one machine. One environment, one baseline, one plan. Its manifest is `sessions/<session_id>.json`.
- **Trial**: one variant on one scenario version within a session. `trial_id = <session_id>:<variant>:<scenario>`.
- **Rep**: one repetition inside a trial. One JSON line. Warmup reps are recorded too, flagged `warmup: true` with negative `rep`.

## Layout

```
bench/
  bench.json                         harness command, build, baseline, env probes
  variants.json                      the designs
  harness.sh                         (yours) runs one rep, prints metrics JSON
  scenarios/<id>.json                the current spec, `version` inside
  scenarios/.snapshots/<sha>.json    the exact spec each trial ran (written by run)
  suites/<id>.json                   which scenario versions are ranked together
  eval/<id>.json                     what "best" means
  sessions/<session_id>.json         one per sitting
  results/<scenario>/<session_id>.jsonl   one line per rep
.bench/worktrees/<variant>/          checkouts (gitignored)
```

Results are partitioned **by scenario id only**. The scenario version is an attribute of each trial, never a path segment. A new scenario adds a directory and touches nothing else; a new version of a scenario lands in the same directory, told apart by `scenario_version` and `scenario_sha`.

Commit everything under `bench/` except what is huge; raw results are the record.

## Comparability

Two trials are comparable when they have the **same `scenario_sha`**. `version` is the human label for a sha.

- The sha is SHA-256 of the spec as canonical JSON (sorted keys, no whitespace), **excluding** `version`, `description`, `notes`, `supersedes`. A typo fix in the description keeps the sha; any change to what is measured changes it.
- One `(scenario, version)` maps to exactly one sha. Two shas under one version means the spec was edited without a bump: `run` refuses, `check` errors.
- One sha under two versions means a bump with no change: `check` warns, because it splits comparable trials.
- The snapshot `scenarios/.snapshots/<sha>.json` lets any trial name the exact spec it ran, with no git archaeology.

## Files

### bench.json

```json
{
  "command": "{bench}/harness.sh {workdir} {scenario}",
  "build": "cargo build --release",
  "baseline": "lsm-mmap",
  "env_probes": ["rustc --version", "uname -r"],
  "worktrees": ".bench/worktrees"
}
```

`command` placeholders (each shell-quoted): `{bench}` bench dir, `{workdir}` the variant checkout, `{scenario}` the snapshot path, `{scenario_id}`, `{variant}`, `{rep}`, `{seed}`, `{params_json}`. The same values are in the environment as `BENCH_<NAME>`, plus `BENCH_SESSION` and `BENCH_WARMUP`. The command runs with the variant checkout as its working directory.

### variants.json

```json
[
  {"id": "lsm-mmap", "commit": "a1b2c3d", "factors": {"storage": "lsm", "io": "mmap"}, "notes": "current design"},
  {"id": "btree-direct", "commit": "e4f5a6b", "factors": {"storage": "btree", "io": "direct"}},
  {"id": "wip", "commit": null, "factors": {"storage": "lsm", "io": "direct"}}
]
```

`commit` is any rev; `run` resolves it to a full sha and records that. `null` means the working tree: provisional.

### scenarios/\<id\>.json

```json
{
  "id": "burst-write",
  "version": 2,
  "supersedes": "v1 used 2 clients; production sees 4",
  "description": "10k writes in 1 s bursts",
  "params": {"clients": 4, "duration_s": 60},
  "inputs": [{"path": "bench/data/burst-10k.bin", "sha256": "9f2c…"}],
  "seed": 42,
  "warmup": 3,
  "reps": 10,
  "timeout_s": 300,
  "metrics": {
    "p50_ms": {"unit": "ms"},
    "p99_ms": {"unit": "ms"},
    "throughput_ops": {"unit": "ops/s"},
    "peak_rss_mb": {"unit": "MB"}
  }
}
```

Required: `id`, `version`, `reps`, `metrics`. Every input file is pinned by sha256 and verified before a session starts. A rep that does not report every listed metric is recorded as an error.

### Result line

```json
{"session_id": "20261010-140210-3fa1", "trial_id": "20261010-140210-3fa1:lsm-mmap:burst-write",
 "variant": "lsm-mmap", "commit": "a1b2c3d…", "dirty": false,
 "scenario": "burst-write", "scenario_version": 2, "scenario_sha": "1c149c…",
 "rep": 3, "warmup": false, "status": "ok", "wall_s": 61.2, "ts": "2026-10-10T06:03:11+00:00",
 "metrics": {"p50_ms": 1.8, "p99_ms": 7.2, "throughput_ops": 51200, "peak_rss_mb": 310}}
```

`status` is `ok`, `error` (with `error`: exit code and stderr tail), or `timeout`. Failed reps stay in the file; the `failures` gate counts them.

### sessions/\<session_id\>.json

Written before the first rep and rewritten with `finished` and `failures` at the end: start time, baseline, the command and build, the environment (host, platform, CPU, core count, load average, and each `env_probes` output), each variant's resolved commit, dirty flag, provisional flag and factors, and each scenario's version, sha, warmup and reps.

### suites/\<id\>.json and eval/\<id\>.json

See [evaluation.md](evaluation.md).

## Invariants `check` enforces

- Each result sits in the directory named by its `scenario`.
- Each `scenario_sha` has a snapshot; each `session_id` has a manifest; each variant is in `variants.json`.
- One sha per `(scenario, version)`; the current spec at a version that has trials still hashes to that version's sha.
- A pinned variant ran at one commit only, and it is the commit `variants.json` pins.
- The baseline is a registered variant.
