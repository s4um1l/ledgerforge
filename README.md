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

**Phase 1 — evaluator built, before the product exists.**

```bash
uv run python -m evals.accounting_eval
# fake_run_baseline  [llm_only]
#   24/30 cases correct   (80.0%)
#   autonomous error rate    33.3%   <- primary

uv run python -m evals.accounting_eval \
    evals/fixtures/fake_run_patched.jsonl --against evals/fixtures/fake_run_baseline.jsonl
# 24/30  ->  27/30      newly passing D05, R07, V02      REGRESSIONS (none)
```

`benchmark/` currently holds a **v0.0 scaffold**: 30 shape-correct cases in the 8/7/7/8 category
mix, with gold answers. Phase 4 replaces it with the frozen v0.1 benchmark. The run files under
`evals/fixtures/` are simulated agent output, which is the point — the evaluator produced a real
24/30 with no model in the loop.
