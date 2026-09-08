# ============================================================
# my-ci shared library
# ============================================================
# Source from every my-ci script:
#   . "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
#
# Normalizes GitLab CI and GitHub Actions into one set of MYCI_* variables
# and provides forge-agnostic helpers for every forge operation the pipeline
# needs: tag creation, merged-request lookup, release creation, back-merge,
# artifact publish, notification.
#
# This file deliberately does NOT `set -euo pipefail` — it is a library; each
# entry-point script owns its own error mode (backmerge.sh, for example, is
# best-effort by design and must not inherit -e).
#
# Normalized environment (set on source; a pre-set value always wins, so
# workflows can override — e.g. GitHub's pull_request events report a
# synthetic "<n>/merge" ref, so release.yml passes MYCI_BRANCH explicitly):
#   MYCI_FORGE           gitlab | github | local
#   MYCI_BRANCH          branch name ("" on tag builds)
#   MYCI_TAG             tag name ("" on branch builds)
#   MYCI_PROJECT         repo name without owner
#   MYCI_PROJECT_URL     web URL of the repo ("" if underivable)
#   MYCI_DEFAULT_BRANCH  default branch (probed from origin if not provided)
#   MYCI_COMMIT_PATH     commit-link path segment ("-/commit" on GitLab)
#
# Auth:
#   GitLab: CI_JOB_TOKEN for reads and API fallbacks; MYCI_PUSH_TOKEN (a
#           project access token with `api` + `write_repository` scope and
#           push rights on protected release/* + tags) for tag push and
#           back-merge MRs.
#   GitHub: GITHUB_TOKEN — the checkout's persisted credentials push the tag,
#           and `gh` (GH_TOKEN) does the rest. The workflow must grant
#           `permissions: contents: write, pull-requests: write`.
# ============================================================

myci_log()  { printf '==> %s\n' "$*"; }
myci_warn() { printf 'WARNING: %s\n' "$*" >&2; }
myci_die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Patterns shared by scripts and documented in references/pipeline-model.md:
# production tags are plain semver (no leading 'v'); dev-release tags carry a
# suffix; release branches embed the version they ship.
MYCI_SEMVER_RE='^[0-9]+\.[0-9]+\.[0-9]+$'
MYCI_DEV_TAG_RE='^v?[0-9]+\.[0-9]+\.[0-9]+-[0-9A-Za-z.-]+$'
MYCI_RELEASE_BRANCH_RE='^release/[0-9]+\.[0-9]+\.[0-9]+$'

git config --global --add safe.directory "$PWD" 2>/dev/null || true

# --- Forge detection -----------------------------------------------------
if [ -n "${GITLAB_CI:-}" ]; then
  MYCI_FORGE="gitlab"
elif [ -n "${GITHUB_ACTIONS:-}" ]; then
  MYCI_FORGE="github"
else
  MYCI_FORGE="local"
fi

# --- Environment normalization (pre-set values win) ----------------------
case "$MYCI_FORGE" in
  gitlab)
    MYCI_BRANCH="${MYCI_BRANCH:-${CI_COMMIT_BRANCH:-}}"
    MYCI_TAG="${MYCI_TAG:-${CI_COMMIT_TAG:-}}"
    MYCI_PROJECT="${MYCI_PROJECT:-${CI_PROJECT_NAME:-$(basename "$PWD")}}"
    MYCI_PROJECT_URL="${MYCI_PROJECT_URL:-${CI_PROJECT_URL:-}}"
    MYCI_DEFAULT_BRANCH="${MYCI_DEFAULT_BRANCH:-${CI_DEFAULT_BRANCH:-}}"
    MYCI_COMMIT_PATH="-/commit"
    ;;
  github)
    if [ "${GITHUB_REF_TYPE:-}" = "tag" ]; then
      MYCI_BRANCH="${MYCI_BRANCH:-}"
      MYCI_TAG="${MYCI_TAG:-${GITHUB_REF_NAME:-}}"
    else
      MYCI_BRANCH="${MYCI_BRANCH:-${GITHUB_REF_NAME:-}}"
      MYCI_TAG="${MYCI_TAG:-}"
    fi
    MYCI_PROJECT="${MYCI_PROJECT:-${GITHUB_REPOSITORY##*/}}"
    MYCI_PROJECT_URL="${MYCI_PROJECT_URL:-${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}}"
    MYCI_DEFAULT_BRANCH="${MYCI_DEFAULT_BRANCH:-}"
    MYCI_COMMIT_PATH="commit"
    ;;
  local)
    MYCI_BRANCH="${MYCI_BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)}"
    MYCI_TAG="${MYCI_TAG:-}"
    MYCI_PROJECT="${MYCI_PROJECT:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")")}"
    MYCI_DEFAULT_BRANCH="${MYCI_DEFAULT_BRANCH:-}"
    # GitLab redirects /commit/ to /-/commit/, so the plain path is safe when
    # the forge is unknown.
    MYCI_COMMIT_PATH="commit"
    ;;
