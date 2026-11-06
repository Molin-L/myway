---
name: test-audit
description: Control test bloat in an agent-built codebase. Gate each new test, and remove low-value tests with per-test evidence and a before/after gate. Use this skill when writing, reviewing, or pruning tests, even if the user only says "too many tests", "overdesigned tests", "test bloat", "trim the tests", "are these tests useful", or "the agent added too many tests". Covers C++, Go, Rust, and Python.
---

# Test Audit

This skill controls two points:

1. **Inflow:** A new test must name the wrong behavior that it rejects.
2. **Stock:** A deleted test must have evidence that no protection goes with it.

If you trim only the stock, agents add the bloat again. Do the inflow gate first.

## Architecture

```text
INFLOW
Requirement ─► Named wrong behavior ─► Test ─► Authoring gate ─► prove ─► Merge
                                                     │              │
                                                     └── fail ──────┴─► Remove or rewrite

STOCK
collect before ─► Discovery agent ─► candidates.json ─► Independent judge ─► check
                                                                               │
              PR ◄─ dead code commit ◄─ gate ◄─ collect after ◄─ test-only commit
```

## Design Rules

- **Agents give judgment. The script gives status.** `test_audit.py` derives `rejected`, `ready`, and the gate verdict. Do not write these by hand.
- **The author does not judge itself.** Use a fresh agent to judge candidates. Do not show the test author the production patch before it writes the requirement.
- **Coverage is a floor, not the goal.** Coverage shows that a line runs. It does not show that a test checks the line.
- **A mutation score is not a proof.** Default operators change tokens. They do not produce a wrong reading of a requirement. Write contract mutants by hand with `prove`.
- **No deletion count is a success metric.** A target can drive discovery. Only evidence can approve a deletion.
- **Change tests first.** The gate needs stable production line numbers. Delete dead production code in the next commit.
- **Slow is not low value.** Do not delete a test because it is slow or static.

## Safety

- `test_audit.py` runs the commands in `config.json` with a shell. Read the config before you run it.
- Use test credentials and test environments only.
- Stop and ask the user if a test can place a real order, move funds, or change production data.

## Authoring Gate

Apply this gate before you add or change a test. A missing answer means: do not add the test.

1. What behavior, invariant, or independent contract does the test protect?
2. Which plausible wrong implementation does the test reject?
3. Why does existing coverage not reject it? Each contract has one owner test at the strongest boundary. Prefer a new table case to a new test.
4. Does the test need an export, flag, wrapper, or hook that no production caller uses? If yes, move the test to the real boundary.

