# Escorting the pipeline

## Applicability

CI applies only when **the forge of `origin` has CI config for that same
forge**:

| `origin` | CI config that counts | Ignored |
|---|---|---|
| GitHub | `.github/workflows/*.yml` | `.gitlab-ci.yml` |
| GitLab | `.gitlab-ci.yml` | `.github/workflows/*.yml` |

Then **confirm by observation**: after pushing, a run must actually appear
within ~60s. If none does, CI does not apply — say so in the change request and
finish. Do not poll indefinitely for a pipeline that was never going to start.

Most repos have no CI. That is a normal outcome, not a failure; local
verification already gave the change its meaning.

## Polling

### GitHub

```sh
# most recent run for the branch
gh run list --branch "<branch>" --limit 1 --json databaseId,status,conclusion

# block until it finishes; non-zero exit on failure
gh run watch <run-id> --exit-status

# failing logs only
gh run view <run-id> --log-failed
```

### GitLab

```sh
glab ci status --branch "<branch>" --output json
glab ci list --ref "<branch>" --per-page 1 --output json
glab ci trace <job-id-or-name>
```

Poll on an interval (~20s) rather than tight-looping. Treat a pipeline still
**queued after ~10 minutes** as INFRA — the runners here are single
self-hosted instances, so an unavailable runner presents as a pipeline that
never starts, not as one that fails.

## Classify before reacting

Read the failing job's log and decide **CODE** or **INFRA** before touching
anything.

### CODE — fix it

Compiler and linker errors, test failures, assertion failures, type errors,
lint and format violations, missing symbols or includes, failures that
reproduce locally.

→ Diagnose, fix, commit `fix(ci): …`, push, re-watch.
→ **Maximum 3 attempts.** Then stop and report.

### INFRA — never touch the code

- No runner available; job pending or queued past timeout; runner offline
- Registry or network failure: image pull failure, DNS, TLS, connection reset,
  429 or 5xx from a registry or package index
- Disk full, out of memory on the runner, job cancelled by the system
- Timeouts with no test or build output at all

→ Report immediately with the evidence. Do not commit, do not push, do not
retry the code.

**Retrying the pipeline** (`gh run rerun`, `glab ci retry`) is acceptable
**once** for a clearly transient infra failure. Beyond that, report — a runner
that is down does not come back because you asked twice.

The reason this split is mandatory: a self-hosted runner going offline would
otherwise send the loop "fixing" code that was never broken, and land three
speculative commits on the branch before giving up.

## The retry budget

Three CODE attempts, counted across the whole escort — not per job, not per
pipeline. When the budget is spent, convert the change request to **draft** and
state in the body what failed, what was tried, and what is now suspected.

If the same failure recurs unchanged after a fix attempt, stop early. Repeating
a fix that did not work is not a second attempt, it is a loop.

## Reporting

On success:

```
✓ pipeline #332 passed — 4 jobs, 6m12s
```

On a spent budget or infra failure, be specific and do not soften it. "3 fix
attempts, all failed" is the report; "mostly working" is not.