esac

# Derive the project web URL from origin when the forge didn't provide one
# (local runs; changelog links degrade to short hashes if this stays empty).
if [ -z "${MYCI_PROJECT_URL:-}" ]; then
  _myci_origin="$(git remote get-url origin 2>/dev/null || true)"
  _myci_origin="${_myci_origin%.git}"
  case "$_myci_origin" in
    git@*)       MYCI_PROJECT_URL="https://$(printf '%s' "${_myci_origin#git@}" | sed 's|:|/|')" ;;
    ssh://git@*) MYCI_PROJECT_URL="https://$(printf '%s' "${_myci_origin#ssh://git@}" | sed -E 's|:[0-9]+/|/|')" ;;
    http*)       MYCI_PROJECT_URL="$_myci_origin" ;;
    *)           MYCI_PROJECT_URL="" ;;
  esac
fi

# Default branch: origin/HEAD, then main, then master.
if [ -z "${MYCI_DEFAULT_BRANCH:-}" ]; then
  MYCI_DEFAULT_BRANCH="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||' || true)"
fi
if [ -z "${MYCI_DEFAULT_BRANCH:-}" ]; then
  if git show-ref --verify --quiet refs/remotes/origin/main; then
    MYCI_DEFAULT_BRANCH="main"
  else
    MYCI_DEFAULT_BRANCH="master"
  fi
fi

export MYCI_FORGE MYCI_BRANCH MYCI_TAG MYCI_PROJECT MYCI_PROJECT_URL \
       MYCI_DEFAULT_BRANCH MYCI_COMMIT_PATH

# --- Small helpers -------------------------------------------------------

# release/X.Y.Z -> X.Y.Z
myci_release_version() { printf '%s' "${1#release/}"; }

# Usage: myci_tag_exists VERSION
# True when the production tag for VERSION is present locally or on origin.
# Accepts the bare semver this pipeline creates and a `v` prefix, so a repo
# that tags `v1.2.3` by hand is still recognized. A remote lookup failure is
# not a missing tag — the caller must not act on a flaked network — so a
# failed `ls-remote` re-reports whatever the local check found.
myci_tag_exists() {
  local v="$1" t
  for t in "$v" "v$v"; do
    git rev-parse -q --verify "refs/tags/${t}" >/dev/null 2>&1 && return 0
  done
  for t in "$v" "v$v"; do
    [ -n "$(git ls-remote --tags origin "refs/tags/${t}" 2>/dev/null)" ] && return 0
  done
  return 1
}

_myci_git_identity() {
  git config user.email >/dev/null 2>&1 || git config user.email "${MYCI_GIT_EMAIL:-ci@my-ci.invalid}"
  git config user.name  >/dev/null 2>&1 || git config user.name  "${MYCI_GIT_NAME:-my-ci}"
}

