"""Metrics. Pure functions over results — no I/O, no models.

The primary production-style metric is the autonomous error rate:

    wrong automatically executed actions / all automatically executed actions

Task correctness is the headline number, but it is the wrong thing to optimise
on its own: a system that routes everything to a human scores well on errors and
is worthless. Read coverage and error rate together.
"""

from __future__ import annotations

from collections.abc import Sequence

from evals.schemas import Action, CaseResult, SuiteMetrics


def accuracy(results: Sequence[CaseResult]) -> float:
    if not results:
        return 0.0
    return sum(1 for r in results if r.passed) / len(results)


def automation_coverage(results: Sequence[CaseResult]) -> float:
    """Share of cases the system acted on without a human."""
    if not results:
        return 0.0
    return sum(1 for r in results if r.actual is Action.AUTO) / len(results)


def autonomous_error_rate(results: Sequence[CaseResult]) -> float:
    """Of the actions taken autonomously, how many were wrong.

    Zero automated actions means zero autonomous risk, so the rate is 0.0 — read
    it alongside coverage, which will also be 0.0.
    """
    automated = [r for r in results if r.actual is Action.AUTO]
    if not automated:
        return 0.0
    return sum(1 for r in automated if not r.passed) / len(automated)


def rate_of(results: Sequence[CaseResult], action: Action) -> float:
    if not results:
        return 0.0
    return sum(1 for r in results if r.actual is action) / len(results)


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile. `q` in [0, 1]."""
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    index = min(int(round(q * (len(clean) - 1))), len(clean) - 1)
    return clean[index]


def brier_score(probabilities: Sequence[float], outcomes: Sequence[bool]) -> float:
    """Mean squared error of probabilistic judgments. Lower is better.

    This is the primary judge metric in Phase 6. A judge that is accurate but
    always says 0.95 scores worse than one that is equally accurate and honest
    about hard cases — which is exactly the difference the policy thresholds
    depend on.
    """
    if len(probabilities) != len(outcomes):
        raise ValueError("probabilities and outcomes must be the same length")
    if not probabilities:
        raise ValueError("cannot score an empty set of judgments")
    return sum((p - float(o)) ** 2 for p, o in zip(probabilities, outcomes, strict=True)) / len(
        probabilities
    )


def suite_metrics(
    results: Sequence[CaseResult],
    latencies: Sequence[float] | None = None,
    costs: Sequence[float] | None = None,
) -> SuiteMetrics:
    latencies = [v for v in (latencies or []) if v is not None]
    costs = [v for v in (costs or []) if v is not None]
    return SuiteMetrics(
        task_correctness=accuracy(results),
        automation_coverage=automation_coverage(results),
        autonomous_error_rate=autonomous_error_rate(results),
        human_review_rate=rate_of(results, Action.REVIEW),
        reject_rate=rate_of(results, Action.REJECT),
        latency_p50_ms=percentile(latencies, 0.50),
        latency_p95_ms=percentile(latencies, 0.95),
        total_cost_usd=round(sum(costs), 6) if costs else None,
    )
