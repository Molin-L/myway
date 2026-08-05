#!/usr/bin/env bash
# Best-effort by design: NO `set -e`. This runs after a production release
# has already shipped; nothing here may turn that green pipeline red. Every
# failure path warns (and notifies, if configured) and exits 0.
set -uo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# ============================================================
# Back-merge release/X.Y.Z → default branch
# ============================================================
# Opens (or reuses) an auto-merge MR/PR from the shipped release branch into
# the default branch, so the default branch always reflects what was last
# released. Override the target with BACKMERGE_TARGET_BRANCH.
# ============================================================

SOURCE="${MYCI_BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null)}"
if [[ ! "$SOURCE" =~ ^release/[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  myci_warn "branch '${SOURCE}' is not release/X.Y.Z — skipping back-merge"
  exit 0
fi

TARGET="${BACKMERGE_TARGET_BRANCH:-$MYCI_DEFAULT_BRANCH}"
myci_log "back-merge: '${SOURCE}' -> '${TARGET}'"

myci_open_backmerge "$SOURCE" "$TARGET"
exit 0