# --- GitLab API wrapper --------------------------------------------------
# Usage: _myci_gl_api METHOD PATH [extra curl args...]
# Call as a plain statement, NEVER inside $(...): the response routes through
# side-effect variables ($MYCI_API_HTTP / $MYCI_API_BODY), and a command
# substitution would run the helper in a subshell and silently discard them.
_myci_gl_api() {
  local method="$1" path="$2"
  shift 2
  local token_header
  if [ -n "${MYCI_PUSH_TOKEN:-}" ]; then
    token_header="PRIVATE-TOKEN: ${MYCI_PUSH_TOKEN}"
  else
    token_header="JOB-TOKEN: ${CI_JOB_TOKEN:-}"
  fi
  if [ -z "${_MYCI_API_BODY_FILE:-}" ]; then
    _MYCI_API_BODY_FILE="$(mktemp)"
  fi
  MYCI_API_HTTP=$(curl --silent --show-error --request "$method" \
    --header "$token_header" \
    --output "$_MYCI_API_BODY_FILE" \
    --write-out '%{http_code}' \
    "$@" \
    "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}${path}" 2>/dev/null) || MYCI_API_HTTP="000"
  MYCI_API_BODY="$(cat "$_MYCI_API_BODY_FILE" 2>/dev/null || true)"
}

# --- Tag creation (idempotent) -------------------------------------------
# Usage: myci_create_tag TAG REF MESSAGE
# Safe to re-run: an existing local or remote tag is a success, not an error,
# so a retried CI job never fails on its own earlier progress.
myci_create_tag() {
  local tag="$1" ref="$2" msg="$3"
  if git rev-parse -q --verify "refs/tags/$tag" >/dev/null 2>&1 \
     || git ls-remote --tags origin "refs/tags/$tag" 2>/dev/null | grep -q .; then
    myci_log "tag '$tag' already exists — skipping creation (idempotent)"
    return 0
  fi
  case "$MYCI_FORGE" in
    gitlab)
      if [ -n "${MYCI_PUSH_TOKEN:-}" ]; then
        _myci_git_identity
        git tag -a "$tag" -m "$msg" "$ref"
        git remote set-url origin \
          "https://oauth2:${MYCI_PUSH_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git"
        if git push origin "refs/tags/$tag"; then
          myci_log "tag '$tag' pushed"
          return 0
        fi
        myci_warn "git push failed — falling back to API tag creation"
        git tag -d "$tag" 2>/dev/null || true
      fi
      _myci_gl_api POST "/repository/tags" \
        --data-urlencode "tag_name=${tag}" \
        --data-urlencode "ref=${ref}" \
        --data-urlencode "message=${msg}"
      if [ "$MYCI_API_HTTP" != "201" ]; then
        myci_die "tag creation failed (HTTP ${MYCI_API_HTTP}): ${MYCI_API_BODY}"
      fi
      myci_log "tag '$tag' created via API"
      ;;
    github)
      # actions/checkout persists GITHUB_TOKEN credentials by default, and a
      # tag pushed with GITHUB_TOKEN does NOT trigger further workflows — which
      # is exactly the no-double-build guarantee the model wants.
      _myci_git_identity
      git tag -a "$tag" -m "$msg" "$ref"
      git push origin "refs/tags/$tag"
      myci_log "tag '$tag' pushed"
      ;;
    local)
      _myci_git_identity
      git tag -a "$tag" -m "$msg" "$ref"
      myci_log "tag '$tag' created locally (not pushed)"
      ;;
  esac
}

# --- Merged-request lookup -----------------------------------------------
# Usage: myci_merged_request_body TARGET_BRANCH
# Prints the description/body of the most recently merged MR/PR into
# TARGET_BRANCH (the promote request's description becomes the release
# changelog). Prints nothing when none is found.
myci_merged_request_body() {
  local target="$1"
  case "$MYCI_FORGE" in
    gitlab)
      local enc="${target//\//%2F}"
      _myci_gl_api GET "/merge_requests?state=merged&target_branch=${enc}&order_by=updated_at&sort=desc&per_page=1"
      [ "$MYCI_API_HTTP" = "200" ] || return 0
      printf '%s' "$MYCI_API_BODY" | jq -r '.[0].description // empty' 2>/dev/null || true
      ;;
    github)
      gh pr list --state merged --base "$target" --limit 1 \
        --json body --jq '.[0].body // empty' 2>/dev/null || true
      ;;
    local) : ;;
  esac
}

