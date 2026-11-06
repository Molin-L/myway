# Schema

All files live in one batch directory, `$D`. The script writes everything except `config.json` and `candidates.json`.

```text
$D/
├── config.json         commands and path rules          (agent)
├── candidates.json     deletion evidence                (agents)
├── snapshots/
│   ├── before.json     per-test status and lines        (collect)
│   ├── before.tsv      sorted by unique_lines           (collect)
│   ├── after.json
│   └── after.tsv
├── proofs.jsonl        append-only proof records        (prove)
├── check.json          status of each candidate         (check)
└── gate.json           verdict and numbers              (gate)
```

## config.json

| Field | Required | Meaning |
|---|---|---|
| `build` | No | Runs before `collect`, and before each `prove` run in the temporary worktree. |
| `list` | Yes | Prints one test ID per line on stdout. |
| `run` | Yes | Runs one test. Reads `$TEST_ID`. Writes LCOV or a Go cover profile to `$TEST_OUT`. |
| `pass_pattern` | Yes | Regex that must match the output of one passing test. Make it match exactly one test, so that a run of zero tests is `invalid`. |
| `source` | Yes | Globs for production paths, for example `src/*`. `*` matches `/`. |
| `test_paths` | Yes | Globs for test paths. These paths are not production coverage. |
| `strip_prefix` | No | Prefix to remove from coverage paths, for example a Go module path. |
| `inline_test_marker` | No | Text that starts an inline test module, for example `#[cfg(test)]`. Lines from the marker to the end of the file are test code. The test module must be the last item in the file. |
| `timeout` | No | Seconds for each command. The default is 600. |

Both snapshots must use the same config.

## Test status

| Status | Rule |
|---|---|
| `pass` | Exit code 0, `pass_pattern` matches, and `$TEST_OUT` exists. |
| `fail` | Exit code is not 0. |
| `invalid` | Exit code 0, but `pass_pattern` does not match or `$TEST_OUT` is missing. |
| `timeout` | The command did not finish in `timeout` seconds. |

`unique_lines` is the number of production lines that only this test covers, in the `--match` scope.

## candidates.json

```json
{
  "candidates": [
    {
      "test": "tests/test_margin.py::test_legacy_round",
      "path": "tests/test_margin.py",
      "action": "delete",
      "pattern": "dead_code_only",
      "detects": "A wrong rounding result in legacy_round.",
      "stronger_proof": {"none": "No production code calls legacy_round."},
      "non_test_callers": "None. Searched src/ for legacy_round.",
      "history": "Added by an agent in abc1234. No failure in CI history.",
      "unlocks": [{"path": "src/desk/margin.py", "lines": "12-13"}],
      "contract": null,
      "approved_by": null,
      "risk": "Low. The path has no caller.",
      "validation": "pytest tests/test_margin.py"
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `test` | The test ID in the before snapshot. |
| `path` | The file that holds the test, at the before commit. |
| `action` | `delete`, `merge`, or `rewrite`. |
| `pattern` | A value from the junk pattern table in `SKILL.md`. |
| `detects` | The failure that the test can detect now. |
| `stronger_proof` | `{"test": id}` for the test that owns the contract, or `{"none": reason}`. For `merge` and `rewrite`, the target can be a new test. |
| `non_test_callers` | The production callers of the covered path or seam. |
| `history` | The reason that the test exists, and its failure history. |
| `unlocks` | Production lines that lose all coverage. Each entry has `path` and `lines`, for example `12-13`. Use `[]` if there are none. |
| `contract` | The contract from the retention bar, or `null`. |
| `approved_by` | The human who approved a change to a `contract` test, or `null`. The script cannot prove this field. An agent must not fill it for an absent human. |
| `risk` | The risk of the change. |
| `validation` | The focused command to run after the change. |

### Candidate status

`check` gives `ready` only if all of these are true:

- All required fields have a value.
- The test is `pass` in the before snapshot.
- `path` exists at the before commit.
- `stronger_proof` is a passing test that is not a delete candidate, or a reason.
- A candidate with `contract` has `approved_by`.
- The whole batch, deleted together, loses no production line outside `unlocks`.
- No other test covers a line in `unlocks`.

## proofs.jsonl

| Outcome | Rule |
|---|---|
| `rejected` | The test passes at baseline, the patched code builds, the test fails, and `--expect` matches the output. |
| `survived` | The test still passes with the patch. The test does not reject this wrong behavior. |
| `invalid` | The baseline fails, the patch does not apply or build, `--expect` matches the baseline output, or the test failed for a different reason. |

`prove` exits with 0 only for `rejected`. The working tree must be clean for tracked files. A patch can change production files only.

## Gate

`gate` gives `pass` only if all of these are true:

- Both snapshots use the same config and the same `--match` scope.
- The after commit descends from the before commit, and the commits differ.
- The diff changes only test paths, or lines after `inline_test_marker`.
- Each candidate is `ready`.
- Each after test is `pass`.
- Each removed test has a `ready` candidate.
- Each `stronger_proof` test passes after the change.
- Each added test has a `rejected` proof at the after commit.
- Each production line that lost coverage is in `unlocks`.
- No mutant survives after the change that did not survive before.

Give `--survivors-before` and `--survivors-after`, or give `--no-mutation REASON`. The gate exits with 0 for `pass`, 1 for `fail`, and 2 for a usage error.
