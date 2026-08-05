#!/usr/bin/env bash
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# ============================================================
# Package — assemble the final release/ directory
# ============================================================
# Everything under release/ ships: publish.sh uploads it (GitHub release
# assets / GitLab generic package registry / your own store).
# ============================================================

myci_log "packaging release artifacts (${MYCI_PROJECT})"

mkdir -p release

# ============================================================
# CUSTOMIZE — copy this repo's shippable artifacts into release/.
# Examples:
#   Binaries:         cp build/bin/mytool release/
#   Python packages:  cp dist/*.whl dist/*.tar.gz release/
#   Archives:         tar -czf release/${MYCI_PROJECT}.tar.gz -C build/out .
#   Docker images:    docker save image:tag > release/image.tar
# ============================================================
if [ -d dist ]; then
  myci_log "copying artifacts from dist/"
  cp -r dist/* release/ 2>/dev/null || true
fi

# Standard release papers ride along when present.
for file in README.md LICENSE CHANGELOG.md RELEASE_CHANGELOG.md VERSION; do
  if [ -f "$file" ]; then
    cp "$file" release/
  fi
done

myci_log "release directory:"
ls -lh release/

if [ -z "$(ls -A release/ 2>/dev/null)" ]; then
  myci_die "release/ is empty — customize ci/scripts/package.sh to copy this repo's artifacts"
fi
