"""The orchestrator: runs the state machine and makes the final decision.

The reviewer model advises. This module decides, in ordinary Python, from evidence:

    models provide judgment
    code provides authority

Every gate below can veto a change on its own. A green reviewer cannot rescue a
failing test, and passing tests cannot rescue a scope violation.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import time

from factory import builder, context, git, intake, planner, reviewer, validator
from factory.paths import REPO_ROOT
from factory.schemas import (
    Decision,
    Plan,
    Review,
    RunMetadata,
    State,
    ValidationResult,
    WorkItem,
)
from factory.trace import Trace


class FactoryError(RuntimeError):
    """A run could not be completed. Distinct from a run that completed in REJECT."""


def decide(
    item: WorkItem,
    validation: ValidationResult,
    review: Review | None,
) -> Decision:
    """The gate. Ordered so the most fundamental objection is reported first."""
    target = validation.target_case
    gates = {
        "scope_respected": not validation.scope_violations,
        "static_checks_pass": validation.static_ok,
        "unit_tests_pass": bool(validation.unit_tests and validation.unit_tests.ok),
        "target_case_passes": bool(target and target.after),
        "within_regression_policy": (
            len(validation.regressions) <= item.regression_policy.max_new_failures
        ),
        "declared_commands_pass": validation.declared_ok,
        "reviewer_accepts": bool(review and review.decision == "ACCEPT"),
    }

    reasons: list[str] = []
    if not gates["scope_respected"]:
        reasons.append(
            "touched paths outside the allowed scope: " + ", ".join(validation.scope_violations)
        )
    if not gates["static_checks_pass"]:
        reasons.append("static checks failed")
    if not gates["unit_tests_pass"]:
        failed = validation.unit_tests.failed if validation.unit_tests else "?"
        reasons.append(f"{failed} unit test(s) failing")
    if not gates["target_case_passes"]:
        reasons.append(
            f"target case {target.case} still fails" if target else "no target case evidence"
        )
    if not gates["within_regression_policy"]:
        reasons.append(
            f"{len(validation.regressions)} regression(s) against a policy of "
            f"{item.regression_policy.max_new_failures}: " + ", ".join(validation.regressions)
        )
    if not gates["declared_commands_pass"]:
        failing = [c.command for c in validation.declared_commands if not c.ok]
        reasons.append("declared verification command(s) failed: " + ", ".join(failing))
    if not gates["reviewer_accepts"]:
        reasons.append("reviewer did not accept" + (f": {review.summary}" if review else ""))

    accepted = all(gates.values())
    if accepted:
        state = State.ACCEPTED
    elif not gates["scope_respected"]:
        state = State.REJECTED_SCOPE
    elif not gates["within_regression_policy"]:
        state = State.REJECTED_REGRESSION
    elif not gates["reviewer_accepts"] and gates["unit_tests_pass"]:
        state = State.REJECTED_REVIEW
    else:
        state = State.FAILED_VALIDATION

    return Decision(accepted=accepted, state=state, gates=gates, blocking_reasons=reasons)


class FactoryRun:
    """One pass through the loop, with its own trace directory."""

    def __init__(
        self,
        task_path: pathlib.Path,
        dry_run: bool = False,
        keep_on_reject: bool = False,
        require_clean_tree: bool = True,
    ) -> None:
        self.task_path = task_path
        self.dry_run = dry_run
        self.keep_on_reject = keep_on_reject
        self.require_clean_tree = require_clean_tree

        self.states: list[State] = []
        self.item: WorkItem | None = None
        self.plan: Plan | None = None
        self.validation: ValidationResult | None = None
        self.review: Review | None = None
        self.decision: Decision | None = None
        self.trace: Trace | None = None
        self.started = time.monotonic()

    # --- state machine ---------------------------------------------------

    def enter(self, state: State) -> None:
        self.states.append(state)
        print(f"  [{state}]")

    def fail(self, state: State, message: str) -> FactoryError:
        self.enter(state)
        if self.trace:
            self.trace.write_json(
                "result.json",
                {
                    "run_id": self.trace.run_id,
                    "accepted": False,
                    "state": str(state),
                    "error": message,
                    "states": [str(s) for s in self.states],
                },
            )
            self._finish_metadata(state)
        return FactoryError(message)

    # --- the loop --------------------------------------------------------

    def execute(self) -> Decision:
        item, run_id, baseline_sha = intake.intake(
            self.task_path, require_clean_tree=self.require_clean_tree
        )
        self.item = item
        self.trace = Trace(run_id)
        self.trace.copy_in("task.yaml", self.task_path)
        self.metadata = RunMetadata(
            run_id=run_id,
            task_id=item.id,
            git_sha_before=baseline_sha,
            planner_model=planner.MODEL,
            builder_model=builder.MODEL,
            reviewer_model=reviewer.MODEL,
            started_at=dt.datetime.now(dt.UTC).isoformat(),
        )
        print(f"run {run_id}  task {item.id}  baseline {baseline_sha[:10]}")
        self.enter(State.CREATED)

        # --- context -----------------------------------------------------
        try:
            package = context.resolve(item)
        except context.ContextError as exc:
            raise self.fail(State.FAILED_CONTEXT, str(exc)) from exc
        self.trace.write_model("context.json", package)
        self.enter(State.CONTEXT_READY)

        # Baseline evidence must be captured before the tree changes.
        try:
            baseline, baseline_run = validator.product_eval(f"{run_id}-before")
        except validator.ValidationError as exc:
            raise self.fail(State.FAILED_VALIDATION, f"baseline eval failed: {exc}") from exc
        print(
            f"  baseline {baseline['suite']['passed']}/{baseline['suite']['total']}"
            f"  target {item.target_case_id}="
            f"{'PASS' if _passed(baseline, item.target_case_id) else 'FAIL'}"
        )

        # --- plan --------------------------------------------------------
        try:
            self.plan = planner.plan(item, package)
        except planner.PlanError as exc:
            raise self.fail(State.FAILED_PLAN, str(exc)) from exc

        violations = planner.check_plan(self.plan, item)
        if violations:
            self.trace.write_model("plan.json", self.plan)
            raise self.fail(State.FAILED_PLAN, "; ".join(violations))

        self.trace.write_model("plan.json", self.plan)
        self.enter(State.PLANNED)

        if self.dry_run:
            print("  dry run: stopping after planning")
            self.decision = Decision(
                accepted=False, state=State.PLANNED, gates={}, blocking_reasons=["dry run"]
            )
            self.trace.write_model("result.json", self.decision)
            self._finish_metadata(State.PLANNED)
            return self.decision

        # --- build -------------------------------------------------------
        try:
            build = builder.build(item, self.plan)
        except builder.BuildError as exc:
            raise self.fail(State.FAILED_BUILD, str(exc)) from exc
        self.trace.write_model("builder.json", build)
        diff = git.write_patch(self.trace.dir / "diff.patch")
        if not diff.strip():
            raise self.fail(State.FAILED_BUILD, "builder produced no diff")
        self.enter(State.BUILT)

        # --- validate ----------------------------------------------------
        self.validation = validator.validate(
            item, build, baseline, baseline_run, label=f"{run_id}-after"
        )
        self.trace.write_model("validation.json", self.validation)
        if self.validation.error and self.validation.stage_reached in {
            "static_checks",
            "unit_tests",
        }:
            print(
                f"  validation stopped at {self.validation.stage_reached}: {self.validation.error}"
            )
        self.enter(State.VALIDATED)

        # --- review ------------------------------------------------------
        self.review = reviewer.review(item, self.plan, build, self.validation, diff)
        self.trace.write_model("review.json", self.review)
        self.enter(State.REVIEWED)

        # --- decide ------------------------------------------------------
        self.decision = decide(item, self.validation, self.review)
        self.enter(self.decision.state)
        self.trace.write_model("result.json", self.decision)

        if not self.decision.accepted and not self.keep_on_reject:
            git.revert(build.changed_files, build.created_files)
            print("  reverted the rejected change; the patch is preserved in the trace")

        self.metadata.git_sha_after = git.head_sha()
        self._finish_metadata(self.decision.state)
        return self.decision

    def _finish_metadata(self, state: State) -> None:
        assert self.trace is not None
        self.metadata.finished_at = dt.datetime.now(dt.UTC).isoformat()
        self.metadata.duration_seconds = round(time.monotonic() - self.started, 2)
        self.metadata.states = [str(s) for s in self.states]
        self.trace.write_model("metadata.json", self.metadata)


def _passed(payload: dict, case_id: str | None) -> bool:
    if not case_id:
        return False
    return any(r["case_id"] == case_id and r["passed"] for r in payload["suite"]["results"])


def run_factory(
    task_path: pathlib.Path,
    dry_run: bool = False,
    keep_on_reject: bool = False,
    require_clean_tree: bool = True,
) -> tuple[Decision, Trace]:
    run = FactoryRun(
        task_path,
        dry_run=dry_run,
        keep_on_reject=keep_on_reject,
        require_clean_tree=require_clean_tree,
    )
    decision = run.execute()
    assert run.trace is not None
    return decision, run.trace


def format_decision(decision: Decision, trace: Trace, validation: ValidationResult | None) -> str:
    lines = ["", "=" * 68]
    verdict = "ACCEPT" if decision.accepted else f"REJECT ({decision.state})"
    lines.append(f"  {verdict}")
    lines.append("=" * 68)

    if validation and validation.benchmark:
        b = validation.benchmark
        before = f"{b.before.passed}/{b.before.total}"
        after = f"{b.after.passed}/{b.after.total}"
        lines.append(f"  benchmark      {before} -> {after}")
    if validation and validation.target_case:
        t = validation.target_case
        arrow = f"{'PASS' if t.before else 'FAIL'} -> {'PASS' if t.after else 'FAIL'}"
        lines.append(f"  target case    {t.case}  {arrow}")
    if validation and validation.unit_tests:
        lines.append(
            f"  unit tests     {validation.unit_tests.passed} passed, "
            f"{validation.unit_tests.failed} failed"
        )
    if validation:
        lines.append(f"  regressions    {', '.join(validation.regressions) or '(none)'}")
        lines.append(f"  newly passing  {', '.join(validation.newly_passing) or '(none)'}")

    for name, ok in decision.gates.items():
        lines.append(f"    {'PASS' if ok else 'FAIL'}  {name}")
    for reason in decision.blocking_reasons:
        lines.append(f"  ! {reason}")

    lines.append(f"  trace          {trace.dir.relative_to(REPO_ROOT)}")
    return "\n".join(lines)
