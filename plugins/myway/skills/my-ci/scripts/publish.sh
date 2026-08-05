#!/usr/bin/env bash
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# ============================================================
# Publish — upload release/ to an artifact store
# ============================================================
# Default behavior (forge-native, zero config):
#   GitHub: attach every file under release/ to the forge release for the tag
#   GitLab: upload every file to the project's generic package registry
#           (Packages & Registries → Package Registry, name = project,
#            version = release version)
#
# CUSTOMIZE — replace the forge-native default with your own store (Nexus,
# S3, a container registry, PyPI, ...) if artifacts must live elsewhere.
# Contract: exit non-zero when an upload fails; never report success without
# artifacts actually landing.
# ============================================================

# Version chain: create_release_tag.sh dotenv → tag pipeline → latest semver tag.
VERSION="${RELEASE_VERSION:-${MYCI_TAG:-}}"
if [ -z "$VERSION" ]; then
  VERSION="$(git tag --sort=-creatordate | grep -E "$MYCI_SEMVER_RE" | head -1 || true)"
fi
[ -n "$VERSION" ] || myci_die "no version detected (RELEASE_VERSION, tag, or semver git tag)"
TAG="${RELEASE_TAG:-$VERSION}"

if [ ! -d release ] || [ -z "$(ls -A release/ 2>/dev/null)" ]; then
  myci_log "release/ is empty — nothing to publish (normal for library-only or service repos)"
  exit 0
fi

myci_log "publishing release/ (${MYCI_PROJECT} ${VERSION}, forge: ${MYCI_FORGE})"

case "$MYCI_FORGE" in
  github)
    # The release was created by create_release.sh; attach the artifacts.
    gh release upload "$TAG" release/* --clobber
    myci_log "artifacts attached to GitHub release '${TAG}'"
    ;;
  gitlab)
    while IFS= read -r -d '' file; do
      name="$(basename "$file")"
      url="${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages/generic/${MYCI_PROJECT}/${VERSION}/${name}"
      myci_log "uploading ${file} -> ${url}"
      status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
        --header "JOB-TOKEN: ${CI_JOB_TOKEN}" \
        --upload-file "$file" "$url") || status="000"
      if [ "$status" != "200" ] && [ "$status" != "201" ]; then
        myci_die "upload of '${name}' failed (HTTP ${status})"
      fi
    done < <(find release -type f -print0)
    myci_log "artifacts uploaded to the GitLab generic package registry (${MYCI_PROJECT}/${VERSION})"
    ;;
  local)
    myci_log "local run — skipping publish"
    ;;
esac

myci_log "publish complete"
