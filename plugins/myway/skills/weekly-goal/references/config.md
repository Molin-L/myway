# Configuration and the fetch script

## GitLab host and auth

Both the script and the write commands go through `glab`, so authentication is whatever `glab auth status` shows. Nothing here reads a token directly.

```sh
glab auth status          # must show "Logged in to <host>"
```

The host comes from `--host`, else `$GITLAB_HOST`, else `glab config get host`. If `glab` is not authenticated, stop and say so.

> The script deliberately does not use Python's `urllib`. Some self-hosted instances sit behind a front end that resets OpenSSL-style TLS handshakes while accepting Go's; `glab` works everywhere `glab auth status` passes.

## Goal group

Weekly goals are group milestones, so one group must be chosen. First match wins:

| Source | Example |
|---|---|
| `--group` on the script | `scripts/gitlab_activity.py --group infra milestones` |
| `$WEEKLY_GOAL_GROUP` | `export WEEKLY_GOAL_GROUP=infra` |
| `~/.config/myway/weekly-goal.toml` | below |

```toml
[gitlab]
group = "infra"          # full path, e.g. "infra" or "infra/agentic"
```

If none is set, the script exits 1 with `no goal group` and a message that shows this file format. The skill must then **ask the user** which group to use — list `scripts/gitlab_activity.py groups`, wait for the answer, pass `--group` for the rest of the session, and tell the user to persist it with the file above. Never guess. Pick the **highest** group that contains every project the goals touch; issues in projects outside the group cannot take the milestone.

## Script

`scripts/gitlab_activity.py` — Python 3.10+, standard library only, read-only, JSON on stdout, errors on stderr with exit 1. Under Claude Code the path is `${CLAUDE_PLUGIN_ROOT}/skills/weekly-goal/scripts/gitlab_activity.py`.

| Subcommand | Returns |
|---|---|
| `me` | `{id, username, name, web_url}` of the authenticated user |
| `groups` | groups the user has developer access to: `{id, path, parent_id, web_url}` — for choosing the goal group |
| `projects` | non-archived projects of the goal group, subgroups included: `{id, path, web_url, last_activity_at}` |
| `milestones [--state active\|closed\|all]` | group milestones: `{id, iid, title, state, start_date, due_date, description, web_url, …}` |
| `issues --milestone M [window]` | `{window, milestone, issues[]}` |
| `events [--user U] [window]` | `{window, user, events[]}` — defaults to me |
| `evidence --milestone M [window]` | `{window, me, milestone, issues[], my_events[]}` — what the gap arc consumes |

`M` is a milestone `id`, `iid`, or exact title (case-insensitive). Window flags: `--days N` (default 7), `--since YYYY-MM-DD`, `--until YYYY-MM-DD`. Add `--compact` for single-line JSON.

### Issue shape

```json
{
  "project": "infra/agentic/nightshift", "project_id": 12, "iid": 10,
  "reference": "infra/agentic/nightshift#10",
  "title": "chore: bump cord to 0.11.0", "state": "opened",
  "author": "molinliu", "assignees": [], "labels": [],
  "created_at": "…", "updated_at": "…", "closed_at": null, "web_url": "…",
  "description": "first 600 chars",
  "active_in_window": true,
  "notes_in_window": [{"created_at": "…", "author": "molinliu", "system": true, "body": "mentioned in merge request !29"}],
  "links": [{"project": "infra/moonlink", "iid": 40, "title": "…", "state": "opened", "link_type": "is_blocked_by", "web_url": "…"}],
  "merge_requests": [{"iid": 29, "title": "…", "state": "merged", "author": "molinliu", "merged_at": "…", "updated_at": "…", "web_url": "…"}]
}
```

`links` are read from the issue's own point of view: `link_type: "is_blocked_by"` means *this* issue is blocked by the target. `notes_in_window` includes system notes — they record state changes, MR mentions, and commit mentions, which is most of the evidence.

### Event shape

```json
{"created_at": "…", "action": "pushed to", "project": "infra/agentic/nightshift",
 "target_type": "Project", "target_iid": 12, "target_title": "Nightshift",
 "push": {"ref": "pre-release/1.2.0", "ref_type": "branch", "commit_count": 1, "commit_title": "chore(release): bump to 1.2.0"}}
```

`action` values seen: `pushed to`, `pushed new`, `opened`, `closed`, `accepted` (MR merged), `commented on`, `created`. For push events `target_iid` is the project id, not an issue.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | configuration missing, `glab` missing or unauthenticated, API error, unknown milestone/user |
| 2 | bad arguments (argparse) |
