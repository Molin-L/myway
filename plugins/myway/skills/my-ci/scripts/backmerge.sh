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
#
# The gate is the release TAG, not the ship job's exit status. A ship is not
# atomic: by the time publish.sh runs, create_release_tag.sh has already
# pushed X.Y.Z and the forge release exists. That history is permanent, so a
# registry refusing an artifact afterwards must not leave the default branch
# behind a released tag — which is precisely what happened when this ran as
# the last step of a ship job that failed at the npm publish. Conversely, if
# there is no tag then nothing shipped and there is nothing to sync back.
# ============================================================

SOURCE="${MYCI_BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null)}"
if [[ ! "$SOURCE" =~ ^release/[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  myci_warn "branch '${SOURCE}' is not release/X.Y.Z — skipping back-merge"
  exit 0
fi

VERSION="$(myci_release_version "$SOURCE")"
if ! myci_tag_exists "$VERSION"; then
  myci_warn "no release tag '${VERSION}' — nothing shipped from '${SOURCE}', skipping back-merge"
  exit 0
fi

TARGET="${BACKMERGE_TARGET_BRANCH:-$MYCI_DEFAULT_BRANCH}"
myci_log "back-merge: '${SOURCE}' -> '${TARGET}' (release ${VERSION} is tagged)"

myci_open_backmerge "$SOURCE" "$TARGET"
exit 0
