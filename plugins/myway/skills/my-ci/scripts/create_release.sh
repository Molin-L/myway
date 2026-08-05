#!/usr/bin/env bash
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# ============================================================
# Create the forge release (GitLab Release / GitHub Release)
# ============================================================
# Version chain (first match wins):
#   1. RELEASE_VERSION      from create_release_tag.sh (production path)
#   2. current tag          dev-release tag pipelines
#   3. latest semver tag    fallback
#
# Notes file: RELEASE_CHANGELOG.md → CHANGELOG.md. A STABLE release without
# a changelog is a hard error — a shipped version must document its changes.
# Pre-releases fall back to a stub.
# ============================================================

VERSION="${RELEASE_VERSION:-${MYCI_TAG:-}}"
if [ -z "$VERSION" ]; then
  VERSION="$(git tag --sort=-creatordate | grep -E '^v?[0-9]+\.' | head -1 || true)"
fi
[ -n "$VERSION" ] || myci_die "no version detected (RELEASE_VERSION, tag, or semver git tag)"
TAG="${RELEASE_TAG:-$VERSION}"

PRERELEASE="false"
if [[ "$VERSION" =~ -[A-Za-z] ]]; then
  PRERELEASE="true"
fi

NOTES=""
if [ -f RELEASE_CHANGELOG.md ]; then
  NOTES="RELEASE_CHANGELOG.md"
elif [ -f CHANGELOG.md ]; then
  NOTES="CHANGELOG.md"
fi
if [ -z "$NOTES" ]; then
  if [ "$PRERELEASE" = "true" ]; then
    printf 'Pre-release %s\n' "$VERSION" > .myci_notes.md
    NOTES=".myci_notes.md"
    myci_log "no changelog found — using stub notes for pre-release"
  else
    myci_die "stable release ${VERSION} requires a changelog (RELEASE_CHANGELOG.md or CHANGELOG.md)"
  fi
fi

NAME="${MYCI_PROJECT} ${VERSION}"
if [ "$PRERELEASE" = "true" ]; then
  NAME="${MYCI_PROJECT} Pre-Release ${VERSION}"
fi

myci_log "creating release: ${NAME} (tag ${TAG}, prerelease=${PRERELEASE})"
echo ""
echo "NOTES:"
cat "$NOTES"
echo ""

myci_create_release "$TAG" "$NAME" "$NOTES" "$PRERELEASE"

myci_log "create_release complete"
