# Gap — measure the distance between the goal and the evidence

Run this arc for `/weekly-goal-gap` or when the user asks for a gap check. It reads GitLab through `scripts/gitlab_activity.py` and writes through `glab api` (commands in [milestone.md](milestone.md) and below). Configuration: [config.md](config.md).

The arc has two approval gates: the goal group when it is not configured (step 0), and a gap issue's project when it cannot be inferred (step 7). Report at the end, not at each step.

## 0. Resolve the goal group

If the script exits with `no goal group`, list `scripts/gitlab_activity.py groups` and ask which group holds the goals — see *Step 0* in [SKILL.md](../SKILL.md). Do not guess.

## 1. Resolve the window

| Argument | Window |
|---|---|
| none | trailing 7 days ending today |
| `--days N` | trailing N days ending today |
| `--since D [--until D]` | explicit; `--until` defaults to today |

The window bounds **evidence** (notes, merge requests, events). It does not bound which criteria are checked — every unchecked criterion is checked, every time.

## 2. Resolve the goals in scope

```sh
scripts/gitlab_activity.py milestones --state active
```

- A milestone argument (id or exact title) → that goal only.
- No argument → every active milestone of the goal group.
- No active milestone → say so and stop. Suggest `/weekly-goal`.

## 3. Gather evidence, in order

For each goal:

```sh
scripts/gitlab_activity.py evidence --milestone <id> --days N > /tmp/weekly-goal-<id>.json
```

The output carries the evidence in the order it must be weighed:

1. **`issues`** — every issue linked to the milestone, **any author**, with state, assignees, notes inside the window, issue links, and related merge requests. This is the primary source: it is what the team can see.
2. **`my_events`** — the user's own activity inside the window: pushes, merge requests opened/accepted, issues opened/closed, comments. This is the secondary source: it catches work that no linked issue records.

Do not use other sources. If the evidence is thin, the verdict is thin; say so rather than fill the gap with assumptions.

## 4. Judge every unchecked criterion

Parse `## Done when` from `milestone.description`. For each `- [ ]` line, search the evidence and assign one verdict:

| Verdict | Meaning | Typical evidence |
|---|---|---|
| `met` | the outcome is observable now | linked issue closed; related MR merged; a push/accept event that is the outcome itself |
| `partial` | work exists, outcome not yet observable | linked issue open with notes or an open MR; pushes to a branch for it; issue opened but idle |
| `none` | nothing on GitLab points at it | no linked issue, no event matches |

Rules:

- Match on meaning: project path, issue/MR titles, commit titles, note bodies. A criterion about "the router" matches an MR titled `feat(router): …`.
- Linked issues outrank events. If a linked issue is still open, the criterion is at most `partial`, even if a push looks finished.
- Cite the evidence for every verdict: issue refs (`infra/agentic/nightshift#10`), MR refs (`!29`), event dates. A verdict without a citation is a guess — mark it `partial` and say why.
- `met` ticks the box. Nothing else changes the checklist.

## 5. Tick and log

If any criterion became `met`, rewrite those lines as `- [x]`, append to `## Log`:

```
- 2026-09-22 gap check (2026-09-15..2026-09-22): 1/3 met; opened infra/moonlink#41, infra/agentic/nightshift#12
```

and `PUT` the milestone (see [milestone.md](milestone.md)). Do the `PUT` once, after step 6, so the log line can name the issues.

## 6. Print the gap

One table per goal, then one line of totals:

```
Goal: Ship OrderRouter to pre-release   (due 2026-09-21)   <url>

| Criterion | Verdict | Evidence | Action |
|---|---|---|---|
| MR for OrderRouter merged into the train | partial | !29 open, 3 pushes 09-18..09-20 | none — covered by nightshift#10 |
| Router smoke test in CI | none | — | open issue in infra/agentic/nightshift |
| Runbook page published | met | moonlink#40 closed 09-19 | ticked |

1/3 met, 1 partial, 1 none. Window 2026-09-15..2026-09-22.
```

## 7. Open gap issues

For each criterion that is `none`, or `partial` **without an open linked issue that covers it**, create one issue in the project the work belongs to.

**Project resolution**, first match wins:

1. The project of the linked issues or merge requests cited for that criterion.
2. The project of the events cited for that criterion.
3. A project from `scripts/gitlab_activity.py projects` whose path clearly matches the criterion text.
4. Ask the user — one question listing the candidates. This is the only approval gate in the arc.

**Do not create** an issue when an open linked issue already covers the criterion; cite that issue in the `Action` column instead.

Title: imperative, conventional-commit style consistent with `implement-change` (`feat: …`, `fix: …`, `chore: …`). Body:

```md
## Context
Weekly goal: <title> — <milestone url>
Criterion: <the checkbox text, verbatim>
Gap as of <today>: <verdict>. <one line of cited evidence, or "no evidence on GitLab">

## Acceptance criteria
- [ ] <the criterion, verbatim>
```

```sh
me=$(scripts/gitlab_activity.py me | jq .id)
p=$(jq -rn --arg p "$project_path" '$p|@uri')
jq -n --arg title "$title" --rawfile description /tmp/gap-issue.md \
      --argjson milestone_id "$milestone_id" --argjson me "$me" \
      '{title:$title, description:$description, milestone_id:$milestone_id, assignee_ids:[$me]}' \
  > /tmp/gap-issue.json
glab api --hostname "$host" --method POST "projects/$p/issues" --input /tmp/gap-issue.json \
  | jq '{project_id, iid, web_url, milestone: .milestone.title}'
```

`milestone_id` is the group milestone's `id`. Check the response's `milestone.title` — a project outside the goal group cannot take the milestone, and GitLab returns an issue without one instead of an error.

## 8. Relations — `blocks` / `is_blocked_by`

Add a relation only when the evidence shows the dependency. Signals:

| Signal | Relation from the new issue |
|---|---|
| The criterion's outcome needs an open linked issue or open MR to land first | `is_blocked_by` that issue |
| A note, description, or title says "after X", "depends on X", "once X is merged" | `is_blocked_by` X |
| An open milestone issue says it waits on this outcome | `blocks` that issue |
| Two gap issues opened in this run where one is a prerequisite of the other | `blocks` from the prerequisite |

Never infer a dependency from order in the checklist alone.

```sh
jq -n --argjson target_project_id "$tpid" --argjson target_issue_iid "$tiid" --arg link_type "is_blocked_by" \
      '{target_project_id:$target_project_id, target_issue_iid:$target_issue_iid, link_type:$link_type}' \
  > /tmp/link.json
glab api --hostname "$host" --method POST "projects/$p/issues/$iid/links" --input /tmp/link.json \
  | jq '{link_type, target: .target_issue.references.full}'
```

`link_type` is one of `relates_to`, `blocks`, `is_blocked_by`. Blocking link types need a GitLab Premium/Ultimate license; on a lower tier the API stores the link as `relates_to`. Read `link_type` back from the response and, if it downgraded, say so in the report — do not claim a blocking relation that does not exist.

## 9. Report

Per goal: the gap table. Then:

- issues opened, as `project#iid — title — url`
- relations created, as `A is_blocked_by B` (or the downgrade note)
- the milestone URL and the new `Log` line

Never describe a criterion as met without a citation, and never describe an issue as linked to the milestone without checking the response.
