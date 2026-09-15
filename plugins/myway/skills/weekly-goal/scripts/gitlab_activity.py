#!/usr/bin/env python3
"""Fetch GitLab evidence for weekly goals. Read-only. Prints JSON to stdout.

Subcommands:
  me                           the authenticated user
  groups                       groups the user can see (to pick the goal group)
  projects                     projects in the goal group (for issue placement)
  milestones [--state S]       group milestones (active by default)
  issues --milestone M         issues linked to a milestone, with notes, links
                               and related merge requests inside the window
  events [--user U]            activity events of a user inside the window
  evidence --milestone M       milestone + issues + my events, in that order

Window flags (all subcommands that need one):
  --days N        trailing N days ending today (default 7)
  --since DATE    YYYY-MM-DD, overrides --days
  --until DATE    YYYY-MM-DD, default today

Transport: every request goes through `glab api`, so authentication is
whatever `glab auth status` reports. No token is handled here.

Configuration (first match wins):
  host    --host, $GITLAB_HOST, `glab config get host`
  group   --group, $WEEKLY_GOAL_GROUP, ~/.config/myway/weekly-goal.toml
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.parse

CONFIG_PATH = os.path.expanduser("~/.config/myway/weekly-goal.toml")
NOTE_MAX = 600
PER_PAGE = 100


# ----------------------------------------------------------------------------
# configuration


def die(msg: str, code: int = 1) -> None:
    print(f"gitlab_activity: {msg}", file=sys.stderr)
    sys.exit(code)


def glab_config(key: str, host: str | None = None) -> str | None:
    cmd = ["glab", "config", "get", key]
    if host:
        cmd += ["--host", host]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = out.stdout.strip()
    return value or None


def load_config_file() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        return {}
    with open(CONFIG_PATH, "rb") as fh:
        try:
            return tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            die(f"cannot parse {CONFIG_PATH}: {exc}")
    return {}


def resolve_host(arg: str | None) -> str:
    host = arg or os.environ.get("GITLAB_HOST") or glab_config("host")
    if not host:
        die("no GitLab host: pass --host, set GITLAB_HOST, or run `glab auth login`")
    return host.replace("https://", "").replace("http://", "").strip("/")




def resolve_group(arg: str | None) -> str:
    group = arg or os.environ.get("WEEKLY_GOAL_GROUP")
    if not group:
        group = load_config_file().get("gitlab", {}).get("group")
    if not group:
        die(
            "no goal group: pass --group, set WEEKLY_GOAL_GROUP, or write\n"
            f"  [gitlab]\n  group = \"<group/path>\"\nto {CONFIG_PATH}"
        )
    return group


# ----------------------------------------------------------------------------
# HTTP


class Client:
    """Thin transport over `glab api`; `glab` owns the host auth and the TLS stack."""

    def __init__(self, host: str) -> None:
        self.host = host
        self._project_cache: dict[int, dict] = {}

    def _run(self, path: str, params: dict | None, paginate: bool) -> object:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        endpoint = path.lstrip("/") + (f"?{query}" if query else "")
        cmd = ["glab", "api", "--hostname", self.host, "--output", "json"]
        if paginate:
            cmd.append("--paginate")
        cmd.append(endpoint)
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except FileNotFoundError:
            die("`glab` not found on PATH; install it and run `glab auth login`")
        except subprocess.TimeoutExpired:
            die(f"`glab api {endpoint}` timed out")
        if out.returncode != 0:
            err = out.stderr.strip() or out.stdout.strip()
            m = re.search(r"HTTP (\d{3})", err)
            raise ApiError(int(m.group(1)) if m else 0, endpoint, err[:300])
        try:
            return json.loads(out.stdout or "null")
        except json.JSONDecodeError:
            die(f"`glab api {endpoint}` returned non-JSON output: {out.stdout[:200]!r}")
        return None

    def get(self, path: str, params: dict | None = None) -> object:
        return self._run(path, params, paginate=False)

    def get_all(self, path: str, params: dict | None = None) -> list:
        params = dict(params or {})
        params.setdefault("per_page", PER_PAGE)
        data = self._run(path, params, paginate=True)
        if data is None:
            return []
        if not isinstance(data, list):
            die(f"expected a list from {path}, got {type(data).__name__}")
        return data

    def project(self, project_id: int) -> dict:
        if project_id not in self._project_cache:
            try:
                p = self.get(f"projects/{project_id}")
            except ApiError:
                p = {"id": project_id, "path_with_namespace": f"<project {project_id}>"}
            self._project_cache[project_id] = p
        return self._project_cache[project_id]


class ApiError(Exception):
    def __init__(self, status: int, endpoint: str, body: str) -> None:
        super().__init__(f"{body} [{endpoint}]")
        self.status = status
        self.endpoint = endpoint


def enc(path: str) -> str:
    return urllib.parse.quote(path, safe="")


# ----------------------------------------------------------------------------
# window


def parse_date(s: str) -> dt.date:
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        die(f"bad date {s!r}, expected YYYY-MM-DD")
    return dt.date.today()


def resolve_window(args: argparse.Namespace) -> tuple[dt.date, dt.date]:
    until = parse_date(args.until) if args.until else dt.date.today()
    since = parse_date(args.since) if args.since else until - dt.timedelta(days=args.days)
    if since > until:
        die(f"--since {since} is after --until {until}")
    return since, until


def in_window(iso: str | None, since: dt.date, until: dt.date) -> bool:
    if not iso:
        return False
    day = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
    return since <= day <= until


def window_dict(since: dt.date, until: dt.date) -> dict:
    return {"since": since.isoformat(), "until": until.isoformat(), "days": (until - since).days}


# ----------------------------------------------------------------------------
# shaping


def shape_user(u: dict | None) -> str | None:
    return u.get("username") if u else None


def shape_milestone(m: dict) -> dict:
    return {
        "id": m.get("id"),
        "iid": m.get("iid"),
        "title": m.get("title"),
        "state": m.get("state"),
        "start_date": m.get("start_date"),
        "due_date": m.get("due_date"),
        "description": m.get("description") or "",
        "web_url": m.get("web_url"),
        "group_id": m.get("group_id"),
        "project_id": m.get("project_id"),
        "updated_at": m.get("updated_at"),
    }


def shape_note(n: dict) -> dict:
    body = (n.get("body") or "").strip()
    if len(body) > NOTE_MAX:
        body = body[:NOTE_MAX] + " …"
    return {
        "created_at": n.get("created_at"),
        "author": shape_user(n.get("author")),
        "system": bool(n.get("system")),
        "body": body,
    }


def shape_link(client: Client, l: dict) -> dict:
    return {
        "project": client.project(l["project_id"]).get("path_with_namespace"),
        "iid": l.get("iid"),
        "title": l.get("title"),
        "state": l.get("state"),
        "link_type": l.get("link_type", "relates_to"),
        "web_url": l.get("web_url"),
    }


def shape_mr(mr: dict) -> dict:
    return {
        "iid": mr.get("iid"),
        "title": mr.get("title"),
        "state": mr.get("state"),
        "author": shape_user(mr.get("author")),
        "merged_at": mr.get("merged_at"),
        "updated_at": mr.get("updated_at"),
        "web_url": mr.get("web_url"),
    }


def shape_issue(client: Client, i: dict, since: dt.date, until: dt.date) -> dict:
    pid, iid = i["project_id"], i["iid"]
    project = client.project(pid).get("path_with_namespace")

    notes = client.get_all(f"projects/{pid}/issues/{iid}/notes", {"sort": "asc", "order_by": "created_at"})
    notes = [shape_note(n) for n in notes if in_window(n.get("created_at"), since, until)]

    try:
        links = [shape_link(client, l) for l in client.get_all(f"projects/{pid}/issues/{iid}/links")]
    except ApiError as exc:
        links = []
        if exc.status not in (403, 404):
            raise

    try:
        mrs = [shape_mr(m) for m in client.get_all(f"projects/{pid}/issues/{iid}/related_merge_requests")]
    except ApiError as exc:
        mrs = []
        if exc.status not in (403, 404):
            raise

    active = (
        in_window(i.get("created_at"), since, until)
        or in_window(i.get("updated_at"), since, until)
        or in_window(i.get("closed_at"), since, until)
        or bool(notes)
        or any(in_window(m["updated_at"], since, until) for m in mrs)
    )
    return {
        "project": project,
        "project_id": pid,
        "iid": iid,
        "reference": f"{project}#{iid}",
        "title": i.get("title"),
        "state": i.get("state"),
        "author": shape_user(i.get("author")),
        "assignees": [shape_user(a) for a in i.get("assignees") or []],
        "labels": i.get("labels") or [],
        "created_at": i.get("created_at"),
        "updated_at": i.get("updated_at"),
        "closed_at": i.get("closed_at"),
        "web_url": i.get("web_url"),
        "description": (i.get("description") or "")[:NOTE_MAX],
        "active_in_window": active,
        "notes_in_window": notes,
        "links": links,
        "merge_requests": mrs,
    }


def shape_event(client: Client, e: dict) -> dict:
    project = client.project(e["project_id"]).get("path_with_namespace") if e.get("project_id") else None
    out = {
        "created_at": e.get("created_at"),
        "action": e.get("action_name"),
        "project": project,
        "target_type": e.get("target_type"),
        "target_iid": e.get("target_iid"),
        "target_title": e.get("target_title"),
    }
    push = e.get("push_data")
    if push:
        out["push"] = {
            "ref": push.get("ref"),
            "ref_type": push.get("ref_type"),
            "commit_count": push.get("commit_count"),
            "commit_title": push.get("commit_title"),
        }
    note = e.get("note")
    if note:
        out["note"] = {
            "noteable_type": note.get("noteable_type"),
            "noteable_iid": note.get("noteable_iid"),
            "body": (note.get("body") or "")[:NOTE_MAX],
        }
    return out


# ----------------------------------------------------------------------------
# lookups


def find_milestone(client: Client, group: str, key: str) -> dict:
    milestones = client.get_all(f"groups/{enc(group)}/milestones", {"state": "all"})
    if key.isdigit():
        for m in milestones:
            if m["id"] == int(key) or m["iid"] == int(key):
                return m
    for m in milestones:
        if m["title"].strip().lower() == key.strip().lower():
            return m
    die(f"no milestone {key!r} in group {group}")
    return {}


def find_user(client: Client, key: str | None) -> dict:
    if not key:
        return client.get("user")
    if key.isdigit():
        return client.get(f"users/{key}")
    users = client.get("users", {"username": key})
    if not users:
        die(f"no user {key!r}")
    return users[0]


def milestone_issues(client: Client, group: str, m: dict, since: dt.date, until: dt.date) -> list:
    raw = client.get_all(
        f"groups/{enc(group)}/issues",
        {"milestone": m["title"], "scope": "all", "state": "all", "order_by": "updated_at", "sort": "desc"},
    )
    return [shape_issue(client, i, since, until) for i in raw]


def user_events(client: Client, user: dict, since: dt.date, until: dt.date) -> list:
    # `after` and `before` are exclusive day bounds on the events API.
    raw = client.get_all(
        f"users/{user['id']}/events",
        {
            "after": (since - dt.timedelta(days=1)).isoformat(),
            "before": (until + dt.timedelta(days=1)).isoformat(),
            "sort": "asc",
        },
    )
    return [shape_event(client, e) for e in raw if in_window(e.get("created_at"), since, until)]


# ----------------------------------------------------------------------------
# commands


def cmd_me(client: Client, args: argparse.Namespace) -> object:
    u = client.get("user")
    return {"id": u["id"], "username": u["username"], "name": u.get("name"), "web_url": u.get("web_url")}


def cmd_groups(client: Client, args: argparse.Namespace) -> object:
    raw = client.get_all("groups", {"min_access_level": 30, "order_by": "path", "sort": "asc"})
    return [
        {
            "id": g["id"],
            "path": g["full_path"],
            "parent_id": g.get("parent_id"),
            "web_url": g.get("web_url"),
        }
        for g in raw
    ]


def cmd_projects(client: Client, args: argparse.Namespace) -> object:
    group = resolve_group(args.group)
    raw = client.get_all(
        f"groups/{enc(group)}/projects",
        {"include_subgroups": "true", "archived": "false", "simple": "true", "order_by": "last_activity_at"},
    )
    return [
        {
            "id": p["id"],
            "path": p["path_with_namespace"],
            "web_url": p.get("web_url"),
            "last_activity_at": p.get("last_activity_at"),
        }
        for p in raw
    ]


def cmd_milestones(client: Client, args: argparse.Namespace) -> object:
    group = resolve_group(args.group)
    state = None if args.state == "all" else args.state
    raw = client.get_all(f"groups/{enc(group)}/milestones", {"state": state})
    return [shape_milestone(m) for m in raw]


def cmd_issues(client: Client, args: argparse.Namespace) -> object:
    group = resolve_group(args.group)
    since, until = resolve_window(args)
    m = find_milestone(client, group, args.milestone)
    return {
        "window": window_dict(since, until),
        "milestone": shape_milestone(m),
        "issues": milestone_issues(client, group, m, since, until),
    }


def cmd_events(client: Client, args: argparse.Namespace) -> object:
    since, until = resolve_window(args)
    user = find_user(client, args.user)
    return {
        "window": window_dict(since, until),
        "user": {"id": user["id"], "username": user["username"]},
        "events": user_events(client, user, since, until),
    }


def cmd_evidence(client: Client, args: argparse.Namespace) -> object:
    group = resolve_group(args.group)
    since, until = resolve_window(args)
    m = find_milestone(client, group, args.milestone)
    me = client.get("user")
    return {
        "window": window_dict(since, until),
        "me": {"id": me["id"], "username": me["username"]},
        "milestone": shape_milestone(m),
        "issues": milestone_issues(client, group, m, since, until),
        "my_events": user_events(client, me, since, until),
    }


# ----------------------------------------------------------------------------


def add_window_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--days", type=int, default=7, help="trailing window length (default 7)")
    p.add_argument("--since", help="window start, YYYY-MM-DD (overrides --days)")
    p.add_argument("--until", help="window end, YYYY-MM-DD (default today)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="gitlab_activity.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", help="GitLab host (default: $GITLAB_HOST or glab config)")
    parser.add_argument("--group", help="goal group path (default: $WEEKLY_GOAL_GROUP or config file)")
    parser.add_argument("--compact", action="store_true", help="single-line JSON output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("me", help="the authenticated user").set_defaults(fn=cmd_me)
    sub.add_parser("groups", help="groups the user has developer access to").set_defaults(fn=cmd_groups)
    sub.add_parser("projects", help="projects in the goal group").set_defaults(fn=cmd_projects)

    p = sub.add_parser("milestones", help="group milestones")
    p.add_argument("--state", choices=["active", "closed", "all"], default="active")
    p.set_defaults(fn=cmd_milestones)

    p = sub.add_parser("issues", help="issues linked to a milestone")
    p.add_argument("--milestone", required=True, help="milestone id, iid, or exact title")
    add_window_flags(p)
    p.set_defaults(fn=cmd_issues)

    p = sub.add_parser("events", help="activity events of a user")
    p.add_argument("--user", help="username or id (default: me)")
    add_window_flags(p)
    p.set_defaults(fn=cmd_events)

    p = sub.add_parser("evidence", help="milestone + linked issues + my events")
    p.add_argument("--milestone", required=True, help="milestone id, iid, or exact title")
    add_window_flags(p)
    p.set_defaults(fn=cmd_evidence)

    args = parser.parse_args(argv)
    client = Client(resolve_host(args.host))
    try:
        result = args.fn(client, args)
    except ApiError as exc:
        die(str(exc))
        return
    if args.compact:
        json.dump(result, sys.stdout, separators=(",", ":"))
    else:
        json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
