"""Reviewer: reads the task, the plan, the diff and the evidence. Advises only.

Phase 2's reviewer is deterministic. It cannot form an opinion about whether code
is *good* — that is exactly what Phase 3's model is for — but it can check the
things that are checkable, which is most of what a review is: did the change stay
in scope, did it demonstrate its acceptance criteria, did it weaken the tests, did
anything regress.

Its verdict is advice. `factory.orchestrator` decides.
"""

from __future__ import annotations

from factory.schemas import (
    BuildResult,
    Plan,
    Review,
    ReviewCriteria,
    ValidationResult,
    WorkItem,
)

MODEL = "fake:deterministic-reviewer"

# Phrases in a diff that suggest the builder made the evidence easier instead of
# the code better.
WEAKENING_MARKERS = (
    "@pytest.mark.skip",
    "pytest.skip(",
    "# type: ignore",
    "noqa: F",
    "assert True",
    "xfail",
)


def review(
    item: WorkItem,
    plan: Plan,
    build: BuildResult,
    validation: ValidationResult,
    diff: str,
) -> Review:
    concerns: list[str] = []

    scope_respected = not validation.scope_violations
    if not scope_respected:
        concerns.append(
            "change touched paths outside the allowed scope: "
            + ", ".join(validation.scope_violations)
        )

    tests_pass = bool(validation.unit_tests and validation.unit_tests.ok)
    if not tests_pass:
        concerns.append("unit tests are not green")

    no_regressions = len(validation.regressions) <= item.regression_policy.max_new_failures
    if validation.regressions:
        concerns.append("regressions: " + ", ".join(validation.regressions))

    target = validation.target_case
    acceptance_met = bool(target and target.after)
    if target and not target.after:
        concerns.append(f"target case {target.case} still fails")
    if target and target.before and target.after:
        concerns.append(
            f"target case {target.case} already passed before the change; "
            "the work item may not describe a real failure"
        )

    if not build.tests_added and item.source.type == "eval_failure":
        concerns.append("no tests were added for a change motivated by an observed failure")

    weakened = sorted({m for m in WEAKENING_MARKERS if m in diff})
    if weakened:
        concerns.append("diff weakens verification: " + ", ".join(weakened))

    # A change far larger than the plan admitted is worth a human's attention even
    # when every number is green.
    unplanned = sorted(set(build.changed_files) - set(plan.files_to_modify))
    if unplanned:
        concerns.append("changed files the plan did not name: " + ", ".join(unplanned))

    decision = (
        "ACCEPT"
        if scope_respected and tests_pass and no_regressions and acceptance_met and not weakened
        else "REJECT"
    )

    if decision == "ACCEPT":
        summary = (
            f"{build.summary} Scope respected across {len(build.changed_files)} file(s); "
            f"{validation.unit_tests.passed} unit tests green; "
            f"target case {target.case if target else 'n/a'} fixed; no regressions."
        )
    else:
        summary = "Rejected: " + "; ".join(concerns)

    return Review(
        decision=decision,
        criteria=ReviewCriteria(
            scope_respected=scope_respected,
            acceptance_met=acceptance_met,
            tests_pass=tests_pass,
            no_regressions=no_regressions,
        ),
        concerns=concerns,
        summary=summary,
    )
