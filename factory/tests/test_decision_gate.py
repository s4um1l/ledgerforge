"""The gate is the whole thesis: code decides, the model advises.

Each gate must be able to veto on its own, and a green reviewer must never be
able to rescue a failing one.
"""

import pytest

from factory.orchestrator import decide
from factory.schemas import (
    BenchmarkCount,
    BenchmarkEvidence,
    BusinessImpact,
    CommandResult,
    Problem,
    RegressionPolicy,
    Review,
    ReviewCriteria,
    Scope,
    Source,
    State,
    TargetCaseEvidence,
    UnitTestEvidence,
    ValidationResult,
    Verification,
    WorkItem,
)


def work_item(max_new_failures: int = 0) -> WorkItem:
    return WorkItem(
        id="ACCT-001",
        title="Enforce invoice tolerance policy",
        source=Source(type="eval_failure", case_id="R07"),
        problem=Problem(
            summary="overbill auto-approved",
            actual_behavior="AUTO",
            expected_behavior="REVIEW",
        ),
        business_impact=BusinessImpact(severity="high"),
        intent="Prevent invoices outside tolerance from auto-approving.",
        scope=Scope(
            allowed_paths=["product/accounting_agent/controls/**"],
            forbidden_paths=["benchmark/gold/**"],
        ),
        acceptance_criteria=["R07 must pass"],
        verification=Verification(commands=["uv run pytest product/tests"]),
        regression_policy=RegressionPolicy(max_new_failures=max_new_failures),
    )


def clean_validation(**overrides) -> ValidationResult:
    result = ValidationResult(
        static_checks=[CommandResult(command="ruff check", exit_code=0, duration_seconds=0.1)],
        unit_tests=UnitTestEvidence(passed=46, failed=0, exit_code=0),
        target_case=TargetCaseEvidence(case="R07", before=False, after=True),
        benchmark=BenchmarkEvidence(
            before=BenchmarkCount(passed=24, total=30),
            after=BenchmarkCount(passed=25, total=30),
        ),
        regressions=[],
        newly_passing=["R07"],
        declared_commands=[
            CommandResult(command="uv run pytest product/tests", exit_code=0, duration_seconds=1.0)
        ],
        stage_reached="declared_commands",
    )
    for key, value in overrides.items():
        setattr(result, key, value)
    return result


def accepting_review() -> Review:
    return Review(
        decision="ACCEPT",
        criteria=ReviewCriteria(
            scope_respected=True, acceptance_met=True, tests_pass=True, no_regressions=True
        ),
        summary="looks right",
    )


def rejecting_review() -> Review:
    return Review(
        decision="REJECT",
        criteria=ReviewCriteria(
            scope_respected=True, acceptance_met=True, tests_pass=True, no_regressions=True
        ),
        concerns=["this is more complexity than the problem deserves"],
        summary="unnecessary abstraction",
    )


def test_clean_run_is_accepted():
    decision = decide(work_item(), clean_validation(), accepting_review())
    assert decision.accepted
    assert decision.state is State.ACCEPTED
    assert decision.blocking_reasons == []
    assert all(decision.gates.values())


def test_scope_violation_vetoes_everything_else():
    decision = decide(
        work_item(), clean_validation(scope_violations=["evals/metrics.py"]), accepting_review()
    )
    assert not decision.accepted
    assert decision.state is State.REJECTED_SCOPE


def test_failing_unit_tests_veto():
    validation = clean_validation(unit_tests=UnitTestEvidence(passed=45, failed=1, exit_code=1))
    decision = decide(work_item(), validation, accepting_review())
    assert not decision.accepted
    assert "1 unit test(s) failing" in " ".join(decision.blocking_reasons)


def test_unfixed_target_case_vetoes():
    validation = clean_validation(
        target_case=TargetCaseEvidence(case="R07", before=False, after=False)
    )
    decision = decide(work_item(), validation, accepting_review())
    assert not decision.accepted
    assert "target case R07 still fails" in " ".join(decision.blocking_reasons)


def test_regression_vetoes_even_when_the_target_case_is_fixed():
    """A change can be right about its own goal and still unacceptable."""
    decision = decide(work_item(), clean_validation(regressions=["R06"]), accepting_review())
    assert not decision.accepted
    assert decision.state is State.REJECTED_REGRESSION


def test_regression_policy_can_permit_a_known_cost():
    decision = decide(
        work_item(max_new_failures=1), clean_validation(regressions=["R06"]), accepting_review()
    )
    assert decision.accepted


def test_reviewer_can_veto_a_technically_green_change():
    """Judgment still has authority to stop, just never to force through."""
    decision = decide(work_item(), clean_validation(), rejecting_review())
    assert not decision.accepted
    assert decision.state is State.REJECTED_REVIEW


def test_reviewer_cannot_rescue_a_failing_gate():
    validation = clean_validation(unit_tests=UnitTestEvidence(passed=0, failed=3, exit_code=1))
    decision = decide(work_item(), validation, accepting_review())
    assert not decision.accepted


def test_missing_review_is_not_an_acceptance():
    decision = decide(work_item(), clean_validation(), None)
    assert not decision.accepted


def test_failing_declared_command_vetoes():
    validation = clean_validation(
        declared_commands=[
            CommandResult(command="uv run pytest product/tests", exit_code=1, duration_seconds=1.0)
        ]
    )
    decision = decide(work_item(), validation, accepting_review())
    assert not decision.accepted


@pytest.mark.parametrize(
    "gate",
    [
        "scope_respected",
        "static_checks_pass",
        "unit_tests_pass",
        "target_case_passes",
        "within_regression_policy",
        "declared_commands_pass",
        "reviewer_accepts",
    ],
)
def test_every_gate_is_reported(gate):
    decision = decide(work_item(), clean_validation(), accepting_review())
    assert gate in decision.gates
