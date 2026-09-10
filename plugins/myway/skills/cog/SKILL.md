---
name: cog
description: Maintain the repository's cognition docs under docs/cognition/ — the user's own model of the system (Believes / Decided / Unknown). Use ONLY when the user explicitly invokes "/cog init" or "/cog update". Never trigger from task content, feature work, or commit activity on its own. "/cog init" interviews the user to record or revise their understanding. "/cog update" compares the docs against a git commit range and proposes tagged edits plus a chat report.
---

# cog

The cognition doc records what the user holds true about the system. It is the user's model, not the agent's. The agent transcribes and proposes. The user decides.

Two commands. Both are explicit. Do not run either one unless the user invoked it.

- `/cog init` — interview. Source: the user's statements. Writes untagged lines.
- `/cog update [<base>..<head>]` — compare docs to commits. Source: the diff. Writes `[pending]` lines only.

## State

```
docs/cognition/
  README.md      # format rules + `updated-through: <sha>`
  <topic>.md     # one file per subsystem
```

Topic file format:

```markdown
# <topic>

## Believes
- B1 <one falsifiable fact>

## Decided
- D1 <one choice> ref: <issue|commit|doc>

## Unknown
- U1 <one thing the user has not examined>
```

Rules:

- English only.
- One fact per line. No prose paragraphs.
- IDs: `B`, `D`, `U` plus an integer. IDs are stable. Never reuse an ID after a line is dropped.
- Every `D` line has a `ref:`.
- Cap: 50 content lines per file. Flag files over the cap; do not prune them yourself.
- `[pending]` suffix marks a line the agent proposed and the user has not reviewed. Only `/cog update` writes it.
- Never delete a line during `/cog update`. The user deletes on review.
- Never rename or merge topic files. The user does.

Read `assets/template.md` for the empty topic file. Read `assets/readme.md` for the README template.

## /cog init

Mode is chosen by state. Do not ask which mode.

### Fresh — `docs/cognition/` absent

1. Survey the repo: tree, build files, entry points, top-level README. Do not read deep. Propose 3 to 8 topics with one line each. Show the list. The user edits it. Wait for confirmation.
2. Interview one topic at a time. For each topic ask, in order:
   - What do you hold true about this part?
   - What have you decided, and where is it recorded?
   - What have you not looked at?
   Also show 3 to 6 candidate facts you found in code. The user marks each: believe / decided / unknown / drop. Write only what the user confirmed.
3. Write topic files from `assets/template.md`. Write `README.md` from `assets/readme.md` with `updated-through: <HEAD sha>`.
4. Run `python "${CLAUDE_PLUGIN_ROOT}/skills/cog/scripts/lint.py" docs/cognition`.
5. Report: file list with line counts. Nothing is `[pending]`.

### Existing — `docs/cognition/` present

1. Read all topic files. Run lint. If `[pending]` lines exist, resolve them first. Show each line. The user answers accept / edit / drop. Accepted lines lose the tag. Dropped lines are deleted.
2. Survey the repo. Propose new topics only for code areas no existing topic covers. The user edits the list.
3. Interview one topic at a time. Show the topic's current lines. Then ask:
   - What changed in what you hold true?
   - What have you decided since?
   - What is no longer unknown?
   - What is now unknown?
   Apply the user's adds, edits, and drops.
4. Write. Do not change `updated-through`.
5. Run lint.
6. Report: per topic, IDs added / edited / dropped. Files over 50 lines flagged.

Interview rules:

- One topic per turn. Do not batch topics.
- Transcribe the user's words. Do not reword into your own interpretation.
- If the user's statement contradicts an existing line, show both and ask which stands. Do not resolve it yourself.
- A statement from you that the user did not confirm is not written.

## /cog update [<base>..<head>]

Refuse if `docs/cognition/` is absent. Tell the user to run `/cog init`.

Default range: `<updated-through>..HEAD`. Refuse if the range is empty and say so.

1. Read all topic files and `README.md`.
2. Run `git log --oneline <range>` and `git diff --stat <range>`. Then read `git diff <range>` for the changed paths.
3. Map changed paths to topics by the topic's subject, not by directory name alone. Paths that map to no topic go to the report under "Unmapped paths". Do not create a topic for them.
4. For every line in the mapped topics, check the diff:
   - Contradicted: edit the line in place to the new fact. Append `[pending]`. Keep the ID.
   - Extended: leave the line. Add a new line with a new ID and `[pending]`.
   - Untouched: leave the line. Do not mention it in the report.
5. Scan commit messages and the diff for new decisions: new dependency, interface change, config default, removed component, changed protocol. Each becomes a `D` line with `ref: <sha>` and `[pending]`.
6. Check `U` lines against the diff. A resolved unknown is edited in place to state the answer, moved under `## Believes` with a new `B` ID, and the original `U` line is marked `resolved -> B<n> [pending]`.
7. Add new `U` lines for questions the diff raises and does not answer. Tag `[pending]`.
8. Write files. Write `updated-through: <head sha>` in `README.md`.
9. Run lint.
10. Report in chat only. Do not write the report to a file. Use this structure and no other:

```
## Invalidated
- B4 — <sha> <one line: why>

## New decisions
- D9 [pending] <text> ref: <sha>

## Resolved unknowns
- U2 -> B11

## New unknowns
- U7 [pending] <text>

## Requires your decision
- <one line each; only items that block or fork future work>

## Unmapped paths
- <path> — <one line: what changed>

## Evidence
- <sha> <subject>  (each commit in the range)
```

Report rules:

- No untagged doc line appears in the report.
- No narrative of what you did or in which order.
- Omit an empty section. Keep the heading order for the rest.
- "Requires your decision" holds only items where the user must choose. It does not hold status.

## Lint

Lint script: `scripts/lint.py` in this skill directory.

`python "${CLAUDE_PLUGIN_ROOT}/skills/cog/scripts/lint.py" docs/cognition`

Checks: three sections present, ID format and uniqueness within a file, `ref:` on every `D` line, 50-line cap. Prints all `[pending]` lines as the review queue. Exit 1 on a format error, 0 otherwise (pending lines are not errors).
