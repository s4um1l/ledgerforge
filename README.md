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

**Phase 4 — benchmark frozen at v0.1.**

```bash
uv run python scripts/run_agent.py --out results/runs/current.jsonl
uv run python -m evals.accounting_eval results/runs/current.jsonl
uv run python -m factory.run factory/tasks/ACCT-001.yaml --all-models
```

`benchmark/` now holds a frozen world (company, chart of accounts, machine-readable
policy) and **32 cases** in a 10/7/7/8 mix, with gold answers and five atomic labels
each. It does not change again without a version bump.

### The freeze moved the score down, on purpose

```text
v0.0 scaffold   26/31   autonomous error rate 20.0%
v0.1 frozen     20/32   autonomous error rate 47.4%
```

No code got worse. The old cases had a median of three evidence fields, one case
carrying a date, and two carrying a ledger — so several controls were passing by
recognising fixture shapes rather than by doing accounting. v0.1 carries real
documents, dates, ledgers, remittance advice and approval thresholds, and the
defects that were always there are now visible:

| Case | What it exposes |
|---|---|
| R10 | **over-escalation** — the tolerance control sends a $50 invoice to a human because its blanket PO has no total |
| S02 | the cutoff control rejects an October-dated invoice for September work, which policy says to **accrue** |
| S07 | capitalization misses three sub-threshold items bought together for one purpose |
| R05, D07, S08 | duplicate detection does not read the frozen ledger shape, or the same-vendor-same-amount rule |
| V04 | a correct AUTO the control layer cannot reach, because controls may only *reduce* autonomy |

R09 and R10 are a deliberate pair: the same blanket purchase order, once where
failing closed is right and once where it is over-escalation. Without both, a
control that escalates everything scores as well as a correct one.

### Known limits of v0.1

`possible_duplicate` is true in 5 of 32 cases. That is realistic — duplicate rates
in real AP are low — but it means the label is measured on few positives. 21 cases
now carry a ledger, so the question is at least *answerable*; in v0.0 only two were.
`sources_consistent` is similarly skewed (27 true). If Phase 6 shows either label is
under-determined, the fix is a dedicated judge-eval slice, not distorting the suite
away from realistic frequencies.

### Phases

```text
0  repository skeleton                                        done
1  evaluator, before the product                              done
2  factory loop end to end, no models                         done
3  planner, builder and reviewer model-backed                 done
3.5 Jev smoke test, atomic labels designed against the wire   done
4  freeze world, cases, gold, labels as v0.1                  done
5  baseline agent: case -> frontier model -> candidate action
6  judge experiment: Jev vs structured-output LLM judge
7  three architectures, automation/risk curve
8  close the loop on one real failure
```
