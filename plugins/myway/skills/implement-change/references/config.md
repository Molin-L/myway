# `.myway.toml` — per-repo configuration

**Optional.** The workflow runs with zero configuration; this file exists to
resolve the two things that cannot be inferred safely.

Place it at the repo root.

```toml
[version]
# Only set this if the repo has ONE unambiguous version source.
# When set, creating a new pre-release train also bumps this file
# and commits it as `chore(release): bump to X.Y.Z`.
file = "version.txt"

[verify]
# Commands run in order before pushing. All must exit 0.
# Overrides inference entirely.
commands = [
  "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release",
  "cmake --build build -j",
  "ctest --test-dir build --output-on-failure",
]

[branch]
# Pre-release train prefix. Rarely changed.
prefix = "pre-release"
```

## Verify-command inference

Used when `[verify].commands` is absent. First match wins:

| Detected | Commands |
|---|---|
| `.myway.toml` `[verify]` | as declared |
| `CMakeLists.txt` | configure into `build/` if absent, `cmake --build build -j`, then `ctest --test-dir build` if any test is registered |
| `pyproject.toml` with `uv.lock` | `uv sync`, `uv run pytest` |
| `pyproject.toml` | `pytest` |
| `Cargo.toml` | `cargo build`, `cargo test` |
| `package.json` with a `test` script | `npm test` (or the lockfile's package manager) |
| `Makefile` with a `test` target | `make test` |

Reuse an existing build directory rather than reconfiguring from scratch — the
feature worktree starts cold, and a needless full rebuild is the main cost of
working in a worktree.

**If nothing matches**, no local verification is possible. Say so explicitly in
the change request body:

```md
## Verification
⚠ No verify command could be determined for this repo. Not locally verified.
```

Never let an unverified change read as a verified one, and never invent a
plausible-looking test command to fill the gap.

## Why version files are opt-in

Repos disagree with each other and sometimes with themselves — no version at
all, one in a plain file, one hardcoded in a build file, or two that drift
apart. A rule that guessed would write the wrong version into a build. Opting
in makes the safe case explicit and leaves everything else untouched. See
`references/versioning.md`.
