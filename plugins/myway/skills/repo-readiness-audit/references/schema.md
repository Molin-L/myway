# Data Files

All files are in the audit directory: `<repo>/.audit/<commit12>/`.
`audit.py init` writes empty templates. The role that owns a file sets `status` to `complete` when it finishes. `ledger.json` has no `status`.

Do not write verification status, evidence levels, or goal status into any file. The script derives them from `runs.jsonl`.
Do not edit `runs.jsonl`, `approvals.json`, `verdict.json`, or `REPORT.md` by hand.

Each role checks its own file with `audit.py validate --dir D --only <section>`. The sections are `ledger`, `matrix`, `surface`, `integrity`, `readiness`, `cognition`, `gaps`, and `runs`.

## Layout

```text
.audit/<commit12>/
├── baseline.json     commit, frozen input hashes, environment
├── inputs/           frozen PRD and goal text
├── ledger.json       goals, requirements, exclusions
├── acceptance/       independent tests, PLAN.md, not_testable.json
├── runs.jsonl        append-only run records
├── evidence/         one log for each run attempt
├── matrix.json       forward trace
├── surface.json      reverse trace
├── integrity.json    test integrity audit
├── readiness.json    production readiness checks and goal measurements
├── gaps.json         gap register
├── cognition.json    Believes, Decided, Unknown
├── approvals.json    human decisions
├── verdict.json      gate output
├── REPORT.md         rendered report
└── prior/            earlier audit data, when you use --from
```

## File Ownership

| File | Owner | Refers to gaps? |
|---|---|---|
| `ledger.json` | Ledger Extractor | No |
| `acceptance/` | Acceptance Test Author | No |
| `matrix.json` | Forward Tracer | No |
| `surface.json` | Reverse Tracer | No |
| `integrity.json` | Test Integrity Auditor | No |
| `readiness.json` | Readiness Auditor | No |
| `cognition.json`, `gaps.json` | Cognition Reviewer | Yes |

Links go one way. A gap or a Decided entry refers to items through `refs`. Earlier roles do not need gap IDs.

## Evidence Levels

| Level | Evidence | Example |
|---|---|---|
| E0 | Agent statement only | "All tests pass" in a summary |
| E1 | Static inspection | Code read, or a document exists |
| E2 | Test with mocks or with a call inside the process | Unit test |
| E3 | Test of the real running process, through its public interface, with all real dependencies | Service with a real database in Docker. A service with no external dependency qualifies when the test runs the real process. |
| E4 | End-to-end test in a staging-like environment | Deployed build with real network and config |

An E4 run counts as E3 until a human accepts it with `audit.py decide --id RUN-x --decision accepted`. A local process does not qualify as E4.

## Run Rules

- The latest attempt of each run ID counts.
- A failing run fails all IDs that it covers.
- Mixed outcomes in one run ID give `unstable`, which is not a pass. This includes a test that changed after a failure. To clear this state, the Test Integrity Auditor must invalidate the failed attempt with a `test_defect` or `setup_failure` finding.
- Attempts on a dirty tree or another commit do not count. A clean attempt can replace them.
- P0 and goal evidence counts only from `--source acceptance`.
- A run with no `--covers` is a record only. Use this for mutation tools and diagnostics.
- A goal run must exit with an error when the measured value misses the target. The script derives the goal status from the exit status.
- `run` starts the command with a clean environment: `PATH`, `LANG`, `LC_ALL`, `TMPDIR`, and a private `HOME`. Give test settings in the command, for example `env KEY=test pytest ...`. Use `--pass-env NAME` only for non-secret tool settings, such as `GOCACHE` or `DOCKER_HOST`.

## ledger.json

