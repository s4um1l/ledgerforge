import pytest

from evals.metrics import (
    accuracy,
    automation_coverage,
    autonomous_error_rate,
    brier_score,
    percentile,
)
from evals.schemas import Action, CaseResult


def result(case_id: str, expected: Action, actual: Action) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        category="test",
        expected=expected,
        actual=actual,
        passed=expected is actual,
    )


def test_accuracy_counts_passes():
    results = [
        result("A", Action.AUTO, Action.AUTO),
        result("B", Action.REVIEW, Action.AUTO),
    ]
    assert accuracy(results) == 0.5


def test_empty_suite_scores_zero_rather_than_dividing_by_zero():
    assert accuracy([]) == 0.0
    assert automation_coverage([]) == 0.0
    assert autonomous_error_rate([]) == 0.0


def test_autonomous_error_rate_is_over_automated_actions_only():
    # Three AUTO, one of them wrong; the wrong REVIEW must not count.
    results = [
        result("A", Action.AUTO, Action.AUTO),
        result("B", Action.AUTO, Action.AUTO),
        result("C", Action.REVIEW, Action.AUTO),
        result("D", Action.AUTO, Action.REVIEW),
    ]
    assert autonomous_error_rate(results) == pytest.approx(1 / 3)
    assert automation_coverage(results) == 0.75


def test_a_system_that_automates_nothing_has_no_autonomous_risk():
    results = [result("A", Action.AUTO, Action.REVIEW) for _ in range(5)]
    assert autonomous_error_rate(results) == 0.0
    assert automation_coverage(results) == 0.0


def test_percentile_nearest_rank():
    assert percentile([10, 20, 30, 40], 0.0) == 10
    assert percentile([10, 20, 30, 40], 1.0) == 40
    assert percentile([5], 0.5) == 5
    assert percentile([], 0.5) is None


def test_brier_score_rewards_calibration():
    perfect = brier_score([1.0, 0.0], [True, False])
    hedged = brier_score([0.5, 0.5], [True, False])
    confident_and_wrong = brier_score([0.0, 1.0], [True, False])
    assert perfect == 0.0
    assert hedged == 0.25
    assert confident_and_wrong == 1.0
    assert perfect < hedged < confident_and_wrong


def test_brier_score_rejects_bad_input():
    with pytest.raises(ValueError):
        brier_score([0.5], [True, False])
    with pytest.raises(ValueError):
        brier_score([], [])
