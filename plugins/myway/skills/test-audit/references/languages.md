# Languages

Each section gives a `config.json`, the seams to look for, and the mutation command. Change the paths for your repo. Run `collect --match <one test>` first to confirm the config.

Use a separate coverage build. Do not measure latency with this build.

## C++ (GoogleTest, Clang)

Compile the tests and the production code with `-fprofile-instr-generate -fcoverage-mapping`. Link the tests with `-fprofile-instr-generate`. Use `llvm-cov -object <lib>` if production code is in a shared library.

The test ID is `<binary>:<suite>.<name>`.

```json
{
  "build": "cmake -S . -B build-cov -DCMAKE_BUILD_TYPE=Debug -DCOVERAGE=ON >/dev/null && cmake --build build-cov -j >/dev/null",
  "list": "for b in build-cov/tests/*_test; do \"$b\" --gtest_list_tests | awk -v b=\"$b\" '/^[^ ]/{s=$1} /^ /{print b \":\" s $1}'; done",
  "run": "b=\"${TEST_ID%%:*}\"; LLVM_PROFILE_FILE=\"$TEST_OUT.raw\" \"$b\" --gtest_filter=\"${TEST_ID#*:}\" && llvm-profdata merge -sparse \"$TEST_OUT.raw\" -o \"$TEST_OUT.data\" && llvm-cov export -format=lcov -instr-profile=\"$TEST_OUT.data\" \"$b\" > \"$TEST_OUT\"",
  "pass_pattern": "\\[  PASSED  \\] 1 test",
  "source": ["src/*"],
  "test_paths": ["tests/*", "*_test.cc", "*_test.cpp"]
}
```

**Seams:** a `virtual` that exists only for a mock, `#ifdef UNIT_TEST`, `FRIEND_TEST`, `#define private public`, a getter that only tests call, and a template parameter with one real type. A seam on a hot path has a production cost. Remove these first.

**Do not treat these as bloat without proof:** TSan and ASan targets, stress tests, ABI and `sizeof` checks on wire structs, and float edge cases.

**Mutation (Mull):** Build with `-fpass-plugin=<mull-ir-frontend>` and `-g -grecord-command-line`. Mull must match your LLVM version. Confirm that a Mull build exists for your LLVM before you plan on it.

```bash
mull-runner-NN build-mull/tests/margin_test 2>&1 \
  | grep 'warning: Survived:' | sed 's/ warning: Survived:/ /' | sort -u > survivors.txt
```

## Go

The test ID is `<package>:<TestName>`. Use `strip_prefix` for the module path.

```json
{
  "list": "go list ./... | while read -r p; do go test -list '.*' \"$p\" | grep '^Test' | sed \"s|^|$p:|\"; done",
  "run": "go test -count=1 -v -run \"^${TEST_ID##*:}\\$\" -coverpkg=./... -coverprofile=\"$TEST_OUT\" \"${TEST_ID%%:*}\"",
  "pass_pattern": "^--- PASS: ",
  "source": ["internal/*", "pkg/*"],
  "test_paths": ["*_test.go"],
  "strip_prefix": "example.com/desk/"
}
```

**Seams:** `export_test.go`, a package-level function variable that only tests replace, and an interface with one real implementation.

**Do not treat these as bloat without proof:** `go test -race` targets and fuzz targets with a seed corpus.

**Mutation (gremlins):** The tool is pre-1.0, and its targeting is limited. Confirm the output format on your version.

```bash
gremlins unleash ./internal/margin | grep LIVED | sed 's/^ *//' | sort -u > survivors.txt
```

## Rust

`cargo-llvm-cov` needs the `llvm-tools` rustup component. Inline test modules need `inline_test_marker`. The module must be the last item in the file. The clippy lint `items_after_test_module` checks this.

```json
{
  "list": "cargo test --lib -- --list --format=terse 2>/dev/null | sed -n 's/: test$//p'",
  "run": "cargo llvm-cov --lib --lcov --output-path \"$TEST_OUT\" -- --exact \"$TEST_ID\"",
  "pass_pattern": "test result: ok\\. 1 passed",
  "source": ["src/*"],
  "test_paths": ["tests/*"],
  "inline_test_marker": "#[cfg(test)]"
}
```

This config covers library unit tests. Add a separate batch for integration tests.

**Seams:** a `pub(crate)` item that only tests use, a `#[cfg(test)]` field in a production struct, and `mockall` on a trait with one real implementation.

**Do not treat these as bloat without proof:** `loom` and Miri targets, and `proptest` properties.

**Mutation (cargo-mutants):** The command exits with a non-zero code if a mutant survives. This is normal here.

```bash
cargo mutants --file src/margin.rs --no-shuffle
sort mutants.out/missed.txt > survivors.txt
```

## Python (pytest)

```json
{
  "list": "python3 -m pytest --collect-only -q -p no:cacheprovider | grep '::'",
  "run": "export COVERAGE_FILE=\"$TEST_OUT.data\"; python3 -m coverage run --source=src -m pytest -q -p no:cacheprovider \"$TEST_ID\" && python3 -m coverage lcov -q -o \"$TEST_OUT\"",
  "pass_pattern": "^1 passed",
  "source": ["src/*"],
  "test_paths": ["tests/*"]
}
```

**Seams:** an `if TESTING:` branch, `monkeypatch` on a private name, and a module-level hook with no production caller.

**Mutation (mutmut):**

```bash
mutmut run
mutmut results | grep ': survived$' | sed 's/^ *//; s/: survived$//' | sort > survivors.txt
```

## Other frameworks

Any framework works if it can:

1. List test IDs.
2. Run one test alone.
3. Write LCOV or a Go cover profile.

Make `pass_pattern` match only a run of one test.

## Contract mutants

Tools mutate tokens. They do not produce a wrong reading of a requirement. For code in the retention bar, write patches by hand and run `prove`. Examples:

- Change `<=` to `<` at a margin limit.
- Treat a cancel-after-fill as a successful cancel.
- Apply a fill twice after a replay.
- Treat NaN as zero.
- Round a tick toward the wrong side.
- Drop the sequence gap check.
