#!/usr/bin/env bash
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# ============================================================
# Build — the pre-merge gate build (build-once)
# ============================================================
# Contract:
#   * exit non-zero on failure
#   * put everything test/package need under build/ — that directory is the
#     job artifact and flows to later jobs; nothing downstream rebuilds
# ============================================================

myci_log "build (${MYCI_PROJECT})"

# ============================================================
# CUSTOMIZE — replace the inference below with this repo's real build.
# The inference mirrors the verify table in the myway `implement-change`
# skill (references/config.md) so CI and local verification agree.
# ============================================================
if [ -f CMakeLists.txt ]; then
  cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
  cmake --build build -j "$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
elif [ -f Cargo.toml ]; then
  cargo build --release --locked
elif [ -f pyproject.toml ] && [ -f uv.lock ]; then
  uv sync --frozen
elif [ -f pyproject.toml ]; then
  python3 -m pip install -e .
elif [ -f package.json ]; then
  npm ci
  npm run build --if-present
elif [ -f go.mod ]; then
  mkdir -p build
  go build -o build/ ./...
elif [ -f Makefile ]; then
  make
else
  myci_die "no build system detected — customize ci/scripts/build.sh for this repo"
fi

myci_log "build complete"
