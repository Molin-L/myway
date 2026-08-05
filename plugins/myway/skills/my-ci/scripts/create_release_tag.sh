#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/lib.sh"

# ============================================================
# Create the production tag from a release branch
# ============================================================
# Runs on the ship pipeline of release/X.Y.Z (the promote-merge push). The
# branch name is the version source of truth (myway ADR 0001):
#   release/X.Y.Z  →  tag X.Y.Z  (plain semver, NO leading 'v')
#
# Idempotent: an existing tag is a success (safe on CI retry).
#
# Outputs:
#   RELEASE_CHANGELOG.md   promote MR/PR description (fallback: generated)
#   CHANGELOG.md           copy, for artifact consistency
#   dist/VERSION           plain version file
#   release.env            RELEASE_VERSION / RELEASE_TAG (GitLab dotenv;
#                          GitHub jobs `source` it between steps)
#   $GITHUB_OUTPUT         version= / tag= appended when set
# ============================================================

BRANCH="${MYCI_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
if [[ ! "$BRANCH" =~ ^release/([0-9]+\.[0-9]+\.[0-9]+)$ ]]; then
  myci_die "branch '${BRANCH}' does not match release/X.Y.Z"
fi
VERSION="${BASH_REMATCH[1]}"
TAG="$VERSION"

myci_log "release branch: ${BRANCH}"
myci_log "version: ${VERSION}  tag: ${TAG}"

myci_create_tag "$TAG" "$BRANCH" "Release ${VERSION}"

# --- Changelog: promote MR/PR description, else generated -----------------
BODY="$(myci_merged_request_body "$BRANCH" || true)"
if [ -n "$BODY" ]; then
  printf '%s\n' "$BODY" > RELEASE_CHANGELOG.md
  myci_log "RELEASE_CHANGELOG.md taken from the promote request description"
else
  myci_log "no merged request description found — generating changelog from commits"
  "${SCRIPT_DIR}/gen_changelog.sh" -v "$VERSION"
  cp CHANGELOG.md RELEASE_CHANGELOG.md
fi
cp RELEASE_CHANGELOG.md CHANGELOG.md

# --- Version artifacts for downstream jobs --------------------------------
mkdir -p dist
printf '%s\n' "$VERSION" > dist/VERSION

cat > release.env <<EOF
RELEASE_VERSION=${VERSION}
RELEASE_TAG=${TAG}
EOF
myci_log "release.env written:"
cat release.env

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  {
    echo "version=${VERSION}"
    echo "tag=${TAG}"
  } >> "$GITHUB_OUTPUT"
fi

myci_log "create_release_tag complete"
