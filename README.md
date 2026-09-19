# ledgerforge

A minimal **software factory**: it takes a known product failure, turns it into a typed
engineering task, generates a scoped code change, validates that change against unit tests and a
product evaluation suite, and accepts or rejects it with a complete trace.

The factory is the product. The accounting agent it builds is the thing being measured.

```text
Observed failure → Work item → Context → Plan → Patch → Verification → Review → ACCEPT/REJECT → Trace
```

## Layout

```text
product/     the accounting agent under construction
benchmark/   frozen synthetic company, cases, and gold answers
evals/       deterministic evaluators and metrics
factory/     intake, context, planner, builder, validator, reviewer, orchestrator
prompts/     role prompts for the factory's model-backed stages
results/     raw run output (gitignored)
```

One boundary matters more than the rest:

```text
factory/  MAY read   product/, benchmark/cases/, benchmark/world/
factory/  MUST NOT read   benchmark/gold/
```

Only the evaluator reads gold answers. The coding system does not grade its own homework.

## Governing principle

```text
Models supply intelligence.
Software supplies boundaries, evidence and authority.
```

Models propose and judge. Deterministic code decides.

## Usage

```bash
uv sync

uv run pytest                                  # unit tests
uv run python -m evals.accounting_eval         # product evaluation
uv run python -m factory.run factory/tasks/ACCT-001.yaml
```

## Status

**Phase 2 — the factory loop runs end to end with no model in it.**

```bash
uv run python -m factory.validate_task factory/tasks/ACCT-001.yaml
uv run python -m factory.run factory/tasks/ACCT-001.yaml
uv run python -m factory.inspect                     # list runs
uv run python -m factory.inspect <run-id>            # one run in detail
```

A real run of `ACCT-001` ("enforce invoice tolerance policy", raised from the R07
failure):

```text
  [CREATED] [CONTEXT_READY] [PLANNED] [BUILT] [VALIDATED] [REVIEWED] [ACCEPTED]

  benchmark      24/30 -> 25/30
  target case    R07  FAIL -> PASS
  unit tests     46 passed, 0 failed
  regressions    (none)
    PASS  scope_respected          PASS  within_regression_policy
    PASS  static_checks_pass       PASS  declared_commands_pass
    PASS  unit_tests_pass          PASS  reviewer_accepts
    PASS  target_case_passes
```

The tolerance control in `product/accounting_agent/controls/tolerance.py` was
written by that run, not by hand.

### What the loop rejects

An accept path that cannot reject is a rubber stamp, so all three were exercised
against the live loop:

| Change | Caught by | Outcome |
|---|---|---|
| Tolerance control scoped too broadly | the unit test protecting R06 | `FAILED_VALIDATION` |
| A build that also edits `evals/` | scope check, from the git diff | `REJECTED_SCOPE` |
| Broad control **plus** deleting the test that objected | benchmark regression comparison | `REJECTED_REGRESSION` |

The third is the one worth dwelling on. Unit tests were green — the inconvenient
test was gone — the target case passed, and scope was clean. It was rejected
because R06 went from pass to fail. Deleting a test is invisible to a diff scan;
only re-running the whole benchmark sees it.

Every rejected change is reverted from the working tree and survives as
`diff.patch` in its trace. Re-running an already-fixed task halts at
`FAILED_BUILD` rather than reporting a success it did not earn.

### Still stubbed

`factory/fake_builds.py` holds a scripted patch and the planner/builder/reviewer
are deterministic — Phase 3 replaces them with a model, one at a time, in the
order builder → planner → reviewer. The validator stays deterministic throughout.
`benchmark/` is a v0.0 scaffold until Phase 4 freezes it.