# --- Release creation (idempotent) ---------------------------------------
# Usage: myci_create_release TAG NAME NOTES_FILE PRERELEASE(true|false)
myci_create_release() {
  local tag="$1" name="$2" notes="$3" pre="${4:-false}"
  case "$MYCI_FORGE" in
    gitlab)
      local payload
      payload=$(jq -n --arg name "$name" --arg tag "$tag" \
        --rawfile d "$notes" '{name: $name, tag_name: $tag, description: $d}')
      _myci_gl_api POST "/releases" \
        --header "Content-Type: application/json" --data "$payload"
      case "$MYCI_API_HTTP" in
        201) myci_log "GitLab release created: ${name}" ;;
        409) myci_log "release for tag '$tag' already exists — skipping (idempotent)" ;;
        *)   myci_die "GitLab release creation failed (HTTP ${MYCI_API_HTTP}): ${MYCI_API_BODY}" ;;
      esac
      ;;
    github)
      if gh release view "$tag" >/dev/null 2>&1; then
        myci_log "release '$tag' already exists — skipping (idempotent)"
        return 0
      fi
      local flags=(--title "$name" --notes-file "$notes")
      [ "$pre" = "true" ] && flags+=(--prerelease)
      gh release create "$tag" "${flags[@]}"
      myci_log "GitHub release created: ${name}"
      ;;
    local)
      myci_log "local run — skipping forge release creation for '$tag'"
      ;;
  esac
}

# --- Back-merge (best-effort, never fails the caller) --------------------
# Usage: _myci_gh_land_backmerge PR_URL
# Gets a back-merge PR merged on GitHub without a human. Always returns 0 —
# the release has already shipped by the time this runs, so nothing here is
# worth failing over.
#
# Native auto-merge is tried first, but it cannot be relied on: it needs
# `allow_auto_merge` on the repo AND a branch protection rule or ruleset for
# the queue to wait on, and on a private repo without a paid plan none of that
# is available — a PATCH setting allow_auto_merge is accepted while the field
# stays false, and protection and rulesets return 403. Where the queue cannot
# be armed, poll the PR's own checks and merge once they are green.
#
# If no checks are ever reported — a PR opened with GITHUB_TOKEN triggers no
# workflows — that is not an error: the branch is the commit the release
# pipeline just built and tested. After MYCI_BACKMERGE_GRACE seconds of
# silence, merge on that basis and say so in the log.
#
# Every forge read can flake, so an unreadable value re-polls instead of being
# read as a zero.
#
#   MYCI_BACKMERGE_TIMEOUT  seconds to wait for checks to conclude (default 1800)
#   MYCI_BACKMERGE_GRACE    seconds to wait for any check to appear (default 180)
#   MYCI_BACKMERGE_POLL     seconds between polls (default 20)
_myci_gh_land_backmerge() {
  local pr_url="$1"
  local timeout="${MYCI_BACKMERGE_TIMEOUT:-1800}"
  local grace="${MYCI_BACKMERGE_GRACE:-180}"
  local poll="${MYCI_BACKMERGE_POLL:-20}"
  local waited=0 state
  # Elapsed time is counted in units of `poll`, so a zero would spin forever.
  _myci_is_uint "$poll" && [ "$poll" -gt 0 ] || poll=20

  # `gh` merges outright when the PR is already mergeable and nothing is
  # required, so re-read the PR below rather than trust silence here.
  gh pr merge "$pr_url" --auto --merge >/dev/null 2>&1

  while :; do
    state=$(gh pr view "$pr_url" --json state --jq '.state' 2>/dev/null)
    case "$state" in
      MERGED) myci_log "back-merge merged: ${pr_url}"; return 0 ;;
      CLOSED) myci_warn "back-merge PR was closed without merging: ${pr_url}"; return 0 ;;
      OPEN)   _myci_gh_backmerge_step "$pr_url" "$waited" "$grace" && return 0 ;;
      *)      ;;  # unreadable — fall through and re-poll
    esac

    if [ "$waited" -ge "$timeout" ]; then
      myci_warn "back-merge PR ${pr_url} did not become mergeable within ${timeout}s; leaving it open for a human (a bot-opened PR's runs can sit in action_required until someone approves them)"
      return 0
    fi
    sleep "$poll"
    waited=$((waited + poll))
  done
}

