#!/usr/bin/env python3
"""Record and evaluate design benchmarks. Standard library only.

A benchmark compares variants (designs or implementations, each pinned to a
commit) on scenarios (explicit, versioned workloads). Results are kept as raw
reps, partitioned by scenario id; the scenario version is an attribute of each
trial, never part of the path. See references/model.md.

Layout (under the bench dir, default <repo>/bench):
  bench.json                      harness command, build, baseline, probes
  variants.json                   [{id, commit, factors, notes}]
  scenarios/<id>.json             current spec, with a `version` field
  scenarios/.snapshots/<sha>.json exact spec each trial ran against
  suites/<id>.json                {id, version, scenarios: {id: version}}
  eval/<id>.json                  evaluation profile (gates, objectives)
  sessions/<session>.json         one sitting: host, env, baseline, plan
  results/<scenario>/<session>.jsonl   one line per rep

Subcommands:
  init                    scaffold the bench dir in the current repo
  sha SCENARIO            print the scenario's version and content sha
  run --variants A,B --scenarios X,Y [--dry-run]
                          one session: build each variant at its commit,
                          run warmups then interleaved reps, append raw lines
  check                   lint specs and results (exit 1 on any error)
  coverage [--suite S]    variant x scenario@version matrix of ok reps
  evaluate --profile P [--json OUT]
                          gates -> Pareto front -> weighted score -> factor
                          effects, on the scenario versions the suite pins

Global flag: --dir PATH   bench dir (default: <git toplevel>/bench)
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import platform
import shlex
import socket
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path

# Fields that describe a scenario without changing what it measures. Editing
# them keeps the sha, so a typo fix does not split comparable trials.
DESCRIPTIVE = ("version", "description", "notes", "supersedes")
REQUIRED_SCENARIO = ("id", "version", "reps", "metrics")


class BenchError(Exception):
    pass


# --------------------------------------------------------------------------
# paths and loading


def repo_root() -> Path:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise BenchError("not inside a git repository")
    return Path(out.stdout.strip())


def bench_dir(args) -> Path:
    return Path(args.dir).resolve() if args.dir else repo_root() / "bench"


def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise BenchError(f"missing {path}")
    except json.JSONDecodeError as e:
        raise BenchError(f"{path}: invalid JSON: {e}")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")


def scenario_sha(spec: dict) -> str:
    body = {k: v for k, v in spec.items() if k not in DESCRIPTIVE}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


def load_scenario(bdir: Path, sid: str) -> dict:
    spec = load_json(bdir / "scenarios" / f"{sid}.json")
    missing = [k for k in REQUIRED_SCENARIO if k not in spec]
    if missing:
        raise BenchError(f"scenario {sid}: missing {', '.join(missing)}")
    if spec["id"] != sid:
        raise BenchError(f"scenario file {sid}.json has id {spec['id']!r}")
    return spec


def load_variants(bdir: Path) -> dict:
    vs = load_json(bdir / "variants.json")
    out = {}
    for v in vs:
        if v["id"] in out:
            raise BenchError(f"variant {v['id']} defined twice")
        out[v["id"]] = v
    return out


def iter_results(bdir: Path):
    """Yield (path, lineno, record) for every result line."""
    root = bdir / "results"
    if not root.is_dir():
        return
    for path in sorted(root.glob("*/*.jsonl")):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                yield path, n, json.loads(line)
            except json.JSONDecodeError as e:
                raise BenchError(f"{path}:{n}: invalid JSON: {e}")


def short(sha: str | None) -> str:
    return (sha or "-")[:12]


# --------------------------------------------------------------------------
# init


CONFIG_TEMPLATE = {
    "command": "{bench}/harness.sh {workdir} {scenario}",
    "build": None,
    "baseline": None,
    "env_probes": [],
    "worktrees": ".bench/worktrees",
}


def cmd_init(args) -> int:
    bdir = bench_dir(args)
    for sub in ("scenarios/.snapshots", "suites", "eval", "sessions", "results"):
        (bdir / sub).mkdir(parents=True, exist_ok=True)
    created = []
    if not (bdir / "bench.json").exists():
        write_json(bdir / "bench.json", CONFIG_TEMPLATE)
        created.append("bench.json")
    if not (bdir / "variants.json").exists():
        write_json(bdir / "variants.json", [])
        created.append("variants.json")
    root = repo_root()
    gi = root / ".gitignore"
    entry = CONFIG_TEMPLATE["worktrees"].split("/")[0] + "/"
    lines = gi.read_text().splitlines() if gi.exists() else []
    if entry not in lines:
        with gi.open("a") as f:
            f.write(("\n" if lines and lines[-1] else "") + entry + "\n")
        created.append(f".gitignore += {entry}")
    print(f"bench dir: {bdir}")
    for c in created:
        print(f"  created {c}")
    return 0


# --------------------------------------------------------------------------
# sha


def cmd_sha(args) -> int:
    bdir = bench_dir(args)
    spec = load_scenario(bdir, args.scenario)
    print(json.dumps({"scenario": spec["id"], "version": spec["version"],
                      "sha": scenario_sha(spec)}))
    return 0


# --------------------------------------------------------------------------
# run


def git(*a, cwd=None) -> str:
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True,
                          text=True, check=True).stdout.strip()


def sh(cmd: str, cwd: Path, env=None, timeout=None):
    return subprocess.run(cmd, shell=True, cwd=cwd, env=env, timeout=timeout,
                          capture_output=True, text=True)


def env_fingerprint(cfg: dict, root: Path) -> dict:
    fp = {
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
    }
    try:
        if sys.platform == "darwin":
            fp["cpu"] = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True).stdout.strip() or fp["cpu"]
        elif Path("/proc/cpuinfo").exists():
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    fp["cpu"] = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    try:
        fp["loadavg"] = [round(x, 2) for x in os.getloadavg()]
    except OSError:
        pass
    probes = {}
    for p in cfg.get("env_probes") or []:
        r = sh(p, root)
        probes[p] = (r.stdout or r.stderr).strip()
    fp["probes"] = probes
    return fp


def verify_inputs(spec: dict, root: Path) -> None:
    for inp in spec.get("inputs") or []:
        path = root / inp["path"]
        if not path.is_file():
            raise BenchError(f"scenario {spec['id']}: input {inp['path']} missing")
        want = inp.get("sha256")
        if not want:
            raise BenchError(f"scenario {spec['id']}: input {inp['path']} has no sha256")
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != want:
            raise BenchError(
                f"scenario {spec['id']}: input {inp['path']} sha256 is "
                f"{h.hexdigest()}, spec pins {want}. Changed input = new version.")


def snapshot(bdir: Path, spec: dict, sha: str) -> Path:
    path = bdir / "scenarios" / ".snapshots" / f"{sha}.json"
    if path.exists():
        old = load_json(path)
        if scenario_sha(old) != sha:
            raise BenchError(f"snapshot {path} does not hash to its name")
    else:
        write_json(path, spec)
    return path


def prepare_variant(v: dict, cfg: dict, root: Path, dry: bool) -> dict:
    """Return {workdir, commit, dirty, provisional} for a variant."""
    if v.get("commit") is None:
        commit = git("rev-parse", "HEAD", cwd=root)
        dirty = bool(git("status", "--porcelain", cwd=root))
        return {"workdir": root, "commit": commit, "dirty": dirty,
                "provisional": True}
    commit = git("rev-parse", "--verify", f"{v['commit']}^{{commit}}", cwd=root)
    wt = root / cfg.get("worktrees", ".bench/worktrees") / v["id"]
    if not dry:
        if wt.exists():
            head = git("rev-parse", "HEAD", cwd=wt)
            if head != commit:
                git("checkout", "--detach", commit, cwd=wt)
        else:
            wt.parent.mkdir(parents=True, exist_ok=True)
            git("worktree", "add", "--detach", str(wt), commit, cwd=root)
    dirty = (not dry) and bool(git("status", "--porcelain", cwd=wt))
    return {"workdir": wt, "commit": commit, "dirty": dirty,
            "provisional": dirty}


def render(template: str, values: dict) -> str:
    return template.format(**{k: shlex.quote(str(v)) for k, v in values.items()})


def run_rep(cfg, bdir, spec, snap, variant, prep, rep, warmup, session_id):
    values = {
        "bench": bdir, "workdir": prep["workdir"], "scenario": snap,
        "scenario_id": spec["id"], "variant": variant["id"], "rep": rep,
        "seed": spec.get("seed", 0),
        "params_json": json.dumps(spec.get("params", {}), sort_keys=True),
    }
    cmd = render(cfg["command"], values)
    env = dict(os.environ)
    env.update({f"BENCH_{k.upper()}": str(v) for k, v in values.items()})
    env["BENCH_SESSION"] = session_id
    env["BENCH_WARMUP"] = "1" if warmup else "0"
    rec = {"status": "ok", "metrics": {}}
    t0 = time.monotonic()
    try:
        r = sh(cmd, prep["workdir"], env=env, timeout=spec.get("timeout_s"))
    except subprocess.TimeoutExpired:
        rec["status"] = "timeout"
        rec["wall_s"] = round(time.monotonic() - t0, 3)
        return rec
    rec["wall_s"] = round(time.monotonic() - t0, 3)
    if r.returncode != 0:
        rec["status"] = "error"
        rec["error"] = f"exit {r.returncode}: {r.stderr.strip()[-500:]}"
        return rec
    lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
    try:
        metrics = json.loads(lines[-1]) if lines else None
        if not isinstance(metrics, dict):
            raise ValueError("last stdout line is not a JSON object")
    except ValueError as e:
        rec["status"] = "error"
        rec["error"] = f"harness output: {e}"
        return rec
    missing = [m for m in spec["metrics"] if m not in metrics]
    if missing:
        rec["status"] = "error"
        rec["error"] = f"harness did not report {', '.join(missing)}"
    rec["metrics"] = metrics
    return rec


def cmd_run(args) -> int:
    bdir = bench_dir(args)
    root = repo_root()
    cfg = load_json(bdir / "bench.json")
    if not cfg.get("command"):
        raise BenchError("bench.json has no command")
    variants = load_variants(bdir)
    vids = [v for v in args.variants.split(",") if v]
    baseline = cfg.get("baseline")
    if not baseline:
        raise BenchError("bench.json has no baseline variant")
    if baseline not in vids:
        vids.insert(0, baseline)
    for v in vids:
        if v not in variants:
            raise BenchError(f"unknown variant {v} (add it to variants.json)")
    specs = [load_scenario(bdir, s) for s in args.scenarios.split(",") if s]

    # Fail before any rep runs if a spec was edited without a version bump.
    known = sha_by_version(bdir)
    plan = []
    for spec in specs:
        sha = scenario_sha(spec)
        prior = known.get((spec["id"], spec["version"]))
        if prior and prior != {sha}:
            raise BenchError(
                f"scenario {spec['id']} v{spec['version']} changed since it "
                f"last ran ({', '.join(short(s) for s in prior)} -> {short(sha)}). "
                f"Bump `version`.")
        verify_inputs(spec, root)
        plan.append((spec, sha))

    session_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    preps = {v: prepare_variant(variants[v], cfg, root, args.dry_run) for v in vids}

    manifest = {
        "session_id": session_id,
        "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "baseline": baseline,
        "env": env_fingerprint(cfg, root),
        "command": cfg["command"],
        "build": cfg.get("build"),
        "variants": {v: {"commit": p["commit"], "dirty": p["dirty"],
                         "provisional": p["provisional"],
                         "factors": variants[v].get("factors", {})}
                     for v, p in preps.items()},
        "scenarios": {s["id"]: {"version": s["version"], "sha": sha,
                                "warmup": s.get("warmup", 0), "reps": s["reps"]}
                      for s, sha in plan},
        "order": "warmup per variant, then rounds rotating variant order",
    }
    if args.dry_run:
        print(json.dumps(manifest, indent=2, default=str))
        return 0

    if cfg.get("build"):
        for v, p in preps.items():
            print(f"build {v} @ {short(p['commit'])}", file=sys.stderr)
            r = sh(cfg["build"], p["workdir"])
            if r.returncode != 0:
                raise BenchError(f"build failed for {v}:\n{r.stderr[-2000:]}")
    write_json(bdir / "sessions" / f"{session_id}.json", manifest)

    failures = 0
    for spec, sha in plan:
        snap = snapshot(bdir, spec, sha)
        out = bdir / "results" / spec["id"] / f"{session_id}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        schedule = [(v, -1 - i, True) for i in range(spec.get("warmup", 0))
                    for v in vids]
        for rnd in range(spec["reps"]):
            k = rnd % len(vids)
            for v in vids[k:] + vids[:k]:
                schedule.append((v, rnd, False))
        with out.open("a") as f:
            for v, rep, warm in schedule:
                p = preps[v]
                rec = run_rep(cfg, bdir, spec, snap, variants[v], p, rep, warm,
                              session_id)
                line = {
                    "session_id": session_id,
                    "trial_id": f"{session_id}:{v}:{spec['id']}",
                    "variant": v, "commit": p["commit"], "dirty": p["dirty"],
                    "scenario": spec["id"], "scenario_version": spec["version"],
                    "scenario_sha": sha, "rep": rep, "warmup": warm,
                    "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    **rec,
                }
                f.write(json.dumps(line, sort_keys=True) + "\n")
                f.flush()
                failures += rec["status"] != "ok"
                tag = "warm" if warm else f"rep {rep}"
                print(f"{spec['id']} v{spec['version']} {v:>16} {tag:>7} "
                      f"{rec['status']}", file=sys.stderr)

    manifest["finished"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    manifest["failures"] = failures
    write_json(bdir / "sessions" / f"{session_id}.json", manifest)
    print(json.dumps({"session_id": session_id, "failures": failures}))
    return 0


# --------------------------------------------------------------------------
# check


def sha_by_version(bdir: Path) -> dict:
    seen: dict = {}
    for _, _, r in iter_results(bdir):
        seen.setdefault((r["scenario"], r["scenario_version"]), set()).add(r["scenario_sha"])
    return seen


def cmd_check(args) -> int:
    bdir = bench_dir(args)
    errors, warnings = [], []
    variants = load_variants(bdir)
    cfg = load_json(bdir / "bench.json")
    if cfg.get("baseline") and cfg["baseline"] not in variants:
        errors.append(f"baseline {cfg['baseline']} is not in variants.json")

    current = {}
    for path in sorted((bdir / "scenarios").glob("*.json")):
        try:
            spec = load_scenario(bdir, path.stem)
        except BenchError as e:
            errors.append(str(e))
            continue
        current[spec["id"]] = (spec["version"], scenario_sha(spec))

    by_version = sha_by_version(bdir)
    versions_by_sha: dict = {}
    for (sid, ver), shas in by_version.items():
        if len(shas) > 1:
            errors.append(f"{sid} v{ver} ran under {len(shas)} specs "
                          f"({', '.join(short(s) for s in shas)}): edited without a bump")
        for s in shas:
            versions_by_sha.setdefault((sid, s), set()).add(ver)
        if sid in current and current[sid][0] == ver and current[sid][1] not in shas:
            errors.append(f"scenarios/{sid}.json is v{ver} but no longer matches "
                          f"the v{ver} trials: bump `version`")
    for (sid, s), vers in versions_by_sha.items():
        if len(vers) > 1:
            warnings.append(f"{sid} versions {sorted(vers)} share spec {short(s)}: "
                            f"a bump with no change splits comparable trials")

    commits: dict = {}
    snaps = bdir / "scenarios" / ".snapshots"
    sessions = {p.stem for p in (bdir / "sessions").glob("*.json")}
    for path, n, r in iter_results(bdir):
        where = f"{path.relative_to(bdir)}:{n}"
        if path.parent.name != r.get("scenario"):
            errors.append(f"{where}: scenario {r.get('scenario')} in {path.parent.name}/")
        if not (snaps / f"{r['scenario_sha']}.json").exists():
            errors.append(f"{where}: no snapshot for spec {short(r['scenario_sha'])}")
        if r["session_id"] not in sessions:
            errors.append(f"{where}: no session manifest {r['session_id']}")
        v = variants.get(r["variant"])
        if v is None:
            errors.append(f"{where}: variant {r['variant']} is not in variants.json")
        elif v.get("commit") is not None:
            commits.setdefault(r["variant"], set()).add(r["commit"])
    for vid, cs in commits.items():
        if len(cs) > 1:
            errors.append(f"variant {vid} ran at {len(cs)} commits: a variant is "
                          f"pinned; new code is a new variant id")
        want = variants[vid]["commit"]
        try:
            want = git("rev-parse", "--verify", f"{want}^{{commit}}", cwd=bdir)
        except subprocess.CalledProcessError:
            warnings.append(f"variant {vid}: commit {want} not found in this clone")
            continue
        if cs and want not in cs:
            errors.append(f"variant {vid}: variants.json pins {short(want)} but "
                          f"trials ran at {', '.join(short(c) for c in cs)}")

    for e in errors:
        print(f"error: {e}")
    for w in warnings:
        print(f"warning: {w}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


# --------------------------------------------------------------------------
# coverage


def latest_versions(bdir: Path) -> dict:
    out = {}
    for path in (bdir / "scenarios").glob("*.json"):
        spec = load_json(path)
        out[spec["id"]] = spec["version"]
    return out


def load_suite(bdir: Path, sid: str) -> dict:
    suite = load_json(bdir / "suites" / f"{sid}.json")
    if not suite.get("scenarios"):
        raise BenchError(f"suite {sid} lists no scenarios")
    return suite


def cmd_coverage(args) -> int:
    bdir = bench_dir(args)
    pins = (load_suite(bdir, args.suite)["scenarios"] if args.suite
            else latest_versions(bdir))
    counts: dict = {}
    for _, _, r in iter_results(bdir):
        if r["warmup"] or r["status"] != "ok":
            continue
        if pins.get(r["scenario"]) != r["scenario_version"]:
            continue
        key = (r["variant"], r["scenario"])
        counts[key] = counts.get(key, 0) + 1
    variants = list(load_variants(bdir))
    cols = [f"{s}@v{v}" for s, v in sorted(pins.items())]
    print("| variant | " + " | ".join(cols) + " |")
    print("|---" * (len(cols) + 1) + "|")
    for v in variants:
        cells = [str(counts.get((v, s), "—")) for s in sorted(pins)]
        print(f"| {v} | " + " | ".join(cells) + " |")
    return 0


# --------------------------------------------------------------------------
# evaluate


def geomean(xs):
    xs = [x for x in xs if x is not None and x > 0]
    return math.exp(sum(math.log(x) for x in xs) / len(xs)) if xs else None


def quartiles(xs):
    if len(xs) < 2:
        return xs[0], xs[0]
    q = statistics.quantiles(xs, n=4, method="inclusive")
    return q[0], q[2]


def cmd_evaluate(args) -> int:
    bdir = bench_dir(args)
    prof = load_json(bdir / "eval" / f"{args.profile}.json")
    suite = load_suite(bdir, prof["suite"])
    pins = suite["scenarios"]
    objectives = prof.get("objectives") or {}
    gates = prof.get("gates") or {}
    if not objectives:
        raise BenchError(f"profile {args.profile} has no objectives")
    normalize = prof.get("normalize", "baseline")
    full = prof.get("require_full_coverage", True)
    variants = load_variants(bdir)
    sessions = {p.stem: load_json(p) for p in (bdir / "sessions").glob("*.json")}

    # (scenario, variant, session) -> {"ok": {metric: [..]}, "failed": n}
    trials: dict = {}
    shas: dict = {}
    for _, _, r in iter_results(bdir):
        if r["warmup"] or pins.get(r["scenario"]) != r["scenario_version"]:
            continue
        shas.setdefault(r["scenario"], set()).add(r["scenario_sha"])
        t = trials.setdefault((r["scenario"], r["variant"], r["session_id"]),
                              {"ok": {}, "failed": 0})
        if r["status"] != "ok":
            t["failed"] += 1
            continue
        for m, x in r["metrics"].items():
            if isinstance(x, (int, float)):
                t["ok"].setdefault(m, []).append(float(x))
    for sid, s in shas.items():
        if len(s) > 1:
            raise BenchError(f"{sid} v{pins[sid]} has trials under {len(s)} specs; "
                             f"run `check`")

    hosts = {sessions[k[2]]["env"]["host"] for k in trials if k[2] in sessions}
    notes = []
    if normalize == "none" and len(hosts) > 1:
        notes.append(f"normalize=none across {len(hosts)} hosts: absolute numbers "
                     f"from different machines are pooled")

    # Per scenario x variant: raw stats (pooled reps) and baseline ratios.
    cells: dict = {}
    for (sid, vid, sess), t in trials.items():
        c = cells.setdefault((sid, vid), {"reps": {}, "failed": 0, "ratios": {},
                                          "sessions": []})
        c["failed"] += t["failed"]
        c["sessions"].append(sess)
        for m, xs in t["ok"].items():
            c["reps"].setdefault(m, []).extend(xs)
        base = sessions.get(sess, {}).get("baseline")
        bt = trials.get((sid, base, sess))
        if normalize == "baseline" and bt:
            for m in objectives:
                if t["ok"].get(m) and bt["ok"].get(m):
                    b = statistics.median(bt["ok"][m])
                    if b:
                        c["ratios"].setdefault(m, []).append(
                            statistics.median(t["ok"][m]) / b)

    table = []
    for (sid, vid), c in sorted(cells.items()):
        row = {"scenario": sid, "version": pins[sid], "sha": short(next(iter(shas[sid]))),
               "variant": vid, "sessions": len(set(c["sessions"])),
               "failed": c["failed"], "metrics": {}}
        for m, xs in c["reps"].items():
            q1, q3 = quartiles(xs)
            row["metrics"][m] = {"median": statistics.median(xs), "p25": q1,
                                 "p75": q3, "n": len(xs)}
            if m in c["ratios"]:
                row["metrics"][m]["vs_baseline"] = geomean(c["ratios"][m])
        table.append(row)

    rank = []
    for vid, v in variants.items():
        res = {"variant": vid, "factors": v.get("factors", {}), "gates": [],
               "objectives": {}, "missing": []}
        for sid in pins:
            c = cells.get((sid, vid))
            if not c or not c["reps"]:
                res["missing"].append(sid)
                continue
            for m, rule in gates.items():
                if m == "failures":
                    val = c["failed"]
                elif m in c["reps"]:
                    val = statistics.median(c["reps"][m])
                else:
                    res["gates"].append(f"{sid}: {m} not reported")
                    continue
                if "max" in rule and val > rule["max"]:
                    res["gates"].append(f"{sid}: {m} {val:g} > {rule['max']:g}")
                if "min" in rule and val < rule["min"]:
                    res["gates"].append(f"{sid}: {m} {val:g} < {rule['min']:g}")
        if not res["missing"] or not full:
            for m, o in objectives.items():
                per = []
                for sid in pins:
                    c = cells.get((sid, vid))
                    if not c:
                        continue
                    if normalize == "baseline":
                        r = geomean(c["ratios"].get(m, []))
                    else:
                        r = statistics.median(c["reps"][m]) if c["reps"].get(m) else None
                    if r:
                        per.append(r if o["direction"] == "max" else 1 / r)
                res["objectives"][m] = geomean(per)
        res["provisional"] = any(
            sessions.get(c_sess, {}).get("variants", {}).get(vid, {}).get("provisional")
            for sid in pins for c_sess in (cells.get((sid, vid)) or {}).get("sessions", []))
        res["qualified"] = (not res["gates"] and (not res["missing"] or not full)
                            and all(res["objectives"].get(m) for m in objectives))
        if res["qualified"]:
            wsum = sum(o.get("weight", 1) for o in objectives.values())
            res["score"] = math.exp(sum(
                o.get("weight", 1) / wsum * math.log(res["objectives"][m])
                for m, o in objectives.items()))
        rank.append(res)

    q = [r for r in rank if r["qualified"]]
    for r in q:
        r["pareto"] = not any(
            all(o["objectives"][m] >= r["objectives"][m] for m in objectives)
            and any(o["objectives"][m] > r["objectives"][m] for m in objectives)
            for o in q if o is not r)
    q.sort(key=lambda r: -r["score"])

    effects: dict = {}
    for r in q:
        for f, level in r["factors"].items():
            effects.setdefault(f, {}).setdefault(str(level), []).append(r["score"])
    effects = {f: {lv: {"score": geomean(xs), "n": len(xs)} for lv, xs in lv_.items()}
               for f, lv_ in effects.items() if len(lv_) > 1}

    out = {
        "profile": {"id": prof.get("id", args.profile), "version": prof.get("version")},
        "suite": {"id": suite.get("id", prof["suite"]), "version": suite.get("version"),
                  "scenarios": pins},
        "normalize": normalize, "objectives": objectives, "gates": gates,
        "hosts": sorted(hosts), "notes": notes,
        "ranking": q, "excluded": [r for r in rank if not r["qualified"]],
        "effects": effects, "cells": table,
    }
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, indent=2) + "\n")
    print_evaluation(out)
    return 0


def fmt(x, nd=3):
    return "—" if x is None else f"{x:.{nd}g}"


def print_evaluation(out: dict) -> None:
    p, s = out["profile"], out["suite"]
    pins = ", ".join(f"{k}@v{v}" for k, v in s["scenarios"].items())
    print(f"## {p['id']} v{p['version']} on suite {s['id']} v{s['version']} ({pins})")
    print(f"normalize: {out['normalize']}; score > 1 beats the baseline"
          if out["normalize"] == "baseline" else "normalize: none")
    for n in out["notes"]:
        print(f"note: {n}")
    objs = list(out["objectives"])
    print("\n| rank | variant | score | pareto | " + " | ".join(objs) + " |")
    print("|---" * (4 + len(objs)) + "|")
    for i, r in enumerate(out["ranking"], 1):
        name = r["variant"] + (" (provisional)" if r["provisional"] else "")
        print(f"| {i} | {name} | {fmt(r['score'])} | "
              f"{'yes' if r['pareto'] else ''} | "
              + " | ".join(fmt(r["objectives"][m]) for m in objs) + " |")
    for r in out["excluded"]:
        why = r["gates"] or ([f"missing {', '.join(r['missing'])}"] if r["missing"]
                             else ["no baseline ratio for an objective"])
        print(f"excluded {r['variant']}: {'; '.join(why)}")
    if out["effects"]:
        print("\n| factor | level | score | n |\n|---|---|---|---|")
        for f, lv in out["effects"].items():
            for level, e in sorted(lv.items(), key=lambda kv: -(kv[1]["score"] or 0)):
                print(f"| {f} | {level} | {fmt(e['score'])} | {e['n']} |")


# --------------------------------------------------------------------------


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", help="bench dir (default <git toplevel>/bench)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p = sub.add_parser("sha")
    p.add_argument("scenario")
    p = sub.add_parser("run")
    p.add_argument("--variants", required=True, help="comma-separated ids")
    p.add_argument("--scenarios", required=True, help="comma-separated ids")
    p.add_argument("--dry-run", action="store_true")
    sub.add_parser("check")
    p = sub.add_parser("coverage")
    p.add_argument("--suite")
    p = sub.add_parser("evaluate")
    p.add_argument("--profile", required=True)
    p.add_argument("--json")
    args = ap.parse_args(argv)
    try:
        return {"init": cmd_init, "sha": cmd_sha, "run": cmd_run,
                "check": cmd_check, "coverage": cmd_coverage,
                "evaluate": cmd_evaluate}[args.cmd](args)
    except BenchError as e:
        print(f"bench: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
