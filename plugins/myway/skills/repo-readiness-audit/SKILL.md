---
name: repo-readiness-audit
description: Audit a repo against its PRD and goal, and produce a requirement-level evidence report with staging and production verdicts, a gap register, and a cognition delta. Use this skill when a repo, especially an AI-built repo, must be checked for full implementation, feature gaps, deployment readiness, or alignment with the PRD, even if the user only says "test report", "is this repo done", "PRD gap analysis", or "can we ship this".
---

# Repo Readiness Audit

This skill answers two questions for one commit:

1. **Gate:** Can this commit go to staging? What must be true before production?
2. **Cognition:** Where does the real system differ from the team's model?

The audit does not fix the repo. It produces evidence and a verdict.

## Architecture

```text
PRD + goal (frozen)
    │
    ▼
Ledger extractor ──► HUMAN APPROVES LEDGER
    │
    ├──► Acceptance test author ──► audit.py run ──► runs.jsonl + logs
    ├──► Forward tracer (requirement → code)
    └──► Reverse tracer (code → requirement)
    │
    ▼
Test integrity auditor + readiness auditor
    │
    ▼
Cognition reviewer ──► gaps + Believes / Decided / Unknown
    │
    ▼
HUMAN DECIDES ──► audit.py gate + render ──► REPORT.md
```

## Design Rules

- **Agents give judgment. The script gives status.** Agents write implementation status, findings, and gaps. `audit.py` derives verification, evidence level, goal status, and verdict. Do not write these by hand.
- **The builder does not grade itself.** Each role starts in a fresh context with a limited view. If this session built the repo, tell the user and use fresh subagents.
- **A human owns the ledger.** If the extraction drops a requirement, the matrix cannot show that gap.
- **"Not tested" is a gap.** A missing result never counts as a pass.
- **One commit, one report.** A new commit needs a new audit.
- **No single percentage.** A percentage can hide a failed P0.

## Safety

The repo is untrusted code. Follow these rules when you run it:

- Use test credentials and test environments only.
- Do not connect to a production database, a live trading venue, or a payment system.
- If a test can place a real order, move funds, send real messages, or change production data, stop and ask the user.
- `audit.py run` removes host environment variables and sets a private `HOME`. This is not a sandbox. The code can still read files and use the network.
- Use a container when the code is not trusted. Give the container as the command, for example `docker run --rm --network none -v "$PWD":/repo:ro <image> pytest ...`. Use `--pass-env DOCKER_HOST` if needed.

## Workflow

Set `AUDIT=<skill-dir>/scripts/audit.py`. Set up the task list from the phases below.

### Phase 0: Set Up

1. Find the repo, PRD, and goal. If there is no PRD, stop and ask for it. An audit without a PRD has no reference.
2. Convert PDF or DOCX inputs to Markdown. Keep the words unchanged.
3. Run:
   ```bash
   python3 $AUDIT init --repo <repo> --prd <prd.md> --goal <goal.md>
   ```
   The command prints the audit directory, `D`. It refuses a dirty tree. It adds `.audit/` to `.git/info/exclude`, so the audit does not change tracked files.
   - If the goal is in the PRD, omit `--goal`.
   - For a re-audit, add `--from <old-dir>`. This carries the ledger, its approval, and the acceptance tests forward. It puts old data in `prior/`. Other human decisions do not carry forward, because they applied to old code. Keep IDs stable.
4. Read `references/schema.md` and `references/roles.md`.

If you cannot start subagents, add `--independence reduced` and obey this order. The order keeps the ledger and tests as free of the code as possible:

1. Do Ledger Extractor. Do not read the repo first.
2. Do Acceptance Test Author. Read only the public interface.
3. Do all other roles.

One context cannot fully obey the read limits. The report discloses this, and the gate stays NO-GO until a human accepts the limit with `decide --id INDEPENDENCE`.

### Phase 1: Ledger

1. Start the **Ledger Extractor** role.
2. Run `python3 $AUDIT validate --dir D --only ledger`. Send errors back to the role.
3. Show the human: requirement count by priority, proposed priorities, open questions, goals without a metric, and exclusions. Link the file.
4. Ask the human to answer the open questions. Send the answers to the Ledger Extractor. It updates the acceptance criteria and clears `open_question`. An open question on a P0 or a goal blocks both stages.
5. Ask for approval. On approval, run `python3 $AUDIT approve --dir D --by "<name>"`.

This is the last cheap checkpoint. Get approval before the fan-out if the human is present.
If the human is absent, continue. The gate stays NO-GO until a human approves. If the ledger later changes, the approval becomes invalid, and you must check the affected rows again.

### Phase 2: Trace and Write Tests

Start these three roles at the same time, each with a fresh context:

