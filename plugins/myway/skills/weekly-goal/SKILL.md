---
name: weekly-goal
description: Weekly goals as GitLab group milestones. Two modes — set a goal through a three-question interview (`/weekly-goal`), or measure the gap between the goal's "done when" criteria and the evidence on GitLab (`/weekly-goal-gap`). Use when the user says "weekly goal", "goal for this week", "what is my gap", "how far am I from my goal", or "gap check". Do NOT use to implement a change (that is `implement-change`), and do NOT use for daily stand-up notes or time tracking.
---

# Weekly Goal

A weekly goal is a **GitLab group milestone**. The milestone body holds what to achieve, what it contributes to, and the criteria that say it is done. Issues in any project of the group link to it. The gap between the criteria and the evidence on GitLab is measured, not guessed.

Two modes share this skill:

| Mode | Trigger | Arc |
|---|---|---|
| Set a goal | `/weekly-goal`, "set my goal for this week" | below |
| Measure the gap | `/weekly-goal-gap`, "what is my gap", "gap check" | [references/gap.md](references/gap.md) |

Both modes read GitLab through `scripts/gitlab_activity.py` (relative to this skill directory; under Claude Code that is `${CLAUDE_PLUGIN_ROOT}/skills/weekly-goal/scripts/gitlab_activity.py`). Both write GitLab through `glab api`. Setup and script usage: [references/config.md](references/config.md).

## Why a group milestone

A goal for the week usually spans several repos. Only a **group** milestone can be assigned to issues across projects, so the goal lives on the group, never on a project. The group is configured once — see [references/config.md](references/config.md).

## Step 0 — resolve the goal group (both modes)

Run `scripts/gitlab_activity.py milestones` first. If it exits 1 with `no goal group`, **stop and ask** — never guess a group and never pick one silently:

```sh
scripts/gitlab_activity.py groups
```

Show the groups as a list and ask one question: *which group should hold your weekly goals?* Remind the user that issues outside that group cannot take the milestone, so the highest group that contains all their projects is the right pick. Then continue with `--group <answer>` on every script call in this session, and tell the user once how to persist it:

```toml
# ~/.config/myway/weekly-goal.toml
[gitlab]
group = "<answer>"
```

The same rule applies when `glab` is not authenticated: say so and stop.

## Set a goal — the arc

### 1. Interview, one question at a time

Ask exactly three questions, **in this order, one per message**. Wait for the answer before asking the next. Do not bundle them, do not suggest answers, do not paraphrase the previous answer back unless it was ambiguous.

1. **What do you want to achieve this week?**
2. **What does that contribute to?** (the larger outcome, project, or person it serves)
3. **How will you know it is done?** (observable outcomes — push for checkable ones; if the answer is vague, ask once for something you could tick)

Question 3 becomes the `Done when` checklist. Split a compound answer into one checkbox per outcome.

### 2. Dedupe against existing milestones

```sh
scripts/gitlab_activity.py milestones --state active
```

Compare the three answers with every active milestone's title, `Achieve`, and `Contributes to`. Judge on meaning, not on string match — "ship the router" and "get OrderRouter into the release" are the same goal.

- **No plausible match** → say "no similar active goal" and continue as a new goal. Do not ask.
- **One or more plausible matches** → show each candidate (title, `Achieve` line, due date, URL) and ask **one** question: *same goal as one of these, or a new goal?* The user decides; never auto-merge.

**Same goal** means update: keep the milestone id, keep ticked criteria, add the new criteria that are not already listed, replace `Achieve` / `Contributes to` only if the user's answers changed them, and extend `due_date` to this week. **New goal** means create.

### 3. Show the full body, then confirm

Render the complete milestone — title, start date, due date, and the whole body from [references/milestone.md](references/milestone.md) — and ask one question: *create this?* (or *apply this update?*). For an update, show the resulting body, not a diff.

Apply edits the user asks for and show the body again. Do not write until the user says yes.

### 4. Create or update

Commands and field rules (group milestones are addressed by `id`, not `iid`): [references/milestone.md](references/milestone.md).

### 5. Report

Milestone URL, title, due date, and the criteria as a checklist. Mention that `/weekly-goal-gap` measures progress.

## Measure the gap

Follow [references/gap.md](references/gap.md). Summary: resolve the window (default trailing 7 days) and the goals in scope, gather evidence from the milestone's linked issues first and personal activity second, judge every unchecked criterion, tick the met ones, print the gap, and open issues for the rest — linked to the milestone, with `blocks` / `is_blocked_by` relations where the evidence shows a dependency.

## References

| File | Contents |
|---|---|
| [references/milestone.md](references/milestone.md) | Milestone title, dates, body format, create/update commands, dedupe and merge rules |
| [references/gap.md](references/gap.md) | The gap arc: window, scope, evidence order, verdicts, gap issues, relations |
| [references/config.md](references/config.md) | Goal group configuration, `glab` auth, script subcommands and output |
| `scripts/gitlab_activity.py` | Read-only GitLab fetcher (milestones, issues with notes/links/MRs, events) |