# Usage: _myci_gh_backmerge_step PR_URL WAITED GRACE
# One poll of an open back-merge PR. Returns 0 when the caller is done (auto-
# merge armed, merge attempted, or a check failed), 1 to keep polling.
_myci_gh_backmerge_step() {
  local pr_url="$1" waited="$2" grace="$3" auto total pending failing

  auto=$(gh pr view "$pr_url" --json autoMergeRequest --jq '.autoMergeRequest != null' 2>/dev/null)
  if [ "$auto" = "true" ]; then
    myci_log "auto-merge is armed on ${pr_url}; GitHub merges it when its checks pass"
    return 0
  fi

  total=$(gh pr checks "$pr_url" --json state --jq 'length' 2>/dev/null)
  _myci_is_uint "$total" || return 1   # unreadable, not "no checks" — re-poll

  if [ "$total" -eq 0 ]; then
    [ "$waited" -ge "$grace" ] || return 1
    myci_log "no checks reported on ${pr_url} after ${grace}s (a GITHUB_TOKEN-opened PR triggers none) — merging the commit the release pipeline already built and tested"
    _myci_gh_merge_pr "$pr_url"
    return 0
  fi

  failing=$(gh pr checks "$pr_url" --json state --jq \
    '[.[] | select(.state | IN("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "STARTUP_FAILURE"))] | length' 2>/dev/null)
  _myci_is_uint "$failing" || return 1
  if [ "$failing" -gt 0 ]; then
    myci_warn "${failing} of ${total} check(s) failed on ${pr_url}; leaving it open for a human"
    return 0
  fi

  # SKIPPED and NEUTRAL are conclusions, not waits: a job skipped by a rule
  # (or already satisfied by another run on the same commit) is not pending.
  pending=$(gh pr checks "$pr_url" --json state --jq \
    '[.[] | select(.state | IN("SUCCESS", "SKIPPED", "NEUTRAL") | not)] | length' 2>/dev/null)
  _myci_is_uint "$pending" || return 1
  [ "$pending" -eq 0 ] || return 1

  myci_log "all ${total} check(s) green on ${pr_url} — merging"
  _myci_gh_merge_pr "$pr_url"
  return 0
}

_myci_gh_merge_pr() {
  if gh pr merge "$1" --merge >/dev/null 2>&1; then
    myci_log "back-merge merged: $1"
  else
    myci_warn "could not merge $1 (conflicts, or the token lacks merge rights on the default branch); resolve manually"
  fi
}

_myci_is_uint() { case "${1:-}" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }

