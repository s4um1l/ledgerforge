"""The product evaluator: the three functions everything else is built on.

    evaluate_case(...)    one decision against one gold answer
    evaluate_suite(...)   a whole run, with metrics
    compare_runs(...)     before/after, with regressions named

Deliberately boring and deliberately first. This exists before the agent does,
so the agent is measured by something it had no hand in shaping.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections.abc import Sequence

from evals.gold import load_gold
from evals.loaders import load_cases, load_run
from evals.metrics import suite_metrics
from evals.paths import FIXTURES_DIR
from evals.schemas import Case, CaseResult, GoldAnswer, RunComparison, RunRecord, SuiteResult


def evaluate_case(
    record: RunRecord,
    gold: GoldAnswer,
    case: Case | None = None,
) -> CaseResult:
    """Grade one decision. Exact match on the routing action."""
    if record.case_id != gold.case_id:
        raise ValueError(f"record {record.case_id} graded against gold {gold.case_id}")
    return CaseResult(
        case_id=record.case_id,
        category=case.category if case else "unknown",
        expected=gold.gold_action,
        actual=record.action,
        passed=record.action is gold.gold_action,
    )


def evaluate_suite(
    records: Sequence[RunRecord],
    gold: dict[str, GoldAnswer] | None = None,
    cases: dict[str, Case] | None = None,
    label: str = "run",
    require_complete: bool = True,
) -> SuiteResult:
    """Grade a whole run.

    A run missing cases is an incomplete run, not a good one — by default that is
    an error rather than a quietly higher score.
    """
    gold = gold if gold is not None else load_gold()
    cases = cases if cases is not None else load_cases()

    seen = {r.case_id for r in records}
    unknown = sorted(seen - set(gold))
    if unknown:
        raise ValueError(f"run contains cases with no gold answer: {', '.join(unknown)}")
    missing = sorted(set(gold) - seen)
    if missing and require_complete:
        raise ValueError(f"run is missing {len(missing)} case(s): {', '.join(missing)}")

    results = [evaluate_case(r, gold[r.case_id], cases.get(r.case_id)) for r in records]
    results.sort(key=lambda r: r.case_id)

    architectures = {r.architecture for r in records}
    return SuiteResult(
        label=label,
        architecture=architectures.pop() if len(architectures) == 1 else "mixed",
        passed=sum(1 for r in results if r.passed),
        total=len(results),
        results=results,
        metrics=suite_metrics(
            results,
            latencies=[r.latency_ms for r in records if r.latency_ms is not None],
            costs=[r.cost_usd for r in records if r.cost_usd is not None],
        ),
    )


def compare_runs(before: SuiteResult, after: SuiteResult) -> RunComparison:
    """Diff two runs. Regressions are the number that can veto a change."""
    before_pass = before.passed_case_ids()
    after_pass = after.passed_case_ids()
    shared = {r.case_id for r in before.results} & {r.case_id for r in after.results}

    return RunComparison(
        before=before.label,
        after=after.label,
        before_passed=before.passed,
        after_passed=after.passed,
        total=max(before.total, after.total),
        newly_passing=sorted((after_pass - before_pass) & shared),
        newly_failing=sorted((before_pass - after_pass) & shared),
        unchanged_failures=sorted(shared - before_pass - after_pass),
    )


# --- reporting -----------------------------------------------------------


def format_suite(suite: SuiteResult) -> str:
    m = suite.metrics
    lines = [
        f"{suite.label}  [{suite.architecture}]",
        f"  {suite.passed}/{suite.total} cases correct   ({m.task_correctness:.1%})",
        f"  automation coverage      {m.automation_coverage:.1%}",
        f"  autonomous error rate    {m.autonomous_error_rate:.1%}   <- primary",
        f"  human review rate        {m.human_review_rate:.1%}",
        f"  reject rate              {m.reject_rate:.1%}",
    ]
    if m.latency_p50_ms is not None:
        lines.append(
            f"  latency p50/p95          {m.latency_p50_ms:.0f}ms / {m.latency_p95_ms:.0f}ms"
        )
    if m.total_cost_usd is not None:
        lines.append(f"  total cost               ${m.total_cost_usd:.4f}")
    if suite.failures:
        lines.append("  failures:")
        for r in suite.failures:
            lines.append(
                f"    {r.case_id:<5} {r.category:<14} expected {r.expected:<6} got {r.actual}"
            )
    return "\n".join(lines)


def format_comparison(cmp: RunComparison) -> str:
    lines = [
        f"{cmp.before} -> {cmp.after}",
        f"  {cmp.before_passed}/{cmp.total}  ->  {cmp.after_passed}/{cmp.total}",
        f"  newly passing   {', '.join(cmp.newly_passing) or '(none)'}",
        f"  REGRESSIONS     {', '.join(cmp.newly_failing) or '(none)'}",
        f"  still failing   {', '.join(cmp.unchanged_failures) or '(none)'}",
    ]
    return "\n".join(lines)


# --- cli -----------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals.accounting_eval",
        description="Evaluate an accounting agent run against the frozen benchmark.",
    )
    parser.add_argument(
        "run",
        nargs="?",
        type=pathlib.Path,
        default=FIXTURES_DIR / "fake_run_baseline.jsonl",
        help="run .jsonl to grade (default: the fake baseline fixture)",
    )
    parser.add_argument(
        "--against",
        type=pathlib.Path,
        help="a second run to compare against; REGRESSIONS are reported relative to it",
    )
    parser.add_argument("--json", type=pathlib.Path, help="also write the result as JSON here")
    args = parser.parse_args(argv)

    gold, cases = load_gold(), load_cases()
    suite = evaluate_suite(load_run(args.run), gold, cases, label=args.run.stem)
    print(format_suite(suite))

    payload: dict = {"suite": suite.model_dump(mode="json")}
    if args.against:
        baseline = evaluate_suite(load_run(args.against), gold, cases, label=args.against.stem)
        comparison = compare_runs(baseline, suite)
        print()
        print(format_comparison(comparison))
        payload["comparison"] = comparison.model_dump(mode="json")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"\nwrote {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