```json
{
  "goals": [{
    "id": "G-001", "text": "...", "metric": "...", "target": "...",
    "source": {"doc": "PRD.md", "section": "1", "quote": "exact words from the doc"},
    "open_question": null
  }],
  "requirements": [{
    "id": "REQ-001", "priority": "P0", "priority_source": "prd",
    "text": "One testable behavior.",
    "acceptance": ["Given X, when Y, then Z."],
    "source": {"doc": "PRD.md", "section": "3.2", "quote": "exact words from the doc"},
    "open_question": null
  }],
  "exclusions": [{
    "id": "EXC-001", "text": "...",
    "source": {"doc": "PRD.md", "section": "2", "quote": "..."}
  }]
}
```

- `priority_source`: `prd` or `proposed`.
- `doc` is the exact file name in `inputs/`.
- `quote` must appear in that file. The script checks this. It ignores case, `*`, backticks, and white space.
- An `open_question` on a P0 or a goal blocks both stages.
- Use a stable ID across audits. Do not renumber.

## acceptance/not_testable.json

Optional. The Acceptance Test Author writes this file. It gives `not_testable` verification.

```json
{"REQ-009": "The PRD defines no way to reach the filled state."}
```

## matrix.json

```json
{
  "status": "complete",
  "requirements": [{
    "id": "REQ-001",
    "implementation": "complete",
    "code": ["src/orders.py:10-48"],
    "entrypoint": "POST /v1/orders -> create_order()",
    "notes": ""
  }],
  "limits": []
}
```

- `implementation`: `complete`, `partial`, `stub`, `missing`, or `divergent`.
- `code`: `path`, `path:line`, or `path:start-end` at the baseline commit. The script checks `code` fields. It does not check `location` or `evidence` fields.
- `limits`: What this role did not check. All `limits` lists go in the report.

## surface.json

```json
{
  "status": "complete",
  "method": "How the role enumerated the surface.",
  "items": [{
    "id": "SURF-001",
    "kind": "endpoint",
    "location": "src/admin.py:12",
    "description": "...",
    "classification": "unrequested",
    "requirements": [],
    "exclusions": ["EXC-001"]
  }],
  "limits": []
}
```

- `kind`: `endpoint`, `cli`, `job`, `config`, `dependency`, `network`, `filesystem`, `side_effect`, or `other`.
- `classification`: `required`, `supporting`, or `unrequested`.
- A `required` item needs known requirement IDs.
- `exclusions`: The exclusion IDs that this item violates.

## integrity.json

```json
{
  "status": "complete",
  "scans": [{"check": "Skipped tests", "method": "rg 'skip|xfail' tests/", "result": "2 hits"}],
  "findings": [{
    "id": "INT-001", "kind": "mocked_sut", "location": "tests/test_x.py:20",
    "summary": "...", "requirements": ["REQ-001"], "invalidates_runs": ["RUN-010"]
  }],
  "mutation": [{
    "id": "MUT-001", "scope": "P0: src/risk.py", "tool": "mutmut",
    "score": 0.72, "killed": 18, "total": 25, "run": "RUN-050", "not_run_reason": null
  }],
  "limits": []
}
```

- `kind`: `stub`, `todo`, `hardcoded_return`, `swallowed_error`, `skipped_test`, `tautological_assert`, `mocked_sut`, `level_overclaim`, `unwired_code`, `test_defect`, `setup_failure`, or `other`.
- `invalidates_runs`: `RUN-010` removes all attempts. `RUN-010#2` removes one attempt.
- `mutation` needs at least one entry. A `score` needs a `run`. An entry without a score needs `not_run_reason`.
- A score below 0.7 needs a gap.

## readiness.json

```json
{
  "status": "complete",
  "checks": [{
    "id": "RDY-001", "category": "rollback", "check": "...",
    "target": null, "measured": null,
    "static_result": "pass", "code": ["docs/rollback.md"], "method": null,
    "not_applicable": null
  }],
  "goals": [{
    "id": "G-001", "measured": "p99 41 ms at 100 req/s", "post_launch": null, "notes": ""
  }],
  "limits": []
}
```

