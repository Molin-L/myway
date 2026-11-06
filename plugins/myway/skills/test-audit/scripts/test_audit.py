#!/usr/bin/env python3
"""Evidence for a test audit: per-test signals, proofs, and a deletion gate.

Agents give judgment. This script gives status.

  collect  Run each test alone. Record status, time, and production lines.
  prove    Apply a wrong-behavior patch in a temporary worktree. The named test
           must pass before the patch and fail after it, for the expected reason.
  check    Derive ready or blocked for each deletion candidate.
  gate     Compare the before and after snapshots of a test-only commit.

The commands use the standard library only. See references/schema.md.
"""
import argparse
import collections
import concurrent.futures
import datetime
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile
import time

CONFIG_REQUIRED = ("list", "run", "pass_pattern", "source", "test_paths")
CANDIDATE_REQUIRED = ("test", "path", "action", "pattern", "detects", "stronger_proof",
                      "non_test_callers", "history", "unlocks", "risk", "validation")
ACTIONS = ("delete", "merge", "rewrite")
PATTERNS = ("no_assertion", "tautology", "asserts_mock", "self_derived_expected",
            "duplicate_contract", "copied_inventory", "source_grep", "private_shape",
            "seam_only", "dead_code_only", "false_negative_control", "misleading_name",
            "implementation_coupled")


