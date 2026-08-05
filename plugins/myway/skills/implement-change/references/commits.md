# Commits

## Format

[Conventional Commits](https://www.conventionalcommits.org/), with a mandatory
issue trailer:

```
<type>(<scope>): <subject>

<optional body — why, not what>

Refs: #42
```

- **Subject** — imperative mood, lower case, no trailing period, ≤72 chars.
  "add retry policy", not "Added retry policy." or "adds retry policy".
- **Scope** — the module or component touched (`router`, `easytier`, `ci`).
  Omit rather than invent one.
- **Body** — only when the *why* is not obvious from the subject. Skip it
  freely; a body that restates the diff is noise.

## Types

| Type | Use for |
|---|---|
| `feat` | New capability |
| `fix` | Corrected behaviour |
| `chore` | Dependency bumps, tooling, housekeeping |
| `docs` | Documentation only |
| `test` | Tests only |
| `refactor` | Behaviour-preserving restructuring |
| `perf` | Performance work |
| `build` / `ci` | Build system, pipeline config |

Breaking changes: `feat(router)!: …` plus a `BREAKING CHANGE:` trailer.

## `Refs:`, never `Closes:`

Every commit gets `Refs: #42`.

Do **not** use `Closes:` / `Fixes:`. Those auto-close the issue when the commit
lands on the *default* branch — but this workflow merges into a **pre-release
train**, so on GitHub the keyword sits dormant until the train reaches `main`,
and on GitLab it can fire early depending on project settings. Either way the
issue's lifecycle stops matching reality. The issue stays open until the change
actually ships; closing it is a release-time act, not a merge-time one.

## Granularity

**One commit per logical unit, committed the moment it is self-contained.**

Not one squashed commit at the end: with the session potentially dying
mid-feature, incremental commits are the only durable record of progress, and
they are what makes the change request reviewable and the branch bisectable.

Not one commit per plan step either: plans are written before contact with the
code, and steps merge, split, and reorder in practice. Forcing a 1:1 mapping
means faking it.

A good unit compiles and, where practical, keeps the tests passing.

```
feat(router): add OrderRouter interface

Refs: #42

fix(router): handle empty venue list

The venue selector assumed at least one enabled venue; a fully
disabled config crashed at startup.

Refs: #42

test(router): cover partial-fill path

Refs: #42
```

## CI fix commits

Commits pushed by the escort loop follow the same rules and state that they are
pipeline fixes:

```
fix(ci): add missing <algorithm> include

Refs: #42
```

## Branch names

`<type>/<issue-id>-<brief>`, where `<type>` matches the change's primary
conventional type and `<brief>` is kebab-case from the issue title, about four
words:

```
feat/42-order-router
fix/43-nil-deref-on-empty-venue
chore/44-bump-easytier-2-4-5
```

The worktree directory drops the type: `.worktrees/42-order-router/`. The issue
id appears in both, so state is recoverable from either.