- `category`: `failure`, `recovery`, `idempotency`, `security`, `secrets`, `config`, `performance`, `observability`, `migration`, or `rollback`. Each category needs at least one check.
- `static_result`: `pass`, `fail`, or `null`. It gives E1 evidence, and it needs `code` or `method`. A run that covers the check takes priority.
- `not_applicable`: A reason. A human must accept it with `decide`.
- `goals`: One row for each ledger goal. Use `post_launch` only when no pre-production environment can measure the goal. Give the reason. A human must accept it.

## gaps.json

```json
{
  "status": "complete",
  "gaps": [{
    "id": "GAP-001", "type": "missing", "summary": "...", "impact": "...",
    "refs": ["REQ-001", "INT-002"], "blocks": "staging", "owner": "", "action": "..."
  }]
}
```

- `type`: `missing`, `partial`, `stub`, `divergent`, `hollow_test`, `prd_ambiguity`, `unrequested`, `not_tested`, or `readiness`.
- `blocks`: `staging`, `production`, or `none`. The script raises this value to the minimum for the references. It does not lower it.

Minimum block:

| Reference | Minimum block | Waiver |
|---|---|---|
| Failing or incomplete P0 requirement | staging | Not valid |
| Goal with `not_met` status | staging | Not valid |
| Goal with other status | production | Not valid |
| Failing or incomplete P1 requirement | production | Valid |
| P2 requirement, or a requirement that passes | none | Valid |
| Exclusion (`EXC-`) | staging | Valid |
| Readiness: rollback, security, secrets | staging | Valid |
| Other readiness check | production | Valid |
| Rejected agent choice (`D-`) | production | Valid |

A gap needs a reference for each of these items:

- A requirement that is not `complete`, or that does not pass.
- A goal that is `not_met`, `not_measured`, or `unstable`.
- A readiness check that is `fail`, `unstable`, or `not_tested`.
- An `unrequested` surface item with no Decided entry.
- An exclusion that a surface item violates.
- An integrity finding with requirements or invalidated runs. `test_defect` and `setup_failure` do not need a gap.
- A mutation score below 0.7.

Keep one gap for one defect. Do not merge unrelated defects, because a waiver applies to the whole gap.

## cognition.json

```json
{
  "status": "complete",
  "model_source": "docs/cognition/ or PRD and README",
  "believes": [{
    "id": "B-001", "delta": "contradicted", "team_claim": "...", "text": "...",
    "evidence": ["RUN-010", "src/x.py:10"]
  }],
  "decided": [{
    "id": "D-001", "text": "...", "alternatives": "...", "location": "src/x.py:10",
    "refs": ["REQ-001", "SURF-003"]
  }],
  "unknown": [{
    "id": "U-001", "text": "...", "how_to_resolve": "...", "blocks": "production", "refs": ["REQ-002"]
  }],
  "limits": []
}
```

- `delta`: `new`, `confirmed`, or `contradicted`.
- An Unknown gets the same minimum block as a gap with the same `refs`.
- Use a stable ID across audits.

## Gate Rules

| Stage | Rule |
|---|---|
| Both | All data is valid. A human approved the current ledger. HEAD is the baseline. The tree is clean. Each agent choice has a human decision. Each not-applicable status has human acceptance. A P0 or goal has no open question. A human accepted reduced independence, if it applies. |
| Staging | Each P0 is complete and passes at E3 or higher from acceptance runs. Rollback, security, and secrets checks pass. No goal is `not_met`. No gap or Unknown blocks staging. |
| Production | All staging rules. Each P0 passes at E4. Each P1 is complete and passes at E3 or higher. Each goal is `met` at E4, or `post_launch` with human acceptance. Security, secrets, and config checks pass. All other readiness checks pass at E4. A human confirmed each E4 environment. No gap or Unknown blocks production. |

A gap carries its linked items. One defect gives one blocker line.
