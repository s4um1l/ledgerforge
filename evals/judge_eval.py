"""Evaluation 1 — judgment, with the candidate action held fixed.

Both judges see the same case, the same *fixed* candidate action from the
benchmark, and the same five questions worded identically. Neither proposes
anything. This isolates the decision layer from the reasoning layer.

    uv run python -m evals.judge_eval

Accuracy is the obvious metric and the less interesting one. The policy engine
thresholds raw probabilities, so a judge whose 0.9 means 90% is worth more than an
equally accurate judge whose 0.9 means "probably". That is what Brier measures,
and it is the hypothesis under test.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from collections.abc import Sequence

from evals.gold import load_gold
from evals.loaders import load_cases
from evals.metrics import brier_score, percentile
from evals.paths import REPO_ROOT, RESULTS_DIR
from product.accounting_agent.judges.jev_judge import JevJudge
from product.accounting_agent.judges.llm_judge import LLMJudge
from product.accounting_agent.judges.questions import LABELS
from product.accounting_agent.models import Action


def judge_suite(judge, cases: dict, gold: dict) -> dict:
    """Ask one judge every question about every case."""
    per_case, latencies, costs = [], [], []
    for case_id in sorted(cases):
        case = cases[case_id]
        payload = {
            "id": case.id,
            "category": case.category,
            "summary": case.summary,
            "input": case.input,
        }
        judgments = judge.judge(payload, Action(case.candidate_action))
        per_case.append(
            {
                "case_id": case_id,
                "values": judgments.values,
                "assumed": judgments.assumed,
                "gold": {label: getattr(gold[case_id].labels, label) for label in LABELS},
                "latency_ms": judgments.latency_ms,
                "cost_usd": judgments.cost_usd,
                "cached": judgments.cached,
            }
        )
        if not judgments.cached:
            latencies.append(judgments.latency_ms)
        costs.append(judgments.cost_usd)
        print(
            f"  {judge.name:<10} {case_id}  "
            + " ".join(f"{label[:4]}={judgments.values[label]:.2f}" for label in LABELS),
            flush=True,
        )

    return {
        "judge": judge.name,
        "cases": per_case,
        "latency_ms_p50": percentile(latencies, 0.50),
        "latency_ms_p95": percentile(latencies, 0.95),
        "total_cost_usd": round(sum(costs), 8),
    }


def score(suite: dict, include_assumed: bool = True) -> dict:
    """Accuracy and Brier, overall and per label."""
    per_label: dict[str, dict] = {}
    all_probs, all_outcomes = [], []

    for label in LABELS:
        probs, outcomes = [], []
        for entry in suite["cases"]:
            if not include_assumed and label in entry["assumed"]:
                continue
            probs.append(float(entry["values"][label]))
            outcomes.append(bool(entry["gold"][label]))
        if not probs:
            continue
        correct = sum(1 for p, o in zip(probs, outcomes, strict=True) if (p > 0.5) == o)
        per_label[label] = {
            "n": len(probs),
            "accuracy": round(correct / len(probs), 4),
            "brier": round(brier_score(probs, outcomes), 4),
            "positives": sum(outcomes),
        }
        all_probs += probs
        all_outcomes += outcomes

    correct = sum(1 for p, o in zip(all_probs, all_outcomes, strict=True) if (p > 0.5) == o)
    return {
        "judge": suite["judge"],
        "n_judgments": len(all_probs),
        "accuracy": round(correct / len(all_probs), 4),
        "brier": round(brier_score(all_probs, all_outcomes), 4),
        "per_label": per_label,
        "latency_ms_p50": suite["latency_ms_p50"],
        "latency_ms_p95": suite["latency_ms_p95"],
        "total_cost_usd": suite["total_cost_usd"],
    }


def confidence_histogram(suite: dict) -> dict:
    """Where a judge's probabilities actually land, and whether they are earned.

    A judge that says 0.9 on everything looks confident and is uninformative. The
    calibration column is what a reliability diagram would plot.
    """
    buckets = {f"{b / 10:.1f}-{(b + 1) / 10:.1f}": {"n": 0, "correct": 0} for b in range(10)}
    for entry in suite["cases"]:
        for label in LABELS:
            p = float(entry["values"][label])
            index = min(int(p * 10), 9)
            key = f"{index / 10:.1f}-{(index + 1) / 10:.1f}"
            buckets[key]["n"] += 1
            buckets[key]["correct"] += int((p > 0.5) == bool(entry["gold"][label]))
    for stats in buckets.values():
        stats["observed_rate"] = round(stats["correct"] / stats["n"], 3) if stats["n"] else None
    return buckets


def format_report(scores: Sequence[dict]) -> str:
    lines = ["", "=" * 74, "  EVALUATION 1 — judgment, fixed candidate action", "=" * 74, ""]
    lines.append(
        f"  {'judge':<12} {'n':>4} {'accuracy':>9} {'Brier':>8} {'p50 ms':>8} {'cost':>10}"
    )
    for s in scores:
        p50 = f"{s['latency_ms_p50']:.0f}" if s["latency_ms_p50"] else "cached"
        lines.append(
            f"  {s['judge']:<12} {s['n_judgments']:>4} {s['accuracy']:>8.1%} "
            f"{s['brier']:>8.4f} {p50:>8} {s['total_cost_usd']:>10.5f}"
        )
    lines += ["", "  per label:", ""]
    labels = scores[0]["per_label"].keys()
    header = f"  {'label':<24}" + "".join(f"{s['judge'][:10]:>22}" for s in scores)
    lines.append(header)
    for label in labels:
        row = f"  {label:<24}"
        for s in scores:
            stats = s["per_label"].get(label)
            row += f"{stats['accuracy']:>12.1%} /{stats['brier']:>8.3f}" if stats else f"{'-':>22}"
        lines.append(row)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare the two judges on fixed candidates.")
    parser.add_argument("--out", type=pathlib.Path, default=RESULTS_DIR / "phase6")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args(argv)

    cases, gold = load_cases(), load_gold()
    judges = [LLMJudge(use_cache=not args.no_cache), JevJudge(use_cache=not args.no_cache)]

    started = time.monotonic()
    suites = [judge_suite(judge, cases, gold) for judge in judges]
    scores = [score(suite) for suite in suites]
    asked_only = [score(suite, include_assumed=False) for suite in suites]

    print(format_report(scores))
    print("\n  excluding questions answered by absent evidence:")
    for s in asked_only:
        print(
            f"    {s['judge']:<12} n={s['n_judgments']:>4}  "
            f"accuracy {s['accuracy']:.1%}  Brier {s['brier']:.4f}"
        )

    args.out.mkdir(parents=True, exist_ok=True)
    payload = {
        "scores": scores,
        "scores_excluding_assumed": asked_only,
        "calibration": {
            s["judge"]: confidence_histogram(su) for s, su in zip(scores, suites, strict=True)
        },
        "suites": suites,
        "duration_seconds": round(time.monotonic() - started, 1),
    }
    (args.out / "judge_eval.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(f"\nwritten to {(args.out / 'judge_eval.json').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
