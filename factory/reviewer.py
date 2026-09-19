"""Reviewer: reads the task, the plan, the diff and the evidence. Advises only.

Phase 2's reviewer is deterministic. It cannot form an opinion about whether code
is *good* — that is exactly what Phase 3's model is for — but it can check the
things that are checkable, which is most of what a review is: did the change stay
in scope, did it demonstrate its acceptance criteria, did it weaken the tests, did
anything regress.

Its verdict is advice. `factory.orchestrator` decides.
"""

from __future__ import annotations

import json
import os

from factory import llm
from factory.paths import PROMPTS_DIR
from factory.schemas import (
    BuildResult,
    Plan,
    Review,
    ReviewCriteria,
    ValidationResult,
    WorkItem,
)

SCRIPTED_MODEL = "fake:deterministic-reviewer"
DEFAULT_BACKEND = os.environ.get("FACTORY_REVIEWER", "scripted")

last_call: llm.ModelCall | None = None

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


def review_scripted(
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


MAX_DIFF_CHARS = 60_000


def _prompt(
    item: WorkItem,
    plan: Plan,
    build: BuildResult,
    validation: ValidationResult,
    diff: str,
) -> str:
    """The task, the plan, the diff and the evidence. No answers."""
    evidence = validation.model_dump(mode="json")
    # The declared commands' output is noise for a reviewer and can be long.
    for entry in evidence.get("declared_commands", []) + evidence.get("static_checks", []):
        entry.pop("stdout_tail", None)
        entry.pop("stderr_tail", None)

    truncated = len(diff) > MAX_DIFF_CHARS
    lines = [
        f"# Work item {item.id}: {item.title}",
        "",
        f"**Intent.** {item.intent}",
        "",
        f"**Observed.** {item.problem.summary}",
        "",
        "**Acceptance criteria.**",
        *[f"- {c}" for c in item.acceptance_criteria],
        "",
        "**Paths the change was allowed to touch.**",
        *[f"- `{p}`" for p in item.scope.allowed_paths],
        "",
        f"**Regression policy.** At most {item.regression_policy.max_new_failures} "
        "newly failing case(s).",
        "",
        "## The plan the builder worked from",
        "",
        "```json",
        plan.model_dump_json(indent=2),
        "```",
        "",
        "## What the builder says it did",
        "",
        "```json",
        build.model_dump_json(indent=2),
        "```",
        "",
        "This is the builder's own account. The diff below is what actually happened.",
        "",
        "## The diff",
        "",
        "```diff",
        diff[:MAX_DIFF_CHARS],
        "```",
    ]
    if truncated:
        lines.append(
            f"\n**The diff was truncated at {MAX_DIFF_CHARS:,} characters.** Treat an "
            "unreviewably large diff as a finding in itself."
        )

    lines += [
        "",
        "## Validation evidence",
        "",
        "```json",
        json.dumps(evidence, indent=2),
        "```",
    ]
    return "\n".join(lines)


def review_with_api(
    item: WorkItem,
    plan: Plan,
    build: BuildResult,
    validation: ValidationResult,
    diff: str,
) -> Review:
    global last_call
    system = (PROMPTS_DIR / "reviewer.md").read_text()
    result, call = llm.run_structured(
        _prompt(item, plan, build, validation, diff),
        Review,
        system=system,
        model=llm.DEFAULT_REVIEWER_MODEL,
    )
    last_call = call
    print(
        f"  reviewer: {call.duration_seconds}s, "
        f"${call.cost_usd:.4f} list-price equivalent ({call.model})"
    )
    return result


BACKENDS = {
    "scripted": review_scripted,
    "api": review_with_api,
}

MODELS = {
    "scripted": SCRIPTED_MODEL,
    "api": llm.DEFAULT_REVIEWER_MODEL,
}

MODEL = MODELS[DEFAULT_BACKEND]


def review(
    item: WorkItem,
    plan: Plan,
    build: BuildResult,
    validation: ValidationResult,
    diff: str,
    backend: str | None = None,
) -> Review:
    name = backend or DEFAULT_BACKEND
    if name not in BACKENDS:
        raise RuntimeError(f"unknown reviewer backend {name!r}; have {', '.join(BACKENDS)}")
    return BACKENDS[name](item, plan, build, validation, diff)
