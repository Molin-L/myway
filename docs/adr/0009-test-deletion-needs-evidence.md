# A test deletion needs evidence

Coding agents add tests for each small change. Many tests repeat a contract, check a mock, or keep a test-only seam alive. These tests add cost, and weak tests can give the next agent a wrong target. An instruction to "clean up the tests" stops too early, or it deletes protection. A limit such as "keep coverage within 2%" allows both failures: a line can still run after the test that checked it is gone.

OpenClaw's `test-audit` skill gives the base model: an authoring gate, a list of junk patterns, and a retention bar. We use these ideas. We add our trading contracts, and we move each status to a script, as in ADR 0008.

We decided that **a deleted test must have evidence, and a new test must name the wrong behavior that it rejects.** Agents judge the value of a test. `scripts/test_audit.py` measures each test alone and derives each status.

## Consequences

- The gate compares covered lines, not a percentage. Each line that loses coverage must have a declaration, and no other test can cover it.
- `check` simulates the whole batch. Two duplicate tests each have no unique line, but they cannot both go without a declaration.
- `gate` needs stable line numbers, so the first commit changes only tests. Dead production code goes in a later commit. The cost is one extra commit for each batch.
- `prove` needs a build, a pass before the patch, a failure after the patch, and an output match. A build failure or a crash is not a proof. Each run builds in a new worktree, so a slow C++ build needs a compiler cache.
- The script does not compute unique mutant kills for each test. Mutation tools report survivors for a suite, and one run for each test costs too much. The gate compares the survivors before and after the batch, and hand-written contract mutants cover what the tools do not generate.
- The script does not read CI failure history, because that depends on the forge. The discovery agent records it in the candidate.
- A human must approve a change to a contract test. The script cannot prove this approval, so an agent must not write it for an absent human.
- `collect` runs each test in its own process. On a large repo, the cost is high. Scope each batch to one module.
