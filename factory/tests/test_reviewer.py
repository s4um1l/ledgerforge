"""The reviewer's job is to notice things the numbers do not show."""

from factory.reviewer import review
from factory.schemas import BuildResult, Plan
from factory.tests.test_decision_gate import clean_validation, work_item

PLAN = Plan(
    understanding="u",
    root_cause_hypothesis="r",
    files_to_modify=["product/accounting_agent/controls/tolerance.py"],
    steps=["add the control"],
    smallest_change_rationale="one module, no callers touched",
)

BUILD = BuildResult(
    changed_files=["product/accounting_agent/controls/tolerance.py"],
    summary="Added the tolerance control.",
    tests_added=["product/tests/test_tolerance_control.py"],
)

CLEAN_DIFF = "+def check(case_input, proposed):\n+    return None\n"


def test_accepts_a_clean_change():
    result = review(work_item(), PLAN, BUILD, clean_validation(), CLEAN_DIFF)
    assert result.decision == "ACCEPT"
    assert result.concerns == []


def test_rejects_a_diff_that_skips_a_test():
    diff = CLEAN_DIFF + '+@pytest.mark.skip(reason="flaky")\n'
    result = review(work_item(), PLAN, BUILD, clean_validation(), diff)
    assert result.decision == "REJECT"
    assert any("weakens verification" in c for c in result.concerns)


def test_rejects_a_regression():
    result = review(work_item(), PLAN, BUILD, clean_validation(regressions=["R06"]), CLEAN_DIFF)
    assert result.decision == "REJECT"
    assert not result.criteria.no_regressions


def test_flags_a_change_with_no_tests_for_an_observed_failure():
    build = BuildResult(changed_files=BUILD.changed_files, summary="x", tests_added=[])
    result = review(work_item(), PLAN, build, clean_validation(), CLEAN_DIFF)
    assert any("no tests were added" in c for c in result.concerns)


def test_flags_files_the_plan_never_mentioned():
    """In scope but unplanned is still worth a human's attention."""
    build = BuildResult(
        changed_files=[
            "product/accounting_agent/controls/tolerance.py",
            "product/accounting_agent/controls/cutoff.py",
        ],
        summary="x",
        tests_added=["product/tests/test_tolerance_control.py"],
    )
    result = review(work_item(), PLAN, build, clean_validation(), CLEAN_DIFF)
    assert any("the plan did not name" in c for c in result.concerns)


def test_flags_a_target_case_that_was_never_broken():
    """If the case passed before the change, the work item described nothing."""
    from factory.schemas import TargetCaseEvidence

    validation = clean_validation(
        target_case=TargetCaseEvidence(case="R07", before=True, after=True)
    )
    result = review(work_item(), PLAN, BUILD, validation, CLEAN_DIFF)
    assert any("already passed before" in c for c in result.concerns)