def die(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


def shell(command, cwd, env=None, timeout=None, stdout_only=False):
    """Run a shell command. Return (exit code or None on timeout, output).

    With stdout_only, stderr appears in the output only after a failure.
    """
    process = subprocess.Popen(
        command, shell=True, cwd=cwd, env={**os.environ, **(env or {})}, text=True,
        errors="replace", stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if stdout_only else subprocess.STDOUT,
        start_new_session=True)
    try:
        output, errors = process.communicate(timeout=timeout)
        if process.returncode and errors:
            output += errors
        return process.returncode, output
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        output, errors = process.communicate()
        return None, output + (errors or "")


def git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", str(repo), *args], text=True, errors="replace",
                            capture_output=True)
    if check and result.returncode:
        die(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result


def repo_root(path):
    return pathlib.Path(git(path, "rev-parse", "--show-toplevel").stdout.strip()).resolve()


def require_clean(repo):
    if git(repo, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        die("tracked files have changes. Commit them first, so that evidence binds to one commit")


def head(repo):
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def tail(text, count=30):
    return "\n".join(text.splitlines()[-count:])


def load_json(path, label):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except FileNotFoundError:
        die(f"{label} is missing: {path}")
    except json.JSONDecodeError as error:
        die(f"{label} is not valid JSON: {path}: {error}")


def load_config(directory):
    config = load_json(directory / "config.json", "config")
    missing = [key for key in CONFIG_REQUIRED if not config.get(key)]
    if missing:
        die(f"config.json needs: {', '.join(missing)}")
    re.compile(config["pass_pattern"])
    config.setdefault("build", "")
    config.setdefault("strip_prefix", "")
    config.setdefault("inline_test_marker", "")
    config.setdefault("timeout", 600)
    return config


def config_sha(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]


def is_test_path(config, path):
    return any(fnmatch.fnmatch(path, pattern) for pattern in config["test_paths"])


def is_source_path(config, path):
    return any(fnmatch.fnmatch(path, pattern) for pattern in config["source"])


def marker_line(config, repo, path, rev=None):
    """Return the first line of an inline test module, or None."""
    marker = config["inline_test_marker"]
    if not marker:
        return None
    if rev:
        result = git(repo, "show", f"{rev}:{path}", check=False)
        text = result.stdout if result.returncode == 0 else ""
    else:
        try:
            text = (repo / path).read_text(errors="replace")
        except OSError:
            return None
    for number, line in enumerate(text.splitlines(), 1):
        if marker in line:
            return number
    return None


def parse_coverage(text, config, repo):
    """Parse LCOV or a Go cover profile. Return {path: set(covered production lines)}."""
    raw = collections.defaultdict(set)
    if text.startswith("mode:"):
        for line in text.splitlines()[1:]:
            match = re.fullmatch(r"(.+):(\d+)\.\d+,(\d+)\.\d+ \d+ (\d+)", line.strip())
            if match and int(match[4]) > 0:
                raw[match[1]].update(range(int(match[2]), int(match[3]) + 1))
    else:
        current = None
        for line in text.splitlines():
            if line.startswith("SF:"):
                current = line[3:].strip()
            elif line.startswith("DA:") and current:
                number, count = line[3:].split(",")[:2]
                if int(float(count)) > 0:
                    raw[current].add(int(number))
    covered = {}
    for path, lines in raw.items():
        if config["strip_prefix"] and path.startswith(config["strip_prefix"]):
            path = path[len(config["strip_prefix"]):]
        if os.path.isabs(path):
            try:
                path = str(pathlib.Path(path).resolve().relative_to(repo))
            except ValueError:
                continue
        path = os.path.normpath(path)
        if is_test_path(config, path) or not is_source_path(config, path):
            continue
        boundary = marker_line(config, repo, path)
        kept = {line for line in lines if boundary is None or line < boundary}
        if kept:
            covered[path] = kept
    return covered


def run_one(config, root, test_id, scratch):
    """Run one test alone. Return (status, reason, seconds, coverage, log)."""
    out = pathlib.Path(scratch) / (hashlib.sha256(test_id.encode()).hexdigest()[:16] + ".cov")
    started = time.monotonic()
    code, log = shell(config["run"], root, {"TEST_ID": test_id, "TEST_OUT": str(out)},
                      config["timeout"])
    seconds = round(time.monotonic() - started, 3)
    if code is None:
        return "timeout", "the test did not finish", seconds, {}, log
    if code:
        return "fail", f"exit code {code}", seconds, {}, log
    if not re.search(config["pass_pattern"], log, re.M):
        return "invalid", "exit code 0, but the output does not match pass_pattern", seconds, {}, log
    if not out.exists():
        return "invalid", "the run command did not write $TEST_OUT", seconds, {}, log
    return "pass", "", seconds, parse_coverage(out.read_text(errors="replace"), config, root), log


def build(config, root):
    if not config["build"]:
        return 0, ""
    return shell(config["build"], root, timeout=config["timeout"])


def line_keys(coverage):
    return {f"{path}:{line}" for path, lines in coverage.items() for line in lines}


def snapshot_union(snapshot, skip=()):
    covered = set()
    for test_id, record in snapshot["tests"].items():
        if record["status"] == "pass" and test_id not in skip:
            covered |= line_keys(record["lines"])
    return covered


def cmd_collect(args):
    repo, directory = repo_root(args.repo), args.dir.resolve()
    config = load_config(directory)
    require_clean(repo)
    code, output = build(config, repo)
    if code != 0:
        die(f"build failed:\n{tail(output)}")
    code, output = shell(config["list"], repo, timeout=config["timeout"], stdout_only=True)
    if code != 0:
        die(f"list command failed:\n{tail(output)}")
    tests = [line.strip() for line in output.splitlines() if line.strip()]
    if args.match:
        tests = [test for test in tests if re.search(args.match, test)]
    if not tests:
        die("the list command gave zero tests")
    duplicates = [test for test, count in collections.Counter(tests).items() if count > 1]
    if duplicates:
        die(f"test IDs are not unique: {duplicates[:5]}")

    records = {}
    with tempfile.TemporaryDirectory() as scratch:
        with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
            results = pool.map(lambda test: (test, run_one(config, repo, test, scratch)), tests)
            for test, (status, reason, seconds, coverage, log) in results:
                record = {"status": status, "seconds": seconds,
                          "lines": {path: sorted(lines) for path, lines in sorted(coverage.items())}}
                if status != "pass":
                    record.update(reason=reason, log_tail=tail(log))
                records[test] = record

    owners = collections.Counter()
    for record in records.values():
        owners.update(line_keys(record["lines"]))
    for record in records.values():
        keys = line_keys(record["lines"])
        record["line_count"] = len(keys)
        record["unique_lines"] = sum(1 for key in keys if owners[key] == 1)

    snapshot = {"name": args.snapshot, "rev": head(repo), "match": args.match or "",
                "config_sha": config_sha(config), "tests": records}
    target = directory / "snapshots"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{args.snapshot}.json").write_text(json.dumps(snapshot, indent=1) + "\n")
    rows = sorted(records.items(), key=lambda item: (item[1]["unique_lines"], item[0]))
    with (target / f"{args.snapshot}.tsv").open("w") as table:
        table.write("test\tstatus\tseconds\tlines\tunique_lines\n")
        for test, record in rows:
            table.write(f"{test}\t{record['status']}\t{record['seconds']}\t"
                        f"{record['line_count']}\t{record['unique_lines']}\n")
    statuses = collections.Counter(record["status"] for record in records.values())
    print(f"snapshot {args.snapshot} at {snapshot['rev'][:12]}: {len(records)} tests "
          f"{dict(statuses)}, {len(owners)} production lines covered, "
          f"{sum(1 for r in records.values() if r['unique_lines'] == 0)} tests with no unique line")
    for test, record in records.items():
        if record["status"] != "pass":
            print(f"  {record['status']}: {test}: {record['reason']}")
    return 0


def prove_in_worktree(config, tree, test_id, patch, expect):
    """Return (outcome, reason, log)."""
    code, log = build(config, tree)
    if code != 0:
        return "invalid", "the baseline does not build", log
    with tempfile.TemporaryDirectory() as scratch:
        status, reason, _, _, baseline = run_one(config, tree, test_id, scratch)
        if status != "pass":
            return "invalid", f"the test does not pass at baseline: {status}: {reason}", baseline
        if re.search(expect, baseline, re.M):
            return "invalid", "--expect also matches the baseline output", baseline
        applied = git(tree, "apply", str(patch), check=False)
        if applied.returncode:
            return "invalid", "the patch does not apply", applied.stderr
        code, log = build(config, tree)
        if code != 0:
            return "invalid", "the patched code does not build. A build failure proves nothing", log
        status, reason, _, _, log = run_one(config, tree, test_id, scratch)
    if status in ("pass", "invalid") and re.search(config["pass_pattern"], log, re.M):
        return "survived", "the test passes with the wrong behavior", log
    if status == "fail" and re.search(expect, log, re.M):
        return "rejected", "the test fails for the expected reason", log
    return "invalid", f"the run ended as {status}, but --expect did not match the output", log


def cmd_prove(args):
    repo, directory = repo_root(args.repo), args.dir.resolve()
    config = load_config(directory)
    require_clean(repo)
    patch = args.patch.resolve()
    if not patch.is_file():
        die(f"patch is missing: {patch}")
    re.compile(args.expect)
    changed = git(repo, "apply", "--numstat", str(patch), check=False)
    if changed.returncode:
        die(f"the patch is not valid: {changed.stderr.strip()}")
    paths = [line.split("\t")[2] for line in changed.stdout.splitlines()]
    if not paths or any(is_test_path(config, path) for path in paths):
        die("the patch must change production files only")
    rev = head(repo)
    with tempfile.TemporaryDirectory() as scratch:
        tree = pathlib.Path(scratch) / "tree"
        git(repo, "worktree", "add", "--quiet", "--detach", str(tree), rev)
        try:
            outcome, reason, log = prove_in_worktree(config, tree.resolve(), args.test, patch, args.expect)
        finally:
            git(repo, "worktree", "remove", "--force", str(tree), check=False)
    record = {"test": args.test, "wrong_behavior": args.wrong_behavior, "rev": rev,
              "expect": args.expect, "outcome": outcome, "reason": reason,
              "patch": patch.read_text(errors="replace"), "log_tail": tail(log),
              "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "proofs.jsonl").open("a") as proofs:
        proofs.write(json.dumps(record) + "\n")
    print(f"{outcome}: {args.test}: {reason}")
    if outcome == "invalid":
        print(tail(log, 15))
    return 0 if outcome == "rejected" else 1


def unlock_keys(candidate):
    keys, problems = set(), []
    for unlock in candidate.get("unlocks") or []:
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", str(unlock.get("lines", "")))
        if not unlock.get("path") or not match:
            problems.append(f"unlock needs path and lines such as 10-20: {unlock}")
            continue
        first, last = int(match[1]), int(match[2] or match[1])
        keys.update(f"{unlock['path']}:{line}" for line in range(first, last + 1))
    return keys, problems


def evaluate(repo, before, candidates):
    """Derive status for each candidate. Return a row for each one."""
    tests = before["tests"]
    removed = {c.get("test") for c in candidates if c.get("action") == "delete"}
    rows = []
    for candidate in candidates:
        reasons = [f"missing field: {field}" for field in CANDIDATE_REQUIRED
                   if field not in candidate or candidate[field] in (None, "")]
        test_id, action = candidate.get("test"), candidate.get("action")
        if sum(1 for other in candidates if other.get("test") == test_id) > 1:
            reasons.append("the test has more than one candidate record")
        if action not in ACTIONS:
            reasons.append(f"action must be one of {ACTIONS}")
        if candidate.get("pattern") not in PATTERNS:
            reasons.append("pattern is not in the junk pattern list")
        record = tests.get(test_id)
        if record is None:
            reasons.append("the test is not in the before snapshot")
        elif record["status"] != "pass":
            reasons.append(f"the test is {record['status']} at baseline. Treat this as a possible "
                           "product defect. Investigate it. Do not delete it")
        path = candidate.get("path")
        if path and git(repo, "cat-file", "-e", f"{before['rev']}:{path}", check=False).returncode:
            reasons.append(f"path does not exist at the before commit: {path}")
        proof = candidate.get("stronger_proof")
        if isinstance(proof, dict) and proof.get("test"):
            target = tests.get(proof["test"])
            if proof["test"] == test_id:
                reasons.append("stronger_proof names the same test")
            elif action == "delete" and (target is None or target["status"] != "pass"):
                reasons.append(f"stronger_proof is not a passing test: {proof['test']}")
            elif proof["test"] in removed:
                reasons.append(f"stronger_proof is also a delete candidate: {proof['test']}")
        elif not (isinstance(proof, dict) and proof.get("none")):
            reasons.append('stronger_proof needs {"test": id} or {"none": reason}')
        if candidate.get("contract") and not candidate.get("approved_by"):
            reasons.append(f"guards contract '{candidate['contract']}'. A human must approve this")
        _, problems = unlock_keys(candidate)
        reasons.extend(problems)
        rows.append({"test": test_id, "action": action, "status": "blocked" if reasons else "ready",
                     "unique_lines": record["unique_lines"] if record else None, "reasons": reasons})

    # Simulate the whole batch. Two duplicate tests each have no unique line,
    # but the deletion of both loses the lines.
    known_removed = removed & set(tests)
    baseline = snapshot_union(before)
    remaining = snapshot_union(before, skip=known_removed)
    declared = set()
    for candidate in candidates:
        declared |= unlock_keys(candidate)[0]
    lost = baseline - remaining
    undeclared = lost - declared
    row_by_test = {row["test"]: row for row in rows}
    for test_id in known_removed:
        hits = line_keys(tests[test_id]["lines"]) & undeclared
        if hits:
            row = row_by_test[test_id]
            row["status"] = "blocked"
            row["reasons"].append(f"only coverage in this batch for {len(hits)} production lines, "
                                  f"for example {sorted(hits)[:5]}. Declare them in unlocks, or keep the test")
    for candidate in candidates:
        still = unlock_keys(candidate)[0] & remaining
        if still:
            row = row_by_test[candidate.get("test")]
            row["status"] = "blocked"
            row["reasons"].append(f"unlock lines still have coverage from other tests: {sorted(still)[:5]}")
    return rows, {"lost": lost, "undeclared": undeclared, "declared": declared}


def print_rows(rows):
    for row in rows:
        print(f"{row['status']:8} {row['action'] or '-':8} unique={row['unique_lines']} {row['test']}")
        for reason in row["reasons"]:
            print(f"         - {reason}")


def load_candidates(directory):
    candidates = load_json(directory / "candidates.json", "candidates").get("candidates")
    if not isinstance(candidates, list) or not candidates:
        die("candidates.json needs a non-empty candidates list")
    return candidates


def cmd_check(args):
    repo, directory = repo_root(args.repo), args.dir.resolve()
    before = load_json(directory / "snapshots" / "before.json", "before snapshot")
    rows, _ = evaluate(repo, before, load_candidates(directory))
    (directory / "check.json").write_text(json.dumps(rows, indent=1) + "\n")
    print_rows(rows)
    blocked = sum(1 for row in rows if row["status"] == "blocked")
    print(f"{len(rows) - blocked} ready, {blocked} blocked")
    return 1 if blocked else 0


def production_changes(config, repo, before, after):
    """Return the changed paths that are not test code."""
    changes = []
    for path in git(repo, "diff", "--name-only", before, after).stdout.splitlines():
        if is_test_path(config, path):
            continue
        boundary = marker_line(config, repo, path, before)
        diff = git(repo, "diff", "-U0", before, after, "--", path).stdout
        starts = [int(match) for match in re.findall(r"^@@ -(\d+)", diff, re.M)]
        if boundary is None or not starts or min(starts) < boundary:
            changes.append(path)
    return changes


def cmd_gate(args):
    repo, directory = repo_root(args.repo), args.dir.resolve()
    config = load_config(directory)
    before = load_json(directory / "snapshots" / "before.json", "before snapshot")
    after = load_json(directory / "snapshots" / "after.json", "after snapshot")
    candidates = load_candidates(directory)
    has_files = bool(args.survivors_before and args.survivors_after)
    if has_files == bool(args.no_mutation) or (not has_files and (args.survivors_before or args.survivors_after)):
        die("give --survivors-before and --survivors-after, or give --no-mutation REASON")

    failures = []
    if before["config_sha"] != after["config_sha"] or before["config_sha"] != config_sha(config):
        failures.append("the snapshots use different config. Collect both with one config")
    if before["match"] != after["match"]:
        failures.append("the snapshots use different --match scopes")
    if git(repo, "merge-base", "--is-ancestor", before["rev"], after["rev"], check=False).returncode:
        failures.append("the after commit does not descend from the before commit")
    if before["rev"] == after["rev"]:
        failures.append("the before and after commits are the same")
    production = production_changes(config, repo, before["rev"], after["rev"])
    if production:
        failures.append("the commit changes production files. Change only tests here, and delete "
                        f"dead production code in the next commit: {production}")

    rows, _ = evaluate(repo, before, candidates)
    ready = {row["test"] for row in rows if row["status"] == "ready"}
    for row in rows:
        if row["status"] == "blocked":
            failures.append(f"candidate is blocked: {row['test']}: {'; '.join(row['reasons'])}")
    before_tests, after_tests = before["tests"], after["tests"]
    for test_id, record in after_tests.items():
        if record["status"] != "pass":
            failures.append(f"test is {record['status']} after the change: {test_id}")
    removed, added = set(before_tests) - set(after_tests), set(after_tests) - set(before_tests)
    for test_id in sorted(removed - ready):
        failures.append(f"test was removed without a ready candidate: {test_id}")
    for candidate in candidates:
        proof = candidate.get("stronger_proof")
        target = proof.get("test") if isinstance(proof, dict) else None
        if target and after_tests.get(target, {}).get("status") != "pass":
            failures.append(f"stronger_proof does not pass after the change: {target}")

    proofs = []
    proof_file = directory / "proofs.jsonl"
    if proof_file.exists():
        proofs = [json.loads(line) for line in proof_file.read_text().splitlines() if line.strip()]
    rejected = {p["test"] for p in proofs if p["outcome"] == "rejected" and p["rev"] == after["rev"]}
    for test_id in sorted(added - rejected):
        failures.append(f"added test has no rejected proof at the after commit: {test_id}")

    lost = snapshot_union(before) - snapshot_union(after)
    declared = set()
    for candidate in candidates:
        declared |= unlock_keys(candidate)[0]
    undeclared = lost - declared
    if undeclared:
        failures.append(f"{len(undeclared)} production lines lost coverage without a declaration, "
                        f"for example {sorted(undeclared)[:8]}")

    new_survivors = []
    if has_files:
        def survivors(path):
            lines = pathlib.Path(path).read_text().splitlines()
            return {line.strip() for line in lines if line.strip() and not line.startswith("#")}
        new_survivors = sorted(survivors(args.survivors_after) - survivors(args.survivors_before))
        if new_survivors:
            failures.append(f"{len(new_survivors)} mutants survive now, but did not survive before: "
                            f"{new_survivors[:8]}")

    numstat = git(repo, "diff", "--numstat", before["rev"], after["rev"]).stdout.splitlines()
    added_loc = sum(int(line.split("\t")[0]) for line in numstat if line.split("\t")[0].isdigit())
    removed_loc = sum(int(line.split("\t")[1]) for line in numstat if line.split("\t")[1].isdigit())
    seconds = lambda tests: round(sum(record["seconds"] for record in tests.values()), 2)
    result = {"verdict": "fail" if failures else "pass", "before": before["rev"], "after": after["rev"],
              "failures": failures, "tests_before": len(before_tests), "tests_after": len(after_tests),
              "removed": sorted(removed), "added": sorted(added),
              "lines_before": len(snapshot_union(before)), "lines_after": len(snapshot_union(after)),
              "lost_declared": sorted(lost & declared), "seconds_before": seconds(before_tests),
              "seconds_after": seconds(after_tests), "loc_added": added_loc, "loc_removed": removed_loc,
              "mutation": "compared" if has_files else f"not run: {args.no_mutation}",
              "new_survivors": new_survivors}
    (directory / "gate.json").write_text(json.dumps(result, indent=1) + "\n")
    print(f"verdict: {result['verdict'].upper()}")
    print(f"tests: {result['tests_before']} -> {result['tests_after']} "
          f"(removed {len(removed)}, added {len(added)})")
    print(f"production lines covered: {result['lines_before']} -> {result['lines_after']} "
          f"(declared loss {len(result['lost_declared'])})")
    print(f"serial test time: {result['seconds_before']}s -> {result['seconds_after']}s")
    print(f"LOC: +{added_loc} -{removed_loc}")
    print(f"mutation: {result['mutation']}")
    for failure in failures:
        print(f"FAIL: {failure}")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name, function, help_text):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--dir", type=pathlib.Path, required=True, help="audit batch directory")
        command.add_argument("--repo", type=pathlib.Path, default=pathlib.Path("."), help="target repository")
        command.set_defaults(function=function)
        return command

    collect = add("collect", cmd_collect, "run each test alone and write a snapshot")
    collect.add_argument("--snapshot", choices=("before", "after"), required=True)
    collect.add_argument("--match", help="regex that limits the test IDs")
    collect.add_argument("--jobs", type=int, default=1, help="use more than 1 only if tests do not share state")
    prove = add("prove", cmd_prove, "prove that a test rejects a named wrong behavior")
    prove.add_argument("--test", required=True, help="test ID")
    prove.add_argument("--patch", type=pathlib.Path, required=True, help="patch to production code")
    prove.add_argument("--wrong-behavior", required=True, help="the requirement that the patch violates")
    prove.add_argument("--expect", required=True, help="regex for the expected failure output")
    add("check", cmd_check, "derive ready or blocked for each candidate")
    gate = add("gate", cmd_gate, "compare the before and after snapshots")
    gate.add_argument("--survivors-before", type=pathlib.Path, help="one surviving mutant ID per line")
    gate.add_argument("--survivors-after", type=pathlib.Path)
    gate.add_argument("--no-mutation", help="reason that no mutation run exists")
    args = parser.parse_args()
    return args.function(args)


if __name__ == "__main__":
    sys.exit(main())
