# myway

A Claude Code plugin defining development workflows for the Afterlife fleet.
It governs the scaffolding around a change — issue, branch, commits, change
request, pipeline — across both GitHub and a self-hosted GitLab.

## Language

### The work

**Change**:
A single unit of intended work — a feature, a bug fix, or a chore — traced end
to end from issue to green pipeline. The workflow is uniform across all three.
_Avoid_: task, ticket, story

**Change type**:
The conventional-commit type that classifies a Change: `feat`, `fix`, `chore`.
Determines the branch prefix and the commit type.

**Spec of record**:
The issue body. Holds the plan verbatim plus acceptance criteria, and is the
only artifact that survives a lost session — anything not written there is not
recoverable.
_Avoid_: ticket description, requirements

**Plan**:
The agreed sequence of implementation steps, authored before the Change begins
and copied verbatim into the Spec of record.

**Late entry**:
Invoking the workflow on a Change that is already written — dirty tree, local
commits, or a pushed branch — via "create an MR" / "open a PR". Joins the arc
at the first incomplete step; still verifies, still escorts, still stops before
merge.
_Avoid_: "just open the MR"

### Branches

**Pre-release train**:
A long-lived branch named `pre-release/<version>` that accumulates Changes for
the next release. Every feature branch is cut from the latest one, and every
change request targets it. Its name is the version source of truth.
_Avoid_: release branch, develop, staging

**Latest train**:
The `pre-release/*` branch on `origin` with the highest semver, by version sort.
The base for all new work.

**Feature branch**:
`<type>/<issue-id>-<brief>`, cut from the Latest train and checked out in its
own worktree at `.worktrees/<issue-id>-<brief>/`.

### Forge

**Forge**:
The remote hosting service for a repo — GitHub or the self-hosted GitLab.
Determined solely from `origin`.

**Change request**:
The proposal to merge a Feature branch into a Pre-release train. Rendered as
*pull request* on GitHub and *merge request* on GitLab; "change request" is the
forge-neutral term used throughout the workflow.
_Avoid_: PR, MR (as the canonical term — use them only when addressing a
specific forge)

**Escort**:
Watching a pipeline to conclusion and, on a CODE failure, fixing and re-pushing
within a bounded retry budget. Not merely notifying.

**CODE failure**:
A pipeline failure caused by the Change itself — compile error, test failure,
lint violation. Eligible for automatic fixing.

**INFRA failure**:
A pipeline failure caused by the environment — runner offline, queued past
timeout, registry or network error, disk full. Never eligible for automatic
fixing; the code is not what broke.

**Applicable CI**:
CI config belonging to the same Forge as `origin`, confirmed by a run actually
appearing after a push. A `.gitlab-ci.yml` in a GitHub-origin repo is not
Applicable CI.

### Goals

**Goal**:
One intended outcome for a week, stored as a GitLab **group** milestone whose
body holds what to achieve, what it contributes to, and the Criteria. A goal
may roll over into the next week; then the same milestone is updated.
_Avoid_: OKR, objective, sprint goal

**Goal group**:
The GitLab group that owns goal milestones. Chosen once, high enough to
contain every project a goal touches — issues outside it cannot take the
milestone.

**Criterion**:
One checkbox under `## Done when` in a Goal's body: an observable outcome
that GitLab evidence can confirm. One outcome per checkbox.
_Avoid_: key result, deliverable

**Window**:
The date range in which evidence counts for a gap check. Default: the
trailing 7 days. Bounds the evidence, not which Criteria are checked.

**Evidence**:
What a gap check is allowed to weigh, in order: issues linked to the Goal's
milestone (any author), then the user's own GitLab activity. Nothing else.

**Gap**:
Per Criterion, the verdict `met`, `partial`, or `none` with its citation. A
`none` or an uncovered `partial` becomes a Gap issue in the project the work
belongs to, linked to the milestone.

### Outcomes

**Verification**:
Running the repo's own build and tests locally before pushing. Required for
every Change, independent of whether CI exists.

**Blocked**:
A Change that could not reach green — failed Verification, spent retry budget,
ambiguous plan, or INFRA failure. Always lands as a draft Change request
stating the blockage, never as work stranded in a local worktree.