# Usage: myci_open_backmerge SOURCE_BRANCH TARGET_BRANCH
# Opens (or reuses) an auto-merge MR/PR from the shipped release branch back
# into the default branch. Every non-happy path warns and returns 0 — a green
# release pipeline must never go red because of the back-merge.
myci_open_backmerge() {
  local source="$1" target="$2" version title
  version="$(myci_release_version "$source")"
  title="Back-merge release ${version} -> ${target}"
  case "$MYCI_FORGE" in
    gitlab)
      if [ -z "${MYCI_PUSH_TOKEN:-}" ]; then
        myci_warn "MYCI_PUSH_TOKEN not set — cannot open the back-merge MR (needs api scope + merge rights on '${target}')"
        return 0
      fi
      local enc="${source//\//%2F}" iid=""
      _myci_gl_api GET "/merge_requests?state=opened&source_branch=${enc}&target_branch=${target}&per_page=1"
      if [ "$MYCI_API_HTTP" = "200" ] && [ -n "$MYCI_API_BODY" ] && [ "$MYCI_API_BODY" != "[]" ]; then
        iid=$(printf '%s' "$MYCI_API_BODY" | jq -r '.[0].iid // empty' 2>/dev/null)
      fi
      if [ -n "$iid" ]; then
        myci_log "reusing existing back-merge MR !${iid}"
      else
        _myci_gl_api POST "/merge_requests" \
          --data-urlencode "source_branch=${source}" \
          --data-urlencode "target_branch=${target}" \
          --data-urlencode "title=${title}" \
          --data-urlencode "description=Automated back-merge of production release ${version} into ${target}. Opened by CI: ${CI_PIPELINE_URL:-CI}." \
          --data "remove_source_branch=false" \
          --data "squash=false"
        if [ "$MYCI_API_HTTP" = "201" ]; then
          iid=$(printf '%s' "$MYCI_API_BODY" | jq -r '.iid // empty' 2>/dev/null)
          myci_log "created back-merge MR !${iid}"
        elif printf '%s' "$MYCI_API_BODY" | grep -qiE 'no.*difference|already.*up.?to.?date|nothing to merge'; then
          myci_log "'${source}' has no diff against '${target}' — already current; nothing to do"
          return 0
        elif printf '%s' "$MYCI_API_BODY" | grep -qiE 'already exists'; then
          # Race: an MR appeared between lookup and create — re-look it up.
          _myci_gl_api GET "/merge_requests?state=opened&source_branch=${enc}&target_branch=${target}&per_page=1"
          iid=$(printf '%s' "$MYCI_API_BODY" | jq -r '.[0].iid // empty' 2>/dev/null)
        fi
      fi
      if [ -z "$iid" ]; then
        myci_warn "could not create or find a back-merge MR (last HTTP ${MYCI_API_HTTP})"
        return 0
      fi
      # A fresh MR may still be computing mergeability — retry briefly.
      local i
      for i in 1 2 3 4 5 6; do
        _myci_gl_api PUT "/merge_requests/${iid}/merge?merge_when_pipeline_succeeds=true"
        case "$MYCI_API_HTTP" in
          200) myci_log "auto-merge set on MR !${iid}"; return 0 ;;
          406) break ;;  # cannot be merged — conflicts; stop retrying
          *)   sleep 5 ;;
        esac
      done
      myci_warn "back-merge MR !${iid} is open but auto-merge could NOT be set (last HTTP ${MYCI_API_HTTP} — likely conflicts or branch protection on '${target}'); resolve manually"
      return 0
      ;;
    github)
      local pr_url
      pr_url=$(gh pr list --state open --head "$source" --base "$target" \
        --json url --jq '.[0].url // empty' 2>/dev/null || true)
      if [ -n "$pr_url" ]; then
        myci_log "reusing existing back-merge PR: ${pr_url}"
      else
        pr_url=$(gh pr create --head "$source" --base "$target" --title "$title" \
          --body "Automated back-merge of production release ${version} into ${target}." \
          2>/dev/null || true)
      fi
      if [ -z "$pr_url" ]; then
        myci_warn "could not open back-merge PR '${source}' -> '${target}' (no diff, or missing permissions)"
        return 0
      fi
      myci_log "back-merge PR: ${pr_url}"
      _myci_gh_land_backmerge "$pr_url"
      return 0
      ;;
    local)
      myci_log "local run — skipping back-merge"
      return 0
      ;;
  esac
}

# --- Notification (optional, never fails the caller) ---------------------
# Usage: echo "body" | myci_notify LEVEL TITLE
# No-op unless MYCI_NOTIFY_WEBHOOK is set. MYCI_NOTIFY_STYLE selects the
# payload shape: generic (default) | feishu | slack.
myci_notify() {
  local level="$1" title="$2" body payload
  body="$(cat 2>/dev/null || true)"
  if [ -z "${MYCI_NOTIFY_WEBHOOK:-}" ]; then
    myci_log "notify [${level}] ${title} — MYCI_NOTIFY_WEBHOOK not set, skipping"
    return 0
  fi
  case "${MYCI_NOTIFY_STYLE:-generic}" in
    feishu)
      payload=$(jq -n --arg t "[${level}] ${title}" --arg b "$body" \
        '{msg_type: "text", content: {text: ($t + "\n\n" + $b)}}')
      ;;
    slack)
      payload=$(jq -n --arg t "[${level}] ${title}" --arg b "$body" \
        '{text: ($t + "\n\n" + $b)}')
      ;;
    *)
      payload=$(jq -n --arg l "$level" --arg t "$title" --arg b "$body" \
        '{level: $l, title: $t, body: $b}')
      ;;
  esac
  curl --silent --show-error --request POST \
    --header 'Content-Type: application/json' \
    --data "$payload" "$MYCI_NOTIFY_WEBHOOK" >/dev/null 2>&1 \
    || myci_warn "notification delivery failed (non-fatal)"
  return 0
}