Then check the test against the [junk patterns](#junk-patterns).

Prove the answer to question 2:

1. Commit the test.
2. Write the wrong behavior as a patch to production code.
3. Run `test_audit.py prove`. The test must pass before the patch and fail after it, for the expected reason.

A bug regression test must fail on the code before the fix. One regression test at the owner boundary covers one bug.

Prove the wrong behavior that matters. For an empty filter and a missing filter, the patch makes one act as the other. A syntax error or a crash proves nothing.

## Junk Patterns

These values go in the `pattern` field of a candidate.

| `pattern` | The test… |
|---|---|
| `no_assertion` | runs code and checks nothing |
| `tautology` | compares a value with itself, or checks a constant |
| `asserts_mock` | checks a mock, a mock call, or behavior that the mock supplies |
| `self_derived_expected` | gets the expected value from the code under test, or copies current output with no independent source |
| `duplicate_contract` | repeats a contract that a stronger test owns |
| `copied_inventory` | copies a list of fields, exports, or enum values and compares it with the source |
| `source_grep` | checks source text, when a cheaper contract check does not need it |
| `private_shape` | checks a private predicate or call shape that a real boundary already covers |
| `seam_only` | exists only to keep a test-only export, virtual call, flag, or wrapper |
| `dead_code_only` | is the only caller of a production path |
| `false_negative_control` | expects a rejection, but a different guard causes it |
| `misleading_name` | promises more than its input exercises |
| `implementation_coupled` | breaks when a refactor keeps the behavior |

Use `delete` for a test with no independent contract. Use `merge` for a repeated case that belongs in a table. Use `rewrite` for an `implementation_coupled` test that guards a real contract.

## Retention Bar

Keep a test that is the independent guard for any of these. Set `contract` in the candidate if you still propose a change. A human must then set `approved_by`.

- Public API, wire protocol, config, storage format, or migration
- Security or credential handling
- Risk checks, margin checks, position limits, and kill switches
- Order state transitions, including cancel, fill, and reject races
- Sequence numbers, replay determinism, and recovery
- Floating-point semantics: NaN, signed zero, rounding, tick conversion, and overflow
- Concurrency stress, memory ordering, and sanitizer targets
- Latency regressions and allocation-free guarantees on hot paths
- Call order, if the order is observable behavior
- Regressions with a credible failure mode

A test that fails at baseline can be a product defect. Investigate it. Do not delete it.

## Stock Workflow

Set `AUDIT=<skill-dir>/scripts/test_audit.py`. Set `D=.test-audit/<module>`. Add `.test-audit/` to `.git/info/exclude`. Set up the task list from these phases.

### Phase 0: Scope

Choose one module for one PR. Read `references/languages.md`, and write `$D/config.json`. Read `references/schema.md` for the fields. Use one branch.

### Phase 1: Collect

```bash
python3 "$AUDIT" collect --dir "$D" --snapshot before
```

Read `$D/snapshots/before.tsv`. Investigate each test that is not `pass` first. For a large repo, use `--match` to limit the scope.

### Phase 2: Discover

Discovery is read-only. Use a fresh agent. Give it the snapshot and the junk patterns.

If you only say "clean up", an agent stops too early. Give it a discovery target, for example: "Find the least useful 20% of the tests in this module."

For each candidate, read the whole test, the production owner, its callers, overlapping tests, and the history. Get the failure history from the forge. Run `git log --follow -- <file>` for the churn. Write `$D/candidates.json`. A zero in `unique_lines` is a lead, not a verdict.

### Phase 3: Judge

Use a separate fresh agent. Give it `candidates.json` and the code, but not the discovery reasoning. For each candidate, it tries to name a real regression that only this test catches. It removes a candidate if it can name one. Mark uncertain candidates for retention.

Then run:

```bash
python3 "$AUDIT" check --dir "$D"
```

Fix or remove each `blocked` candidate. Do not weaken the evidence to get `ready`. The check simulates the whole batch, so two duplicate tests cannot both go without a declaration.

Show the user each candidate with `contract` set. Only the user can give `approved_by`. If the user is absent, leave the field empty and keep the test.

### Phase 4: Test-Only Commit

Delete, merge, or rewrite the `ready` candidates. Change only the files that match `test_paths`. Commit.

For each new test or merge target, run `prove` at this commit. If you change the commit, run `prove` again.

```bash
python3 "$AUDIT" collect --dir "$D" --snapshot after
```

### Phase 5: Gate

Run the mutation tool on the production files in the batch, at the before and after commits. Normalize the output to one surviving mutant ID per line. Use `references/languages.md`.

```bash
python3 "$AUDIT" gate --dir "$D" --survivors-before <file> --survivors-after <file>
```

If a mutation tool is not available, pass `--no-mutation "<reason>"`. The gate records the reason. For code in the retention bar, get a tool working or prove the contract mutants by hand.

Do not change a failing gate to pass. A failure means that the batch loses protection, or that the evidence is wrong.

### Phase 6: Remove Dead Code

The `unlocks` entries list production lines that lost their only test. In a new commit, delete these lines and any test-only seam. Run the full test suite. Do not run the gate on this commit, because the line numbers change.

Keep each PR to one module. After the merge, start a new batch for the next module.

## Report

Put this in the PR body:

- The categories removed, and the production simplifications
- The output of `gate`
- Candidates that you retained after the judge step, and why
- Mutation status, and what the mutation run did not cover
- Production LOC and test LOC, as separate numbers
- Follow-up modules

Each batch has limits. Say them: a survivor comparison holds only for the mutants that the tool generated. A `collect` covers only the tests in its `--match` scope.

## References

- `references/languages.md`: config, seams, and mutation tools for each language
- `references/schema.md`: file fields and the rules for each status
