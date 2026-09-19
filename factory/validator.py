"""Validation: gather evidence. Never ask a model whether the code looks right.

Stages, in order, each one cheaper than the one after it:

    static checks -> unit tests -> target case -> full product eval -> regressions

Every number here comes from a subprocess exit code or a JSON file written by the
evaluator. The validator shells out to the evaluator rather than importing it, so
the process that grades the work is not the process that produced it.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import time

from factory import git
from factory.paths import REPO_ROOT, RESULTS_DIR
from factory.schemas import (
    BenchmarkCount,
    BenchmarkEvidence,
    BuildResult,
    CommandResult,
    ScopeGuard,
    TargetCaseEvidence,
    UnitTestEvidence,
    ValidationResult,
    WorkItem,
)

TAIL = 2000
TIMEOUT_SECONDS = 600

AGENT_COMMAND = ["uv", "run", "python", "scripts/run_agent.py", "--out"]
EVAL_COMMAND = ["uv", "run", "python", "-m", "evals.accounting_eval"]


def run_command(command: list[str] | str, label: str | None = None) -> CommandResult:
    shell = isinstance(command, str)
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        shell=shell,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    return CommandResult(
        command=label or (command if shell else " ".join(command)),
        exit_code=completed.returncode,
        duration_seconds=round(time.monotonic() - started, 3),
        stdout_tail=completed.stdout[-TAIL:],
        stderr_tail=completed.stderr[-TAIL:],
    )


# --- stages --------------------------------------------------------------


def static_checks(changed: list[str]) -> list[CommandResult]:
    """Syntax first, then lint. A file that will not compile fails fastest."""
    python_files = [p for p in changed if p.endswith(".py") and (REPO_ROOT / p).exists()]
    if not python_files:
        return []
    return [
        run_command(["uv", "run", "python", "-m", "compileall", "-q", *python_files]),
        run_command(["uv", "run", "ruff", "check", *python_files]),
    ]


def unit_tests() -> UnitTestEvidence:
    result = run_command(["uv", "run", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"])
    output = result.stdout_tail + result.stderr_tail
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", output)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", output)) else 0
    if failed == 0 and re.search(r"(\d+) error", output):
        # Collection errors are failures even though pytest words them differently.
        failed = int(re.search(r"(\d+) error", output).group(1))
    return UnitTestEvidence(passed=passed, failed=failed, exit_code=result.exit_code)


def product_eval(label: str, against: pathlib.Path | None = None) -> tuple[dict, pathlib.Path]:
    """Run the agent over the benchmark, then grade the run it produced.

    Returns the evaluator's JSON payload and the path to the run file.
    """
    runs_dir = RESULTS_DIR / "runs"
    run_path = runs_dir / f"{label}.jsonl"
    json_path = RESULTS_DIR / "eval" / f"{label}.json"

    agent = run_command([*AGENT_COMMAND, str(run_path.relative_to(REPO_ROOT))])
    if not agent.ok:
        raise ValidationError(f"agent run failed:\n{agent.stderr_tail or agent.stdout_tail}")

    command = [*EVAL_COMMAND, str(run_path.relative_to(REPO_ROOT))]
    if against:
        command += ["--against", str(against.relative_to(REPO_ROOT))]
    command += ["--json", str(json_path.relative_to(REPO_ROOT))]

    evaluation = run_command(command)
    if not evaluation.ok:
        raise ValidationError(
            f"product eval failed:\n{evaluation.stderr_tail or evaluation.stdout_tail}"
        )
    return json.loads(json_path.read_text()), run_path


class ValidationError(RuntimeError):
    pass


def _case_passed(payload: dict, case_id: str) -> bool:
    for result in payload["suite"]["results"]:
        if result["case_id"] == case_id:
            return bool(result["passed"])
    raise ValidationError(f"case {case_id} is not in the evaluated run")


# --- the validator -------------------------------------------------------


def validate(
    item: WorkItem,
    build: BuildResult,
    baseline: dict,
    baseline_run: pathlib.Path,
    label: str,
) -> ValidationResult:
    """Run every stage. Stop at the first one that makes later stages meaningless."""
    result = ValidationResult()

    # Scope, from the diff rather than from the builder's self-report.
    changed = git.changed_paths()
    result.scope_violations = ScopeGuard(item.scope).violations(changed)
    result.stage_reached = "scope"
    if result.scope_violations:
        result.error = "build touched paths outside the allowed scope"
        return result

    result.static_checks = static_checks(changed)
    result.stage_reached = "static_checks"
    if not result.static_ok:
        result.error = "static checks failed"
        return result

    result.unit_tests = unit_tests()
    result.stage_reached = "unit_tests"
    if not result.unit_tests.ok:
        result.error = f"{result.unit_tests.failed} unit test(s) failing"
        return result

    try:
        after, _ = product_eval(label, against=baseline_run)
    except ValidationError as exc:
        result.stage_reached = "product_eval"
        result.error = str(exc)
        return result

    result.stage_reached = "product_eval"
    result.benchmark = BenchmarkEvidence(
        before=BenchmarkCount(passed=baseline["suite"]["passed"], total=baseline["suite"]["total"]),
        after=BenchmarkCount(passed=after["suite"]["passed"], total=after["suite"]["total"]),
    )

    if item.target_case_id:
        result.target_case = TargetCaseEvidence(
            case=item.target_case_id,
            before=_case_passed(baseline, item.target_case_id),
            after=_case_passed(after, item.target_case_id),
        )

    comparison = after.get("comparison") or {}
    result.regressions = list(comparison.get("newly_failing", []))
    result.newly_passing = list(comparison.get("newly_passing", []))
    result.stage_reached = "regressions"

    # The work item's own declared commands, executed verbatim. They are a
    # contract check, not the gate: the numbers above are the gate.
    result.declared_commands = [run_command(c) for c in item.verification.commands]
    result.stage_reached = "declared_commands"

    return result
