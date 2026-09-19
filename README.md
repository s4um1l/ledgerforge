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

Phase 0 — repository skeleton.
