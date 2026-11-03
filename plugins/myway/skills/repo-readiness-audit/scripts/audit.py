#!/usr/bin/env python3
"""Evidence store, gate rules, and report renderer for repo-readiness-audit.

Standard library only. Agents write judgment into JSON files. This script derives
verification status and verdicts, so that an agent cannot claim them.

Commands: init, run, approve, decide, validate, gate, render, diff.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LEVEL = {"E0": 0, "E1": 1, "E2": 2, "E3": 3, "E4": 4}
IMPLEMENTATION = {"complete", "partial", "stub", "missing", "divergent"}
GAP_TYPES = {
    "missing", "partial", "stub", "divergent", "hollow_test", "prd_ambiguity", "unrequested",
    "not_tested", "readiness",
}
CATEGORIES = [
    "failure", "recovery", "idempotency", "security", "secrets", "config",
    "performance", "observability", "migration", "rollback",
]
STAGING_CATEGORIES = {"rollback", "security", "secrets"}
# These categories have static checks by nature. Production accepts a pass at E1 for them.
STATIC_CATEGORIES = {"security", "secrets", "config"}
MUTATION_FLOOR = 0.7
BLOCK = {"none": 0, "production": 1, "staging": 2}
SURFACE_KINDS = {
    "endpoint", "cli", "job", "config", "dependency", "network", "filesystem",
    "side_effect", "other",
}
SURFACE_CLASSES = {"required", "supporting", "unrequested"}
INT_KINDS = {
    "stub", "todo", "hardcoded_return", "swallowed_error", "skipped_test",
    "tautological_assert", "mocked_sut", "level_overclaim", "unwired_code",
    "test_defect", "setup_failure", "other",
}
# These kinds invalidate a run, but they do not show a defect in the product.
NO_GAP_KINDS = {"test_defect", "setup_failure"}
JSON_FILES = [
    "ledger.json", "matrix.json", "gaps.json", "surface.json", "integrity.json",
    "readiness.json", "cognition.json", "approvals.json",
]
TEMPLATES = {
    "ledger.json": {"goals": [], "requirements": [], "exclusions": []},
    "matrix.json": {"status": "pending", "requirements": [], "limits": []},
    "gaps.json": {"status": "pending", "gaps": []},
    "surface.json": {"status": "pending", "method": "", "items": [], "limits": []},
    "integrity.json": {"status": "pending", "scans": [], "findings": [], "mutation": [], "limits": []},
    "readiness.json": {"status": "pending", "checks": [], "goals": [], "limits": []},
    "cognition.json": {
        "status": "pending", "model_source": "", "believes": [], "decided": [], "unknown": [], "limits": [],
    },
    "approvals.json": {"ledger": None, "decisions": {}},
}


def die(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args, check=True):
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and done.returncode != 0:
        die(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout.strip()


def git_status(repo):
    return subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True
    ).stdout.strip()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def tree_hash(path):
    digest = hashlib.sha256()
    for item in sorted(Path(path).rglob("*")):
        if item.is_file() and "__pycache__" not in item.parts and ".pytest_cache" not in item.parts:
            digest.update(str(item.relative_to(path)).encode())
            digest.update(item.read_bytes())
    return digest.hexdigest()


def normalize(text):
    return re.sub(r"\s+", " ", re.sub(r"[*`]", "", text)).strip().lower()


def duplicates(owner, ids):
    return [f"{owner}: duplicate ID {i}" for i in sorted({i for i in ids if ids.count(i) > 1 and i})]


class Audit:
    """One audit directory, pinned to one commit."""

    def __init__(self, path):
        self.dir = Path(path).resolve()
        if not (self.dir / "baseline.json").exists():
            die(f"{self.dir} is not an audit directory")
        self.baseline = read_json(self.dir / "baseline.json")
        self.repo = Path(self.baseline["repo"])
        self.commit = self.baseline["commit"]
        for name in JSON_FILES:
            try:
                data = read_json(self.dir / name)
            except json.JSONDecodeError as exc:
                die(f"{name} is not valid JSON: {exc}")
            setattr(self, name.split(".")[0], data)
        self.runs = []
        runs_path = self.dir / "runs.jsonl"
        if runs_path.exists():
            for line in runs_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.runs.append(json.loads(line))
        self.req = {r["id"]: r for r in self.ledger["requirements"]}
        self.goal = {g["id"]: g for g in self.ledger["goals"]}
        self.row = {r["id"]: r for r in self.matrix["requirements"]}
        self.goal_row = {g["id"]: g for g in self.readiness["goals"]}
        self.exc = {e["id"]: e for e in self.ledger["exclusions"] if e.get("id")}
        self.rdy = {c["id"]: c for c in self.readiness["checks"]}
        self.gap = {g["id"]: g for g in self.gaps["gaps"]}
        self.decisions = self.approvals["decisions"]
        not_testable = self.dir / "acceptance" / "not_testable.json"
        self.not_testable = read_json(not_testable) if not_testable.exists() else {}

    # Evidence derivation -----------------------------------------------------

    def invalidated(self):
        result = set()
        for finding in self.integrity["findings"]:
            result.update(finding.get("invalidates_runs") or [])
        return result

    def usable(self, attempt):
        if attempt["commit"] != self.commit or attempt["dirty"]:
            return False
        bad = self.invalidated()
        return attempt["run"] not in bad and f"{attempt['run']}#{attempt['attempt']}" not in bad

    def run_level(self, attempt):
        """E4 counts only after a human confirms the environment of the run."""
        if attempt["level"] == "E4" and (self.decisions.get(attempt["run"]) or {}).get("decision") != "accepted":
            return "E3"
        return attempt["level"]

    def evidence(self, target, acceptance_only=False):
        """Return (verification, level, run ids) for one ledger or readiness ID."""
        by_run = {}
        for attempt in self.runs:
            if target not in attempt["covers"] or not self.usable(attempt):
                continue
            if acceptance_only and attempt["source"] != "acceptance":
                continue
            by_run.setdefault(attempt["run"], []).append(attempt)
        if not by_run:
            return "not_tested", None, []
        latest = [items[-1] for items in by_run.values()]
        ids = sorted(by_run)
        failed = [a for a in latest if a["outcome"] != "pass"]
        if failed:
            return "fail", max((self.run_level(a) for a in failed), key=LEVEL.get), ids
        # Mixed outcomes at one commit show a flaky test, or a test changed after a failure.
        # The integrity auditor must invalidate the attempt to clear this state.
        if any(len({a["outcome"] for a in items}) > 1 for items in by_run.values()):
            return "unstable", max((self.run_level(a) for a in latest), key=LEVEL.get), ids
        return "pass", max((self.run_level(a) for a in latest), key=LEVEL.get), ids

    def req_state(self, req_id):
        req, row = self.req[req_id], self.row.get(req_id)
        static = "E1" if row and row.get("code") else "E0"
        if req_id in self.not_testable:
            return {"verification": "not_testable", "level": static, "runs": []}
        verification, level, runs = self.evidence(req_id, acceptance_only=req["priority"] == "P0")
        return {"verification": verification, "level": level or static, "runs": runs}

    def rdy_state(self, check):
        if check.get("not_applicable"):
            return {"status": "not_applicable", "level": "-", "runs": []}
        verification, level, runs = self.evidence(check["id"])
        if verification != "not_tested":
            return {"status": verification, "level": level, "runs": runs}
        static = check.get("static_result")
        if static in ("pass", "fail"):
            return {"status": static, "level": "E1", "runs": []}
        return {"status": "not_tested", "level": "E0", "runs": []}

    def goal_state(self, goal_id):
        """A goal run must fail when the measured value misses the target."""
        row = self.goal_row.get(goal_id) or {}
        verification, level, runs = self.evidence(goal_id, acceptance_only=True)
        status = {"pass": "met", "fail": "not_met", "unstable": "unstable"}.get(verification)
        if status is None:
            status = "post_launch" if row.get("post_launch") else "not_measured"
        return {"status": status, "level": level or "E0", "runs": runs}

    def gaps_for(self, item_id):
        return [g["id"] for g in self.gaps["gaps"] if item_id in (g.get("refs") or [])]

    def approved_ledger(self):
        record = self.approvals.get("ledger")
        return bool(record) and record["sha256"] == self.ledger_hash()

    def ledger_hash(self):
        digest = hashlib.sha256((self.dir / "ledger.json").read_bytes())
        for item in self.baseline["inputs"]:
            digest.update(item["sha256"].encode())
        return digest.hexdigest()

    # Validation --------------------------------------------------------------

    def validate_ledger(self):
        errors = []
        if not self.ledger["requirements"]:
            errors.append("ledger.json has no requirements")
        texts = {}
        for item in self.baseline["inputs"]:
            texts[item["name"]] = normalize((self.dir / "inputs" / item["name"]).read_text(encoding="utf-8"))

        def check_source(owner, source):
            if not isinstance(source, dict):
                errors.append(f"{owner}: source is missing")
                return
            doc, quote = source.get("doc"), source.get("quote") or ""
            if doc not in texts:
                errors.append(f"{owner}: source doc {doc!r} is not in inputs/")
            elif not quote.strip() or normalize(quote) not in texts[doc]:
                errors.append(f"{owner}: source quote is not in {doc}")

        ids = [r.get("id") for r in self.ledger["requirements"]]
        ids += [g.get("id") for g in self.ledger["goals"]]
        ids += [e.get("id") for e in self.ledger["exclusions"]]
        errors += duplicates("ledger.json", ids)
        for req in self.ledger["requirements"]:
            rid = req.get("id", "?")
            if not re.fullmatch(r"REQ-\d+", rid):
                errors.append(f"{rid}: ID must match REQ-<number>")
            if req.get("priority") not in ("P0", "P1", "P2"):
                errors.append(f"{rid}: priority must be P0, P1, or P2")
            if req.get("priority_source") not in ("prd", "proposed"):
                errors.append(f"{rid}: priority_source must be prd or proposed")
            if not req.get("text"):
                errors.append(f"{rid}: text is empty")
            if not req.get("acceptance") and not req.get("open_question"):
                errors.append(f"{rid}: needs acceptance criteria or an open_question")
            check_source(rid, req.get("source"))
        for goal in self.ledger["goals"]:
            gid = goal.get("id", "?")
            if not re.fullmatch(r"G-\d+", gid):
                errors.append(f"{gid}: ID must match G-<number>")
            if not (goal.get("metric") and goal.get("target")) and not goal.get("open_question"):
                errors.append(f"{gid}: needs metric and target, or an open_question")
            check_source(gid, goal.get("source"))
        for item in self.ledger["exclusions"]:
            eid = item.get("id", "?")
            if not re.fullmatch(r"EXC-\d+", eid):
                errors.append(f"{eid}: ID must match EXC-<number>")
            check_source(eid, item.get("source"))
        return errors

    def code_ref_errors(self, owner, refs):
        errors = []
        files = set(git(self.repo, "ls-tree", "-r", "--name-only", self.commit).splitlines())
        for ref in refs or []:
            match = re.fullmatch(r"(.+?)(?::(\d+)(?:-(\d+))?)?", ref)
            path, end = match.group(1), match.group(3) or match.group(2)
            if path not in files:
                errors.append(f"{owner}: code reference {ref} is not at the baseline commit")
            elif end:
                count = git(self.repo, "show", f"{self.commit}:{path}", check=False).count("\n") + 1
                if int(end) > count:
                    errors.append(f"{owner}: code reference {ref} is past end of file ({count} lines)")
        return errors

    def known_ids(self):
        ids = set(self.req) | set(self.goal) | set(self.exc) | set(self.rdy) | set(self.gap)
        ids |= {i["id"] for i in self.surface["items"]}
        ids |= {f["id"] for f in self.integrity["findings"]}
        ids |= {m["id"] for m in self.integrity["mutation"] if m.get("id")}
        ids |= {a["run"] for a in self.runs}
        for key in ("believes", "decided", "unknown"):
            ids |= {i["id"] for i in self.cognition[key]}
        return ids

    def validate_matrix(self):
        errors = duplicates("matrix.json", [r.get("id") for r in self.matrix["requirements"]])
        for rid in set(self.req) ^ set(self.row):
            errors.append(f"{rid}: needs exactly one row in both ledger.json and matrix.json")
        for rid, row in self.row.items():
            if row.get("implementation") not in IMPLEMENTATION:
                errors.append(f"{rid}: implementation value is not valid")
            if row.get("implementation") != "missing" and not row.get("code"):
                errors.append(f"{rid}: implementation {row.get('implementation')} needs code references")
            errors += self.code_ref_errors(rid, row.get("code"))
        for key in self.not_testable:
            if key not in self.req:
                errors.append(f"acceptance/not_testable.json: {key} is not a requirement")
        return errors

    def validate_surface(self):
        errors = duplicates("surface.json", [i.get("id") for i in self.surface["items"]])
        for item in self.surface["items"]:
            sid = item.get("id", "?")
            if item.get("kind") not in SURFACE_KINDS:
                errors.append(f"{sid}: kind value is not valid")
            klass = item.get("classification")
            if klass not in SURFACE_CLASSES:
                errors.append(f"{sid}: classification value is not valid")
            if klass == "required":
                refs = item.get("requirements") or []
                if not refs or any(r not in self.req for r in refs):
                    errors.append(f"{sid}: required item needs known requirement IDs")
            for exc in item.get("exclusions") or []:
                if exc not in self.exc:
                    errors.append(f"{sid}: exclusion {exc} is not known")
        return errors

    def validate_integrity(self):
        errors = duplicates("integrity.json", [f.get("id") for f in self.integrity["findings"]])
        run_ids = {a["run"] for a in self.runs}
        for finding in self.integrity["findings"]:
            fid = finding.get("id", "?")
            if finding.get("kind") not in INT_KINDS:
                errors.append(f"{fid}: kind value is not valid")
            for run in finding.get("invalidates_runs") or []:
                if run.split("#")[0] not in run_ids:
                    errors.append(f"{fid}: run {run} is not in runs.jsonl")
            for ref in finding.get("requirements") or []:
                if ref not in self.req:
                    errors.append(f"{fid}: requirement {ref} is not known")
        if self.integrity.get("status") == "complete":
            if not self.integrity["scans"]:
                errors.append("integrity.json: complete status needs at least one scan")
            if not self.integrity["mutation"]:
                errors.append("integrity.json: complete status needs a mutation entry")
        for item in self.integrity["mutation"]:
            mid = item.get("id", "?")
            if not re.fullmatch(r"MUT-\d+", mid):
                errors.append(f"{mid}: ID must match MUT-<number>")
            if item.get("score") is None:
                if not item.get("not_run_reason"):
                    errors.append(f"{mid}: needs score or not_run_reason")
            else:
                if not 0 <= item["score"] <= 1:
                    errors.append(f"{mid}: score must be between 0 and 1")
                if item.get("run") not in run_ids:
                    errors.append(f"{mid}: a score needs a run that is in runs.jsonl")
        return errors

    def validate_readiness(self):
        errors = duplicates("readiness.json", [c.get("id") for c in self.readiness["checks"]])
        errors += duplicates("readiness.json goals", [g.get("id") for g in self.readiness["goals"]])
        seen = set()
        for check in self.readiness["checks"]:
            cid = check.get("id", "?")
            if not re.fullmatch(r"RDY-\d+", cid):
                errors.append(f"{cid}: ID must match RDY-<number>")
            if check.get("category") not in CATEGORIES:
                errors.append(f"{cid}: category value is not valid")
            seen.add(check.get("category"))
            errors += self.code_ref_errors(cid, check.get("code"))
            if check.get("static_result") and not (check.get("code") or check.get("method")):
                errors.append(f"{cid}: static_result needs code references or a method")
        for gid in set(self.goal) ^ set(self.goal_row):
            errors.append(f"{gid}: needs exactly one row in both ledger.json and readiness.json goals")
        if self.readiness.get("status") == "complete":
            for category in CATEGORIES:
                if category not in seen:
                    errors.append(f"readiness.json: category {category} has no check")
        return errors

    def validate_cognition(self):
        errors = []
        for key in ("believes", "decided", "unknown"):
            errors += duplicates("cognition.json", [i.get("id") for i in self.cognition[key]])
        for item in self.cognition["believes"]:
            if not item.get("evidence"):
                errors.append(f"{item.get('id')}: belief needs evidence")
            if item.get("delta") not in ("new", "confirmed", "contradicted"):
                errors.append(f"{item.get('id')}: delta value is not valid")
        for item in self.cognition["decided"]:
            if not item.get("text"):
                errors.append(f"{item.get('id')}: decision text is empty")
        known = self.known_ids()
        for item in self.cognition["unknown"]:
            if item.get("blocks") not in BLOCK:
                errors.append(f"{item.get('id')}: blocks must be staging, production, or none")
            if not item.get("how_to_resolve"):
                errors.append(f"{item.get('id')}: needs how_to_resolve")
            if not item.get("refs") or any(r not in known for r in item["refs"]):
                errors.append(f"{item.get('id')}: needs known refs")
        return errors

    def validate_gaps(self):
        """Links go one way: gaps and decisions refer to items. Earlier roles need no gap IDs."""
        errors = duplicates("gaps.json", [g.get("id") for g in self.gaps["gaps"]])
        known = self.known_ids()
        for gap in self.gaps["gaps"]:
            gid = gap.get("id", "?")
            if not re.fullmatch(r"GAP-\d+", gid):
                errors.append(f"{gid}: ID must match GAP-<number>")
            if gap.get("type") not in GAP_TYPES:
                errors.append(f"{gid}: type value is not valid")
            if gap.get("blocks") not in BLOCK:
                errors.append(f"{gid}: blocks must be staging, production, or none")
            if not gap.get("action") or not gap.get("summary"):
                errors.append(f"{gid}: needs summary and action")
            if not gap.get("refs"):
                errors.append(f"{gid}: needs at least one reference")
            for ref in gap.get("refs") or []:
                if ref not in known:
                    errors.append(f"{gid}: reference {ref} is not known")
        for rid in self.req:
            implementation = (self.row.get(rid) or {}).get("implementation")
            verification = self.req_state(rid)["verification"]
            if (implementation != "complete" or verification != "pass") and not self.gaps_for(rid):
                errors.append(f"{rid}: implementation {implementation} and verification {verification} need a gap")
        for gid in self.goal:
            status = self.goal_state(gid)["status"]
            if status in ("not_met", "not_measured", "unstable") and not self.gaps_for(gid):
                errors.append(f"{gid}: status {status} needs a gap")
        for check in self.readiness["checks"]:
            status = self.rdy_state(check)["status"]
            if status in ("fail", "unstable", "not_tested") and not self.gaps_for(check["id"]):
                errors.append(f"{check['id']}: status {status} needs a gap")
        decided_refs = {r for d in self.cognition["decided"] for r in d.get("refs") or []}
        for item in self.surface["items"]:
            if item.get("classification") == "unrequested" and not self.gaps_for(item["id"]) \
                    and item["id"] not in decided_refs:
                errors.append(f"{item['id']}: unrequested item needs a gap or a Decided entry")
            for exc in item.get("exclusions") or []:
                if not self.gaps_for(exc):
                    errors.append(f"{item['id']}: violation of {exc} needs a gap that refers to {exc}")
        for finding in self.integrity["findings"]:
            needs_gap = finding.get("requirements") or finding.get("invalidates_runs")
            if needs_gap and finding.get("kind") not in NO_GAP_KINDS and not self.gaps_for(finding["id"]):
                errors.append(f"{finding['id']}: needs a gap")
        for item in self.integrity["mutation"]:
            score = item.get("score")
            if score is not None and score < MUTATION_FLOOR and not self.gaps_for(item.get("id")):
                errors.append(f"{item.get('id')}: score below {MUTATION_FLOOR} needs a gap")
        return errors

    def validate_runs(self):
        errors = []
        targets = set(self.req) | set(self.rdy) | set(self.goal)
        for attempt in self.runs:
            log = self.dir / attempt["log"]
            if not log.exists() or sha256(log.read_bytes()) != attempt["log_sha256"]:
                errors.append(f"{attempt['run']}#{attempt['attempt']}: log file is missing or changed")
            for target in attempt["covers"]:
                if target not in targets:
                    errors.append(f"{attempt['run']}: covers unknown ID {target}")
        return errors

    def validate(self, only=None):
        sections = {
            "ledger": self.validate_ledger, "matrix": self.validate_matrix, "surface": self.validate_surface,
            "integrity": self.validate_integrity, "readiness": self.validate_readiness,
            "cognition": self.validate_cognition, "gaps": self.validate_gaps, "runs": self.validate_runs,
        }
        errors = []
        for name, check in sections.items():
            if only and name not in only:
                continue
            errors += check()
            if name not in ("ledger", "runs") and getattr(self, name).get("status") != "complete":
                errors.append(f"{name}.json: status is not complete")
        if not only:
            known = self.known_ids() | {"INDEPENDENCE"}
            for key in self.decisions:
                if key not in known:
                    errors.append(f"approvals.json: decision {key} has no known item")
        return errors

    # Gate --------------------------------------------------------------------

    def req_ok(self, rid):
        state = self.req_state(rid)
        return (self.row.get(rid) or {}).get("implementation") == "complete" and state["verification"] == "pass"

    def floor(self, refs):
        """Minimum block from references. A passing requirement sets no floor."""
        level = "none"
        for ref in refs or []:
            derived = "none"
            if ref in self.req:
                if not self.req_ok(ref):
                    derived = {"P0": "staging", "P1": "production"}.get(self.req[ref]["priority"], "none")
            elif ref in self.goal:
                derived = "staging" if self.goal_state(ref)["status"] == "not_met" else "production"
            elif ref in self.exc:
                derived = "staging"
            elif ref in self.rdy:
                derived = "staging" if self.rdy[ref].get("category") in STAGING_CATEGORIES else "production"
            elif ref.startswith("D-"):
                derived = "production"
            if BLOCK[derived] > BLOCK[level]:
                level = derived
        return level

    def gap_block(self, gap):
        declared, floor = gap.get("blocks", "none"), self.floor(gap.get("refs"))
        return declared if BLOCK.get(declared, 0) > BLOCK[floor] else floor

    def gap_waivable(self, gap):
        for ref in gap.get("refs") or []:
            if ref in self.goal:
                return False
            if ref in self.req and self.req[ref]["priority"] == "P0" and not self.req_ok(ref):
                return False
        return True

    def gap_waived(self, gap):
        decision = self.decisions.get(gap["id"]) or {}
        return decision.get("decision") == "waived" and self.gap_waivable(gap)

    def gate(self):
        common = [f"Data error: {e}" for e in self.validate()]
        staging, production = [], []  # Items are (ID, text).
        if not self.approved_ledger():
            common.append("A human has not approved the current ledger.")
        if self.baseline.get("independence") != "full" and "INDEPENDENCE" not in self.decisions:
            common.append("Independence is reduced. A human must accept this limit (ID INDEPENDENCE).")
        head = git(self.repo, "rev-parse", "HEAD")
        if head != self.commit:
            common.append(f"Repo HEAD {head[:12]} is not the baseline commit {self.commit[:12]}.")
        if git_status(self.repo):
            common.append("The repo working tree is not clean.")

        for item in self.cognition["decided"]:
            decision = self.decisions.get(item["id"])
            if not decision:
                common.append(f"{item['id']}: A human has not decided this agent choice.")
            elif decision["decision"] == "rejected" and not self.gaps_for(item["id"]):
                common.append(f"{item['id']}: Rejected choice has no gap.")
        for item in self.cognition["unknown"]:
            declared = item.get("blocks", "none")
            floor = self.floor(item.get("refs"))
            level = declared if BLOCK.get(declared, 0) > BLOCK[floor] else floor
            text = f"{item['id']}: Unknown. {item.get('text', '')}"
            if level == "staging":
                staging.append((item["id"], text))
            elif level == "production":
                production.append((item["id"], text))

        for rid, req in self.req.items():
            row = self.row.get(rid) or {}
            state = self.req_state(rid)
            implementation = row.get("implementation", "unknown")
            label = f"{rid} ({req['priority']})"
            verification, level = state["verification"], state["level"]
            if req["priority"] == "P0":
                if req.get("open_question"):
                    common.append(f"{label}: Open question: {req['open_question']}")
                if implementation != "complete":
                    staging.append((rid, f"{label}: Implementation is {implementation}."))
                if verification != "pass":
                    staging.append((rid, f"{label}: Verification is {verification} at {level}. "
                                         "P0 evidence counts only from acceptance runs."))
                elif LEVEL[level] < 3:
                    staging.append((rid, f"{label}: Evidence is {level}. Staging needs E3."))
                elif LEVEL[level] < 4:
                    production.append((rid, f"{label}: Evidence is {level}. Production needs E4."))
            elif req["priority"] == "P1":
                if implementation != "complete":
                    production.append((rid, f"{label}: Implementation is {implementation}."))
                if verification != "pass" or LEVEL[level] < 3:
                    production.append((rid, f"{label}: Verification is {verification} at {level}. "
                                            "Production needs a pass at E3."))

        for check in self.readiness["checks"]:
            state = self.rdy_state(check)
            cid, category = check["id"], check.get("category")
            if state["status"] == "not_applicable":
                if (self.decisions.get(cid) or {}).get("decision") != "accepted":
                    common.append(f"{cid}: A human has not accepted not-applicable status.")
                continue
            if category in STAGING_CATEGORIES and state["status"] != "pass":
                staging.append((cid, f"{cid} ({category}): Status is {state['status']}. Staging needs a pass."))
            needed = 1 if category in STATIC_CATEGORIES else 4
            if state["status"] != "pass" or LEVEL[state["level"]] < needed:
                production.append((cid, f"{cid} ({category}): Status is {state['status']} at {state['level']}. "
                                        f"Production needs a pass at E{needed}."))

        for gid, goal in self.goal.items():
            state = self.goal_state(gid)
            if goal.get("open_question"):
                common.append(f"{gid}: Open question: {goal['open_question']}")
            if state["status"] == "not_met":
                staging.append((gid, f"{gid}: Goal is not met. {goal.get('text', '')}"))
            accepted = (self.decisions.get(gid) or {}).get("decision") == "accepted"
            good = (state["status"] == "met" and state["level"] == "E4") or (state["status"] == "post_launch" and accepted)
            if not good:
                production.append((gid, f"{gid}: Goal status is {state['status']} at {state['level']}. "
                                        "Production needs met at E4, or post_launch with human acceptance."))

        for run in sorted({a["run"] for a in self.runs if a["level"] == "E4" and self.usable(a)}):
            if (self.decisions.get(run) or {}).get("decision") != "accepted":
                production.append((run, f"{run}: A human has not confirmed the E4 environment. "
                                        "The run counts as E3."))

        gap_lines = {"staging": [], "production": []}
        covered = {"staging": set(), "production": set()}
        for gap in self.gaps["gaps"]:
            level = self.gap_block(gap)
            decision = self.decisions.get(gap["id"]) or {}
            if decision.get("decision") == "waived" and not self.gap_waivable(gap):
                common.append(f"{gap['id']}: This gap refers to a failing P0 requirement or a goal. "
                              "A waiver is not valid. Change the ledger and approve it again.")
            refs = set(gap.get("refs") or [])
            if self.gap_waived(gap):
                covered["staging"] |= refs
                covered["production"] |= refs
                continue
            if level == "staging":
                covered["staging"] |= refs
                covered["production"] |= refs
            elif level == "production":
                covered["production"] |= refs
            if level in gap_lines:
                gap_lines[level].append(f"{gap['id']} ({gap.get('type')}): {gap.get('summary')}")

        # A gap carries its linked items, so that one defect gives one blocker.
        staging_all = common + gap_lines["staging"] + [t for i, t in staging if i not in covered["staging"]]
        production_all = staging_all + gap_lines["production"] + [
            t for i, t in production if i not in covered["production"]
        ]
        return {
            "staging": {"verdict": "NO-GO" if staging_all else "GO", "blockers": staging_all},
            "production": {"verdict": "NO-GO" if production_all else "GO", "blockers": production_all},
        }

    def summary(self):
        counts = {}
        for rid, req in self.req.items():
            bucket = counts.setdefault(req["priority"], {"total": 0, "complete": 0, "pass": 0, "E3": 0, "E4": 0})
            state = self.req_state(rid)
            bucket["total"] += 1
            bucket["complete"] += (self.row.get(rid) or {}).get("implementation") == "complete"
            if state["verification"] == "pass":
                bucket["pass"] += 1
                bucket["E3"] += LEVEL[state["level"]] >= 3
                bucket["E4"] += LEVEL[state["level"]] >= 4
        return counts


# Commands --------------------------------------------------------------------


def cmd_init(args):
    repo = Path(git(args.repo, "rev-parse", "--show-toplevel"))
    commit = git(repo, "rev-parse", "HEAD")
    if git_status(repo):
        die("The working tree is not clean. Commit or stash the changes, then run init again.")
    root = repo / ".audit" / commit[:12]
    if root.exists():
        die(f"{root} exists. Use this directory, or remove it to start again.")
    exclude = Path(git(repo, "rev-parse", "--git-path", "info/exclude"))
    exclude = exclude if exclude.is_absolute() else repo / exclude
    exclude.parent.mkdir(parents=True, exist_ok=True)
    current = exclude.read_text() if exclude.exists() else ""
    if ".audit/" not in current.splitlines():
        exclude.write_text(current + ("" if current.endswith("\n") or not current else "\n") + ".audit/\n")

    inputs = []
    pairs = [("prd", p) for p in args.prd] + [("goal", p) for p in args.goal or []]
    for _, source in pairs:
        try:
            Path(source).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            die(f"{source}: read failed ({exc}). Convert PDF and DOCX inputs to Markdown first.")
    for sub in ("inputs", "evidence", "acceptance"):
        (root / sub).mkdir(parents=True)
    for role, source in pairs:
        target = root / "inputs" / Path(source).name
        if target.exists():
            die(f"Two inputs have the same name: {target.name}")
        shutil.copyfile(source, target)
        inputs.append({
            "name": target.name, "role": role, "source": str(Path(source).resolve()),
            "sha256": sha256(target.read_bytes()),
        })
    write_json(root / "baseline.json", {
        "repo": str(repo), "commit": commit, "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "created": now(), "inputs": inputs, "independence": args.independence,
        "platform": platform.platform(),
    })
    for name, template in TEMPLATES.items():
        write_json(root / name, template)
    (root / "runs.jsonl").touch()
    if args.from_dir:
        old = Path(args.from_dir).resolve()
        (root / "prior").mkdir()
        for name in JSON_FILES + ["baseline.json", "verdict.json"]:
            if (old / name).exists():
                shutil.copyfile(old / name, root / "prior" / name)
        shutil.copyfile(old / "ledger.json", root / "ledger.json")
        # A ledger approval stays valid if the ledger and inputs do not change.
        # Other decisions apply to old code, so a human must make them again.
        write_json(root / "approvals.json", {"ledger": read_json(old / "approvals.json")["ledger"], "decisions": {}})
        shutil.copytree(old / "acceptance", root / "acceptance", dirs_exist_ok=True)
    print(root)


def cmd_run(args):
    audit = Audit(args.dir)
    cmd = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
    if not cmd:
        die("Give the command after --")
    if not re.fullmatch(r"RUN-[\w.-]+", args.id):
        die("A run ID must match RUN-<name>.")
    joined = " ".join(cmd)
    tests_dir = audit.dir / "acceptance"
    names = (str(tests_dir), str(tests_dir.relative_to(audit.repo)))
    if args.source == "acceptance" and not any(name in joined for name in names):
        die(f"A run with source acceptance must name {names[1]} in its command.")
    covers = [c.strip() for c in args.covers.split(",") if c.strip()]
    attempt_no = 1 + sum(1 for a in audit.runs if a["run"] == args.id)
    log = f"evidence/{args.id}.{attempt_no}.log"
    log_path = audit.dir / log
    dirty = bool(git_status(audit.repo))
    commit = git(audit.repo, "rev-parse", "HEAD")
    if dirty or commit != audit.commit:
        print("warning: The tree is dirty or not at the baseline. This attempt will not count.", file=sys.stderr)
    tests_hash = tree_hash(audit.dir / "acceptance") if args.source == "acceptance" else commit
    start = time.time()
    timed_out = False
    with open(log_path, "wb") as out:
        # The repo is untrusted. Do not give it host credentials.
        home = audit.dir / ".home"
        home.mkdir(exist_ok=True)
        env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL", "TMPDIR") if k in os.environ}
        env["HOME"] = str(home)
        for name in args.pass_env or []:
            if name in os.environ:
                env[name] = os.environ[name]
        try:
            process = subprocess.Popen(cmd, cwd=audit.repo, stdout=out, stderr=subprocess.STDOUT,
                                       env=env, start_new_session=True)
        except OSError as exc:
            die(f"Command failed to start: {exc}")
        try:
            code = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            code = 124
    text = log_path.read_text(encoding="utf-8", errors="replace")
    outcome, reason = "pass", ""
    if timed_out:
        outcome, reason = "fail", f"timeout after {args.timeout} s"
    elif code != 0:
        outcome, reason = "fail", f"exit code {code}"
    elif not re.search(args.expect_output, text):
        outcome, reason = "fail", f"output has no match for {args.expect_output!r}"
    record = {
        "run": args.id, "attempt": attempt_no, "level": args.level, "source": args.source,
        "covers": covers, "env": args.env, "passed_env": args.pass_env or [], "cmd": cmd, "exit": code, "outcome": outcome,
        "reason": reason, "started": datetime.fromtimestamp(start, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration_s": round(time.time() - start, 3), "commit": commit, "dirty": dirty, "log": log,
        "log_sha256": sha256(log_path.read_bytes()), "tests_sha256": tests_hash,
    }
    with open(audit.dir / "runs.jsonl", "a", encoding="utf-8") as out:
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"{args.id}#{attempt_no}: {outcome} {reason}".rstrip() + f" (log: {log})")
    return 0 if outcome == "pass" else 1


def cmd_approve(args):
    audit = Audit(args.dir)
    errors = audit.validate_ledger()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        die("The ledger has errors. Fix them before approval.")
    audit.approvals["ledger"] = {"by": args.by, "at": now(), "sha256": audit.ledger_hash()}
    write_json(audit.dir / "approvals.json", audit.approvals)
    print(f"Ledger approved by {args.by}.")


def cmd_decide(args):
    audit = Audit(args.dir)
    allowed = {
        "D-": {"accepted", "rejected"}, "GAP-": {"waived"}, "RDY-": {"accepted"}, "G-": {"accepted"},
        "RUN-": {"accepted"}, "INDEPENDENCE": {"accepted"},
    }
    prefix = next((p for p in allowed if args.id.startswith(p)), None)
    if not prefix or args.decision not in allowed[prefix]:
        die(f"Decision {args.decision} is not valid for {args.id}.")
    if args.id != "INDEPENDENCE" and args.id not in audit.known_ids():
        die(f"{args.id} is not a known ID.")
    audit.decisions[args.id] = {"decision": args.decision, "by": args.by, "reason": args.reason, "at": now()}
    write_json(audit.dir / "approvals.json", audit.approvals)
    print(f"{args.id}: {args.decision} by {args.by}.")


def cmd_validate(args):
    audit = Audit(args.dir)
    errors = audit.validate(args.only.split(",") if args.only else None)
    print("\n".join(errors) if errors else "No errors.")
    return 1 if errors else 0


def cmd_gate(args):
    audit = Audit(args.dir)
    result = audit.gate()
    result["summary"] = audit.summary()
    result["commit"] = audit.commit
    result["created"] = now()
    write_json(audit.dir / "verdict.json", result)
    for stage in ("staging", "production"):
        print(f"{stage}: {result[stage]['verdict']} ({len(result[stage]['blockers'])} blockers)")
    if args.stage:
        return 0 if result[args.stage]["verdict"] == "GO" else 1
    return 0


def cell(value):
    if value is None or value == "" or value == []:
        return "-"
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def cmd_render(args):
    audit = Audit(args.dir)
    result = audit.gate()
    result.update(summary=audit.summary(), commit=audit.commit, created=now())
    write_json(audit.dir / "verdict.json", result)
    out = []
    name = audit.repo.name

    # 1. Verdict.
    out.append(f"# Readiness Report: {name}\n")
    out.append("## 1. Verdict\n")
    out.append(table(["Stage", "Verdict", "Blockers", "Of which gaps"], [
        [s.capitalize(), f"**{result[s]['verdict']}**", len(result[s]["blockers"]),
         sum(1 for b in result[s]["blockers"] if b.startswith("GAP-"))]
        for s in ("staging", "production")
    ]) + "\n")
    summary = result["summary"]
    out.append(table(["Priority", "Requirements", "Implementation complete", "Verification pass", "Pass at E3+", "Pass at E4"], [
        [p, summary[p]["total"], summary[p]["complete"], summary[p]["pass"], summary[p]["E3"], summary[p]["E4"]]
        for p in sorted(summary)
    ]) + "\n")
    if audit.baseline.get("independence") != "full":
        accepted = audit.decisions.get("INDEPENDENCE")
        by = f" {accepted['by']} accepted this limit." if accepted else ""
        out.append(f"> **Limit:** Roles did not run in separate contexts. Independence is reduced.{by}\n")
    if result["staging"]["blockers"]:
        out.append("### Staging blockers\n")
        out += [f"- {b}" for b in result["staging"]["blockers"]]
        out.append("")
    extra = [b for b in result["production"]["blockers"] if b not in result["staging"]["blockers"]]
    out.append("### Evidence and conditions for production\n")
    out.append("Production also needs these items. The staging run must produce the evidence.\n")
    out += [f"- {b}" for b in extra] or ["- No additional conditions."]
    out.append("")
    untested = [r for r in audit.req if audit.req_state(r)["verification"] in ("not_tested", "not_testable")]
    untested += [c["id"] for c in audit.readiness["checks"] if audit.rdy_state(c)["status"] == "not_tested"]
    untested += [g for g in audit.goal if audit.goal_state(g)["status"] == "not_measured"]
    out.append("### What this report did not test\n")
    out.append(f"- Items with no test evidence: {cell(untested)}")
    for label, source in (("Forward trace", audit.matrix), ("Reverse trace", audit.surface),
                          ("Test integrity", audit.integrity), ("Readiness", audit.readiness),
                          ("Cognition review", audit.cognition)):
        out += [f"- {label} role: {limit}" for limit in source.get("limits", [])]
    out.append("")

    # 2. Baseline.
    out.append("## 2. Baseline\n")
    out.append("This report is valid only for the commit below.\n")
    approval = audit.approvals.get("ledger")
    out.append(table(["Field", "Value"], [
        ["Commit", f"`{audit.commit}`"],
        ["Branch", audit.baseline.get("branch")],
        ["Audit started", audit.baseline.get("created")],
        ["Report rendered", result["created"]],
        ["Platform", audit.baseline.get("platform")],
        ["Independence", audit.baseline.get("independence")],
        ["Ledger approval", f"{approval['by']} at {approval['at']}" if approval else "Not approved"],
    ] + [[f"Input ({i['role']})", f"{i['name']} `{i['sha256'][:16]}`"] for i in audit.baseline["inputs"]]) + "\n")

    # 3. Goal check.
    out.append("## 3. Goal Check\n")
    out.append(table(["ID", "Goal", "Metric", "Target", "Measured", "Status", "Evidence", "Runs", "Gaps"], [
        [g["id"], g.get("text"), g.get("metric"), g.get("target"),
         (audit.goal_row.get(g["id"]) or {}).get("measured"), audit.goal_state(g["id"])["status"],
         audit.goal_state(g["id"])["level"], audit.goal_state(g["id"])["runs"], audit.gaps_for(g["id"])]
        for g in audit.ledger["goals"]
    ]) + "\n")

    # 4. Requirement matrix.
    out.append("## 4. Requirement Matrix\n")
    rows = []
    for req in sorted(audit.ledger["requirements"], key=lambda r: (r["priority"], r["id"])):
        row = audit.row.get(req["id"], {})
        state = audit.req_state(req["id"])
        rows.append([
            req["id"], req["priority"], req.get("text"), row.get("implementation"), state["verification"],
            state["level"], f"{req['source'].get('doc')} {req['source'].get('section', '')}".strip(),
            row.get("code"), state["runs"], audit.gaps_for(req["id"]),
        ])
    out.append(table(["ID", "Pri", "Requirement", "Implementation", "Verification", "Evidence", "PRD", "Code", "Runs", "Gaps"], rows) + "\n")
    proposed = [r["id"] for r in audit.ledger["requirements"] if r.get("priority_source") == "proposed"]
    questions = [(r["id"], r["open_question"]) for r in audit.ledger["requirements"] if r.get("open_question")]
    if proposed:
        out.append(f"The PRD does not state a priority for: {cell(proposed)}. The agent proposed it.\n")
    if questions:
        out.append("Open PRD questions:\n")
        out += [f"- {i}: {q}" for i, q in questions]
        out.append("")
    if audit.ledger["exclusions"]:
        out.append("PRD exclusions:\n")
        out += [f"- {e.get('id')}: {e.get('text')}" for e in audit.ledger["exclusions"]]
        out.append("")

    # 5. Evidence levels.
    out.append("## 5. Evidence Levels\n")
    out.append(table(["Level", "Evidence"], [
        ["E0", "Agent statement only"],
        ["E1", "Static code inspection"],
        ["E2", "Test with mocks"],
        ["E3", "Integration test with real dependencies"],
        ["E4", "End-to-end test in a staging-like environment"],
    ]) + "\n")
    out.append("The script derives verification and evidence from `runs.jsonl`. "
               "The latest attempt of each run counts. P0 and goal evidence counts only from acceptance runs. "
               "An E4 run counts as E3 until a human confirms its environment.\n")

    # 6. Gap register.
    out.append("## 6. Gap Register\n")
    order = sorted(audit.gaps["gaps"], key=lambda g: (-BLOCK.get(audit.gap_block(g), 0), g["id"]))
    out.append(table(["ID", "Type", "Summary", "Impact", "Refs", "Blocks", "Owner", "Action", "Waiver"], [
        [g["id"], g.get("type"), g.get("summary"), g.get("impact"), g.get("refs"), audit.gap_block(g),
         g.get("owner") or "Unassigned", g.get("action"),
         audit.decisions.get(g["id"], {}).get("by")]
        for g in order
    ]) + "\n")

    # 7. Reverse trace.
    out.append("## 7. Reverse Trace\n")
    out.append(f"Method: {audit.surface.get('method') or '-'}\n")
    items = audit.surface["items"]
    counts = {k: sum(1 for i in items if i.get("classification") == k) for k in sorted(SURFACE_CLASSES)}
    out.append(", ".join(f"{k}: {v}" for k, v in counts.items()) + "\n")
    decided_by = {}
    for item in audit.cognition["decided"]:
        for ref in item.get("refs") or []:
            decided_by.setdefault(ref, []).append(item["id"])
    out.append(table(["ID", "Kind", "Location", "Description", "Class", "Exclusions", "Decision", "Gap"], [
        [i["id"], i.get("kind"), i.get("location"), i.get("description"), i.get("classification"),
         i.get("exclusions"), decided_by.get(i["id"]), audit.gaps_for(i["id"])]
        for i in items if i.get("classification") != "required"
    ]) + "\n")

    # 8. Test integrity.
    out.append("## 8. Test Integrity Audit\n")
    out.append(table(["Check", "Method", "Result"], [
        [s.get("check"), s.get("method"), s.get("result")] for s in audit.integrity["scans"]
    ]) + "\n")
    out.append(table(["ID", "Kind", "Location", "Summary", "Requirements", "Invalidates", "Gap"], [
        [f["id"], f.get("kind"), f.get("location"), f.get("summary"), f.get("requirements"),
         f.get("invalidates_runs"), audit.gaps_for(f["id"])]
        for f in audit.integrity["findings"]
    ]) + "\n")
    out.append("Mutation results:\n")
    out.append(f"A score below {MUTATION_FLOOR} needs a gap. The score covers only code that exists.\n")
    out.append(table(["ID", "Scope", "Tool", "Score", "Killed/Total", "Run", "Reason not run"], [
        [m.get("id"), m.get("scope"), m.get("tool"), m.get("score"), f"{m.get('killed')}/{m.get('total')}" if m.get("total") else "-",
         m.get("run"), m.get("not_run_reason")]
        for m in audit.integrity["mutation"]
    ]) + "\n")

    # 9. Production readiness.
    out.append("## 9. Production Readiness\n")
    rows = []
    for check in audit.readiness["checks"]:
        state = audit.rdy_state(check)
        rows.append([check["id"], check.get("category"), check.get("check"), state["status"], state["level"],
                     check.get("target"), check.get("measured"), state["runs"] or check.get("code"),
                     audit.gaps_for(check["id"]) or check.get("not_applicable")])
    out.append(table(["ID", "Category", "Check", "Status", "Evidence", "Target", "Measured", "Proof", "Gaps or N/A reason"], rows) + "\n")

    # 10. Cognition delta.
    out.append("## 10. Cognition Delta\n")
    out.append(f"Team model source: {audit.cognition.get('model_source') or '-'}\n")
    believes = audit.cognition["believes"]
    delta = [b for b in believes if b.get("delta") != "confirmed"]
    out.append(f"### Believes ({len(believes) - len(delta)} confirmed and not shown)\n")
    out.append(table(["ID", "Delta", "Team claim", "Actual behavior", "Evidence"], [
        [b["id"], b.get("delta"), b.get("team_claim"), b.get("text"), b.get("evidence")] for b in delta
    ]) + "\n")
    out.append("### Decided\n")
    out.append("The agent made these choices. The PRD did not specify them.\n")
    out.append(table(["ID", "Choice", "Alternatives", "Location", "Human decision", "By", "Reason"], [
        [d["id"], d.get("text"), d.get("alternatives"), d.get("location"),
         audit.decisions.get(d["id"], {}).get("decision") or "**Pending**",
         audit.decisions.get(d["id"], {}).get("by"), audit.decisions.get(d["id"], {}).get("reason")]
        for d in audit.cognition["decided"]
    ]) + "\n")
    out.append("### Unknown\n")
    out.append(table(["ID", "Question", "How to resolve", "Blocks"], [
        [u["id"], u.get("text"), u.get("how_to_resolve"), u.get("blocks")] for u in audit.cognition["unknown"]
    ]) + "\n")

    # 11. Reproduction appendix.
    out.append("## 11. Reproduction Appendix\n")
    out.append(f"Check out `{audit.commit}`. Run each command from the repo root.\n")
    out.append(table(["Run", "Attempt", "Outcome", "Claimed level", "Counted", "Source", "Covers", "Environment", "Command", "Log"], [
        [a["run"], a["attempt"], a["outcome"] + (f" ({a['reason']})" if a.get("reason") else ""), a["level"],
         "yes" if audit.usable(a) else "no", a["source"], a["covers"], a["env"], "`" + " ".join(a["cmd"]) + "`", a["log"]]
        for a in audit.runs
    ]) + "\n")

    path = audit.dir / "REPORT.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print(path)
    print(f"staging: {result['staging']['verdict']}; production: {result['production']['verdict']}")


def cmd_diff(args):
    old, new = Audit(args.old), Audit(args.new)
    old_gate, new_gate = old.gate(), new.gate()
    print(f"Commit: {old.commit[:12]} -> {new.commit[:12]}")
    for stage in ("staging", "production"):
        print(f"{stage}: {old_gate[stage]['verdict']} -> {new_gate[stage]['verdict']} "
              f"(blockers {len(old_gate[stage]['blockers'])} -> {len(new_gate[stage]['blockers'])})")
    print(f"Closed gaps: {cell(sorted(set(old.gap) - set(new.gap)))}")
    print(f"New gaps: {cell(sorted(set(new.gap) - set(old.gap)))}")

    def rank(audit, rid):
        state = audit.req_state(rid)
        row = audit.row.get(rid, {})
        return (row.get("implementation"), state["verification"], state["level"])

    print(f"New requirements: {cell(sorted(set(new.req) - set(old.req)))}")
    print(f"Removed requirements: {cell(sorted(set(old.req) - set(new.req)))}")
    for rid in sorted(set(old.req) & set(new.req)):
        before, after = rank(old, rid), rank(new, rid)
        if before == after:
            continue
        worse = (before[1] == "pass" and after[1] != "pass") or (
            before[1] == after[1] and LEVEL[after[2]] < LEVEL[before[2]])
        print(f"{'REGRESSION' if worse else 'CHANGE'} {rid}: {before} -> {after}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Pin a commit and freeze the inputs.")
    p.add_argument("--repo", default=".")
    p.add_argument("--prd", action="append", required=True)
    p.add_argument("--goal", action="append")
    p.add_argument("--independence", choices=["full", "reduced"], default="full")
    p.add_argument("--from", dest="from_dir", help="Earlier audit directory to carry forward.")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("run", help="Run a test command and record evidence.")
    p.add_argument("--dir", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--level", required=True, choices=["E2", "E3", "E4"])
    p.add_argument("--source", required=True, choices=["acceptance", "repo"])
    p.add_argument("--covers", default="", help="Comma-separated REQ, RDY, or G IDs. Omit for a record-only run.")
    p.add_argument("--pass-env", action="append", help="Host environment variable to pass. Repeat as needed.")
    p.add_argument("--env", required=True, help="Real dependencies and environment that the run uses.")
    p.add_argument("--expect-output", required=True, help="Regex. The log must match, so that a run of zero tests fails.")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("approve", help="Record human approval of the ledger.")
    p.add_argument("--dir", required=True)
    p.add_argument("--by", required=True)
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("decide", help="Record one human decision.")
    p.add_argument("--dir", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--decision", required=True, choices=["accepted", "rejected", "waived"])
    p.add_argument("--by", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_decide)

    p = sub.add_parser("validate", help="Check data files and references.")
    p.add_argument("--dir", required=True)
    p.add_argument("--only", help="Comma-separated: ledger,matrix,surface,integrity,readiness,cognition,gaps,runs.")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("gate", help="Compute the verdict. With --stage, exit 1 on NO-GO.")
    p.add_argument("--dir", required=True)
    p.add_argument("--stage", choices=["staging", "production"])
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("render", help="Write REPORT.md and verdict.json.")
    p.add_argument("--dir", required=True)
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("diff", help="Compare two audit directories.")
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)
    p.set_defaults(func=cmd_diff)

    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
