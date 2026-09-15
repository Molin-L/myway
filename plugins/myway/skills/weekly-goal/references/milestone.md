# Milestone — the goal's shape on GitLab

## Title

Short and imperative, at most eight words, no week prefix: `Ship OrderRouter to pre-release`, not `W38: ship the router`. A goal may roll over into the next week; the dates carry the week, the title carries the goal.

## Dates

| Field | New goal | Same goal (update) |
|---|---|---|
| `start_date` | Monday of the current ISO week | unchanged |
| `due_date` | Sunday of the current ISO week | Sunday of the current ISO week |

```sh
monday=$(date -d "-$(( $(date +%u) - 1 )) days" +%F)   # %u: Monday=1 … Sunday=7
sunday=$(date -d "$monday + 6 days" +%F)
```

GNU `date`. Do not use `date -d "monday this week"` — it returns *next* Monday on most days.

## Body

The body is the spec of the goal. Four sections, in this order, with these exact headings — the gap mode parses `## Done when` by heading.

```md
## Achieve
One paragraph: what will exist or be true by the end of the week.

## Contributes to
One paragraph: the larger outcome this serves and who it serves.

## Done when
- [ ] Observable, checkable outcome.
- [ ] Another one.

## Log
- 2026-09-15 set (week 38)
```

Rules:

- `Done when` holds **one outcome per checkbox**. Split "merge X and deploy Y" into two.
- Each criterion must be checkable from GitLab or from something the user can point to. Rewrite "make progress on X" to "MR for X opened against the train" — ask once if you cannot.
- `Log` is append-only, one line per event: set, updated, gap check. Dates are `YYYY-MM-DD`.
- Never delete a ticked criterion.

## Dedupe and merge

Fetch active milestones with `scripts/gitlab_activity.py milestones --state active`. A candidate is any milestone whose title, `Achieve`, or `Contributes to` describes the same outcome as the interview answers. Show up to three candidates. The user picks **same goal** or **new goal**.

On **same goal**:

| Part | Rule |
|---|---|
| `Achieve`, `Contributes to` | keep, unless the new answer changes the meaning — then replace |
| `Done when` | keep every existing line (ticked or not); append new criteria that are not already present in meaning |
| `Log` | append `- <today> updated (week <n>): <what changed>` |
| `due_date` | this week's Sunday |
| `title` | keep |

## Commands

Group paths contain `/`, so URL-encode them. Group milestones are addressed by their **`id`** (the `milestone_id` path segment), not `iid`. The script prints both; use `id`.

```sh
host=$(glab config get host)               # or $GITLAB_HOST
group=infra                                # from config, see config.md
g=$(jq -rn --arg g "$group" '$g|@uri')
```

Write the body to a file first — it is long and contains markdown.

### Create

```sh
jq -n --arg title "$title" --rawfile description /tmp/milestone-body.md \
      --arg start_date "$monday" --arg due_date "$sunday" \
      '{title:$title, description:$description, start_date:$start_date, due_date:$due_date}' \
  > /tmp/milestone.json
glab api --hostname "$host" --method POST "groups/$g/milestones" --input /tmp/milestone.json \
  | jq '{id, iid, title, due_date, web_url}'
```

### Update

```sh
jq -n --rawfile description /tmp/milestone-body.md --arg due_date "$sunday" \
      '{description:$description, due_date:$due_date}' > /tmp/milestone.json
glab api --hostname "$host" --method PUT "groups/$g/milestones/$milestone_id" --input /tmp/milestone.json \
  | jq '{id, title, due_date, web_url}'
```

Send only the fields that change. Always send the **whole** body — `description` replaces, it does not patch.

### Close

Only when the user asks. `--method PUT` with `{"state_event":"close"}`.
