# Audit status comes from the script

An AI-built repo often comes with a confident summary and a passing test suite.
Neither shows that the repo does what its PRD requires. An audit that lets
agents write "pass" has the same defect, because the reader cannot tell a
measured result from a claim.

We decided that **agents give judgment, and `scripts/audit.py` gives status.**
Agents write implementation status, findings, and gaps. The script records each
test run, then derives verification, evidence level, goal status, and the
verdict for staging and production. The data links go one way: gaps and
Decided entries refer to items, so that each role can work without gap IDs.

## Consequences

- Only a run through `audit.py run` is evidence. The run must match an expected
  output pattern, so a run of zero tests fails.
- P0 and goal evidence counts only from acceptance tests that an independent
  agent wrote from the PRD. The repo's own tests cannot certify a P0.
- Mixed outcomes in one run give `unstable`. A separate auditor must invalidate
  a failed attempt before the item can pass, so an agent cannot edit a test
  until it passes and hide the failure.
- The script accepts declared evidence levels. It cannot prove them. The test
  integrity auditor checks each claim, and a human must confirm each E4
  environment.
- A human approves the ledger, and decides each agent choice that the PRD did
  not specify. An agent cannot record these decisions for an absent human, so
  the gate stays NO-GO.
- The cost is high: about 100k tokens for each role on a small repo. This is
  acceptable before a first deployment. It is not a check for each change.
