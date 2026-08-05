#!/usr/bin/env bash
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# ============================================================
# Generate CHANGELOG.md
# ============================================================
# Commits since the previous production tag (plain semver), grouped by
# conventional-commit type, each linked to the forge commit page.
#
# Usage: gen_changelog.sh [-p <previous-ref>] [-v <version>]
#   -p  compare against this ref instead of the latest production tag
#   -v  version heading (default: release branch version → current tag →
#       latest semver tag → "unreleased")
# ============================================================

PREV=""
VERSION=""
while getopts "p:v:" opt; do
  case $opt in
    p) PREV="$OPTARG" ;;
    v) VERSION="$OPTARG" ;;
    *) echo "Usage: $0 [-p previous_ref] [-v version]" >&2; exit 1 ;;
  esac
done

if [ -z "$VERSION" ]; then
  if [[ "${MYCI_BRANCH:-}" =~ ^release/([0-9]+\.[0-9]+\.[0-9]+)$ ]]; then
    VERSION="${BASH_REMATCH[1]}"
  elif [ -n "${MYCI_TAG:-}" ]; then
    VERSION="${MYCI_TAG#v}"
  else
    VERSION="$(git tag --sort=-v:refname | grep -E "$MYCI_SEMVER_RE" | head -1 || true)"
    VERSION="${VERSION:-unreleased}"
  fi
fi

# Range start: previous production tag (excluding the version being cut, in
# case the tag already exists from an earlier idempotent run).
if [ -z "$PREV" ]; then
  PREV="$(git tag --sort=-creatordate | grep -E "$MYCI_SEMVER_RE" | grep -vx "$VERSION" | head -1 || true)"
fi
if [ -n "$PREV" ]; then
  RANGE="${PREV}..HEAD"
  myci_log "changelog range: ${RANGE}"
else
  RANGE="HEAD"
  myci_log "no previous production tag — changelog covers full history"
fi

commits="$(git log "$RANGE" --no-merges --pretty=format:'%s|%H' --reverse | grep -v 'CHANGELOG.md' || true)"

TMP="$(mktemp)"
{
  printf '## %s (%s)\n\n' "$VERSION" "$(date +%Y-%m-%d)"
  if [ -n "$commits" ]; then
    for type in feat fix perf refactor docs test build ci chore style other; do
      section=""
      while IFS= read -r line; do
        msg="${line%%|*}"
        hash="${line##*|}"
        if [ -z "$msg" ]; then continue; fi
        t="$(printf '%s' "$msg" | sed -nE 's/^([a-z]+)(\([^)]*\))?!?:.*/\1/p')"
        case " feat fix perf refactor docs test build ci chore style " in
          *" ${t} "*) : ;;
          *) t="other" ;;
        esac
        if [ "$t" = "$type" ]; then
          if [ -n "$MYCI_PROJECT_URL" ]; then
            section="${section}* ${msg} ([view](${MYCI_PROJECT_URL}/${MYCI_COMMIT_PATH}/${hash}))"$'\n'
          else
            section="${section}* ${msg} (${hash:0:8})"$'\n'
          fi
        fi
      done <<< "$commits"
      if [ -n "$section" ]; then
        printf '### %s\n\n%s\n' "$type" "$section"
      fi
    done
  fi
} > "$TMP"

mv "$TMP" CHANGELOG.md
myci_log "CHANGELOG.md written (version ${VERSION})"
