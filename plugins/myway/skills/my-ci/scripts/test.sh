#!/usr/bin/env bash
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# ============================================================
# Test — the pre-merge gate test run
# ============================================================
# Contract:
#   * consumes build/ produced by build.sh (do not rebuild here)
#   * exit non-zero on any test failure
#   * emit junit.xml at the repo root when the tool supports it — both
#     templates pick it up as a test report
#
# A repo with no detectable tests FAILS this script rather than passing
# silently: never let an unverified change read as a verified one. Customize
# or delete the job if the repo genuinely has nothing to test.
# ============================================================

myci_log "test (${MYCI_PROJECT})"

# ============================================================
# CUSTOMIZE — replace the inference below with this repo's real test run.
# ============================================================
if [ -f CMakeLists.txt ]; then
  [ -d build ] || myci_die "build/ missing — was the build artifact not consumed?"
  ctest --test-dir build --output-on-failure --output-junit "$PWD/junit.xml"
elif [ -f Cargo.toml ]; then
  cargo test --release --locked
elif [ -f pyproject.toml ] && [ -f uv.lock ]; then
  uv run pytest --junitxml=junit.xml
elif [ -f pyproject.toml ]; then
  pytest --junitxml=junit.xml
elif [ -f package.json ]; then
  npm test
elif [ -f go.mod ]; then
  go test ./...
elif [ -f Makefile ] && grep -qE '^test:' Makefile; then
  make test
else
  myci_die "no test runner detected — customize ci/scripts/test.sh (or remove the test job if this repo truly has no tests)"
fi

myci_log "tests complete"