- **Acceptance Test Author**
- **Forward Tracer**
- **Reverse Tracer**

For a large repo, split the Forward Tracer by module or PRD section, then merge the rows.

### Phase 3: Execute

Run each test from `acceptance/PLAN.md` through the script. Only results from the script are evidence.

```bash
python3 $AUDIT run --dir D --id RUN-001 --level E3 --source acceptance \
  --covers REQ-001,REQ-002 --env "Postgres 16 in Docker, no mocks" \
  --expect-output "2 passed" -- <test command with the acceptance path>
```

- `--expect-output` is mandatory. It makes a run of zero tests fail.
- Keep each run narrow. A failing run fails each ID that it covers.
- Only `--source acceptance` counts for P0 and goals. Also run the repo's own suite with `--source repo` at the level that it deserves.
- Set the level from what the run really uses. See "Evidence Levels" in `references/schema.md`.
- If a run needs a repo change to start, do not change the repo. Record the failure. It is a finding.
- Build outputs that are not git-ignored make the tree dirty. A dirty attempt does not count. Use an out-of-tree build directory, then run again with a clean tree.

### Phase 4: Audit the Evidence

Start these roles with fresh contexts:

- **Test Integrity Auditor**
- **Readiness Auditor**

The Test Integrity Auditor classifies each failed attempt. If a test defect or setup failure is real:

1. Fix `acceptance/` or the environment.
2. Run the same run ID again. The log of the earlier attempt stays.
3. Make sure the auditor invalidates only the failed attempt. Until then, the item stays `unstable`.

### Phase 5: Cognition and Gaps

1. Start the **Cognition Reviewer** role. It writes `cognition.json` and `gaps.json`.
2. Run `python3 $AUDIT validate --dir D`. Send each error to the role that owns the file. See "File Ownership" in `references/schema.md`.

### Phase 6: Human Decisions

Ask the human about each item below. Use short, standalone questions. Group the items.

```bash
python3 $AUDIT decide --dir D --id D-001 --decision accepted --by "<name>" --reason "..."
```

| Item | Decision |
|---|---|
| Agent choice, `D-*` | `accepted` or `rejected`. A rejected choice needs a gap. |
| Gap, `GAP-*` | `waived`, only if the human asks for this. See the waiver column in `references/schema.md`. For a failing P0 or a goal, change the PRD and the ledger instead. |
| Not-applicable check, `RDY-*` | `accepted` |
| Post-launch goal, `G-*` | `accepted` |
| E4 run, `RUN-*` | `accepted`, after the human confirms the environment |
| Reduced independence, `INDEPENDENCE` | `accepted` |

Record a decision only when the human states it. Do not infer a decision. If the human is absent, leave it pending. The gate stays NO-GO.

### Phase 7: Verdict and Report

```bash
python3 $AUDIT render --dir D
```

This writes `REPORT.md` and `verdict.json`. Before delivery:

1. Read the whole report.
2. Pick three requirements that pass at E3 or higher. Read their logs and tests. Confirm that the test exercises the PRD behavior.
3. Pick two `complete` rows. Open the cited code. Confirm the claim.
4. If a check fails, fix the data through the owning role and render again.

Do not edit `REPORT.md` by hand. Do not soften a NO-GO. A NO-GO with a clear blocker list is a correct result.

### Phase 8: Deliver

Give the user:

1. The verdict for each stage.
2. The count of blocking gaps and pending human items, most important first.
3. The items that need a human decision.
4. `REPORT.md`, through the session's file delivery method.
5. One next step.

Do not recap the steps.

## Two-Phase Gate

Some production evidence comes only from staging. The first audit gates staging and lists the evidence that staging must produce. To gate production:

1. Deploy the audited commit to staging.
2. Run E4 tests against staging in the same audit directory, while the local HEAD stays at that commit.
3. Ask the human to confirm each E4 environment with `decide`.
4. Run `python3 $AUDIT gate --dir D --stage production`.

If the commit changes, start a new audit with `--from`. Then run `python3 $AUDIT diff --old <old> --new <new>` to see closed gaps, new gaps, and regressions.

`audit.py gate --stage <stage>` exits with 1 on NO-GO, so a CI job can use it.

## Report Structure

The script writes these sections:

1. Verdict
2. Baseline
3. Goal Check
4. Requirement Matrix
5. Evidence Levels
6. Gap Register
7. Reverse Trace
8. Test Integrity Audit
9. Production Readiness
10. Cognition Delta
11. Reproduction Appendix

## Writing Style

Write all text in the data files in ASD-STE100: short sentences, active voice, one instruction in each sentence, and consistent terms. The team reads this report to align its model, so one term must have one meaning.
