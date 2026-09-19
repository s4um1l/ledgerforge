import pytest

from evals.accounting_eval import compare_runs, evaluate_case, evaluate_suite
from evals.gold import load_gold
from evals.loaders import load_cases, load_run
from evals.paths import FIXTURES_DIR
from evals.schemas import Action, GoldAnswer, JudgmentLabels, RunRecord

LABELS = JudgmentLabels(
    evidence_sufficient=True,
    sources_consistent=True,
    candidate_supported=True,
    possible_duplicate=False,
    requires_human_review=False,
)


def gold(case_id: str, action: Action) -> GoldAnswer:
    return GoldAnswer(case_id=case_id, gold_action=action, labels=LABELS)


def test_evaluate_case_exact_match():
    passed = evaluate_case(RunRecord(case_id="R01", action=Action.AUTO), gold("R01", Action.AUTO))
    failed = evaluate_case(RunRecord(case_id="R07", action=Action.AUTO), gold("R07", Action.REVIEW))
    assert passed.passed is True
    assert failed.passed is False
    assert failed.expected is Action.REVIEW and failed.actual is Action.AUTO


def test_evaluate_case_refuses_mismatched_ids():
    with pytest.raises(ValueError, match="graded against gold"):
        evaluate_case(RunRecord(case_id="R01", action=Action.AUTO), gold("R02", Action.AUTO))


def test_action_accepts_longer_spellings_from_fixtures():
    assert Action("AUTO_APPROVE") is Action.AUTO
    assert Action("human_review") is Action.REVIEW


def test_baseline_fixture_scores_24_of_31():
    """The Phase 1 gate: a real number out of the evaluator, with no model involved."""
    suite = evaluate_suite(
        load_run(FIXTURES_DIR / "fake_run_baseline.jsonl"),
        load_gold(),
        load_cases(),
        label="baseline",
    )
    assert (suite.passed, suite.total) == (24, 31)
    assert {r.case_id for r in suite.failures} == {
        "R03", "R07", "D05", "V02", "S03", "S06", "R09",
    }
    # Every failure is the same shape: automated when a human was required.
    assert all(r.actual is Action.AUTO for r in suite.failures)


def test_incomplete_run_is_an_error_not_a_higher_score():
    records = load_run(FIXTURES_DIR / "fake_run_baseline.jsonl")
    trimmed = [r for r in records if r.case_id not in {"R07", "D05"}]
    with pytest.raises(ValueError, match="missing 2 case"):
        evaluate_suite(trimmed, load_gold(), load_cases())

    suite = evaluate_suite(trimmed, load_gold(), load_cases(), require_complete=False)
    assert suite.total == 29


def test_unknown_case_is_rejected():
    with pytest.raises(ValueError, match="no gold answer"):
        evaluate_suite(
            [RunRecord(case_id="NOPE", action=Action.AUTO)],
            load_gold(),
            load_cases(),
            require_complete=False,
        )


def _suite(name: str):
    return evaluate_suite(
        load_run(FIXTURES_DIR / f"fake_run_{name}.jsonl"),
        load_gold(),
        load_cases(),
        label=name,
    )


def test_compare_runs_reports_improvement_without_regressions():
    cmp = compare_runs(_suite("baseline"), _suite("patched"))
    assert (cmp.before_passed, cmp.after_passed) == (24, 27)
    assert cmp.newly_passing == ["D05", "R07", "V02"]
    assert cmp.regressions == []
    assert cmp.improved is True


def test_compare_runs_catches_a_regression_even_when_the_target_case_is_fixed():
    """The case the factory must reject: R07 fixed, two neighbours broken."""
    cmp = compare_runs(_suite("baseline"), _suite("regressed"))
    assert "R07" in cmp.newly_passing
    assert cmp.regressions == ["D06", "R02"]
    assert cmp.improved is False
