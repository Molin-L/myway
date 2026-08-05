---
name: implement-change
description: End-to-end change workflow — issue → branch off the latest pre-release train → conventional commits → change request → bounded CI escort. Use when the user gives an explicit instruction to change code now ("implement this plan", "fix this bug", "bump easytier to 2.4.5", "add rate limiting"). Do NOT use for questions, explanation, code review, exploration, or hypothetical and future-tense work ("how does X work?", "we should probably add Y someday").
---

# Implement a Change

This skill governs the **scaffolding around a change**: the issue that specifies it, the branch it lives on, the commits that build it, the change request that proposes it, and the pipeline that proves it.

**It does not tell you how to write the code.** Implementation strategy is yours (or another skill's — `tdd`, `diagnosing-bugs`). This skill decides where the work lives and what shape it lands in.

## Fire / don't fire

The workflow runs **without approval gates** — one instruction produces an issue, a branch, commits, and a change request on a real remote. The trigger is therefore the only brake. Be conservative.

| Fires | Does not fire |
|---|---|
| "implement the plan in docs/plans/router.md" | "how does OrderRouter work?" |
| "fix the nil deref in OrderRouter" | "we should add rate limiting someday" |
| "bump easytier to 2.4.5" | "review this diff" |
| "add a retry policy to the venue client" | "what would it take to add X?" |

Also do not fire when: not inside a git repo, `origin` is missing, or the working tree belongs to a repo whose forge you cannot authenticate against. Say so plainly and stop.

## The arc

Eight steps. Run them in order. Do not skip ahead, and do not ask for permission between them.

### 1. Classify and draft the issue

Pick the change type — `feat`, `fix`, or `chore` (use `docs`, `refactor`, or `perf` only when clearly more accurate). **Every change type gets an issue**, including a one-line dependency bump; the branch naming convention structurally requires an issue id.

The issue body is the **spec of record**. It is the only artifact that survives a `/clear`, a new session, or a different machine — write it so that `gh issue view 42` alone is enough to resume:

```md
## Context
Why this change is needed.

## Plan
1. Full implementation plan, verbatim — not a summary.
2. …

## Acceptance criteria
- [ ] Observable, checkable outcomes.
- [ ] …
```

If the user handed you a plan, it goes in **verbatim**. If they didn't (a bump, a small fix), write the plan you're about to follow. Create the issue and capture its number — see [references/forge.md](references/forge.md).

### 2. Resolve the base branch

Never branch from `main`. Branch from the **latest pre-release train**:

```sh
git ls-remote --heads origin 'refs/heads/pre-release/*' \
  | sed 's|.*refs/heads/pre-release/||' | sort -V | tail -1
```

If no train exists, create one from the default branch with a **minor** bump (`0.2.0` → `pre-release/0.3.0`). Full resolution and bump rules: [references/versioning.md](references/versioning.md).

### 3. Branch, in a worktree

```sh
git worktree add .worktrees/<id>-<brief> -b <type>/<id>-<brief> origin/pre-release/<version>
```

The brief is kebab-case from the issue title, ~4 words. Both the branch and the directory carry the issue id, so state is recoverable from either.

Work in the worktree. The main checkout stays free — that is the point, since the user has walked away and may want to use it.

Ensure `.worktrees/` is in the repo's `.gitignore`; add it if missing (this is a legitimate part of the change).

### 4. Implement, committing as you go

Commit **one logical unit at a time**, the moment it is self-contained — not in a batch at the end. With the session potentially dying mid-feature, incremental commits are the only durable record of progress.

```
feat(router): add OrderRouter interface

Refs: #42
```

`Refs:`, never `Closes:` — this branch merges into a pre-release train, not `main`, and `Closes` would shut the issue before the change ever ships. Full rules: [references/commits.md](references/commits.md).

### 5. Verify locally — always

Run the repo's own build and tests **before pushing**, whether or not CI exists. Most repos have no CI at all, so this is the only definition of "done" that holds everywhere; where CI does exist, it stops broken pushes from burning a shared self-hosted runner.

Resolve the verify command from `.myway.toml`, else infer it from the build system — see [references/config.md](references/config.md). If no verify command can be determined, **say so explicitly in the change request body**; never silently skip it and imply the change was checked.

Verification failing is not the end of the run — see [Failure contract](#failure-contract).

### 6. Open the change request

Push the branch and open a change request **targeting the pre-release train**, never the default branch.

```md
## Summary
What changed and why, in a few lines.

## Acceptance criteria
- [x] Copied from the issue, ticked as met.

## Verification
`ctest --test-dir build` — 41 passed, 0 failed.

Refs: #42
```

Commands per forge: [references/forge.md](references/forge.md).

### 7. Escort the pipeline

Only if CI actually applies — that means **the forge of `origin` has CI config for that same forge**, confirmed by a run appearing after the push. A `.gitlab-ci.yml` in a repo whose `origin` is GitHub will never fire; waiting on it hangs forever.

Poll to conclusion. On red, **classify before reacting**:

- **CODE** (compile error, test failure, lint) → diagnose, fix, commit `fix(ci): …`, push, re-watch. **Maximum 3 attempts**, then stop.
- **INFRA** (no runner available, queued past timeout, registry/network failure, disk full) → **never touch the code.** Report and stop.

The runners are single self-hosted instances. A runner being down presents as an eternally queued pipeline, not a failure — treat prolonged queueing as INFRA, not as something to fix. Classification signals and polling commands: [references/escort.md](references/escort.md).

### 8. Stop

Green pipeline, change request open, issue still open. **Do not merge** — that is the user's call.

Report: issue link, change request link, pipeline status, and the worktree path.

## Failure contract

If anything blocks — verification won't pass, CI is red after 3 attempts, the plan turns out ambiguous, a runner is down — **still push the branch and still open the change request, as a draft**, with the blockage stated in the body:

```md
## ⚠ Blocked

Local build failed: `OrderRouter.cpp:88: no member named 'venue_id'`
3 fix attempts, all failed. The plan assumes a `venue_id` field that does not exist on `Venue`.

Needs a decision before this can proceed.
```

The user walked away. The outcome must be discoverable where they will look — the forge. Work stranded in a local worktree is invisible from GitHub or GitLab and does not count as a result.

Never report a change request as ready when it is blocked, and never describe unverified work as verified.

## Resuming mid-flight

When invoked in a worktree already on a `<type>/<id>-<brief>` branch, do not start over. Recover state and continue:

1. Issue id from the branch name → read the issue for the spec.
2. `git log origin/pre-release/<v>..HEAD` → what is already committed.
3. Query the forge → does a change request already exist? What is the pipeline status?
4. Rejoin the arc at the first incomplete step.

## References

| File | Contents |
|---|---|
| [references/forge.md](references/forge.md) | GitHub/GitLab detection, issue and change-request commands, id capture |
| [references/versioning.md](references/versioning.md) | Pre-release train resolution, semver sort, minor bump, version-file sync |
| [references/commits.md](references/commits.md) | Conventional Commits rules, types, scopes, trailers |
| [references/escort.md](references/escort.md) | CI applicability, polling, CODE vs INFRA classification, retry budget |
| [references/config.md](references/config.md) | `.myway.toml` schema and verify-command inference |
