"""Intake: turn a YAML file into a validated work item and a run identity.

No model is involved. If a work item cannot be trusted, nothing downstream can.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re

import yaml
from pydantic import ValidationError

from factory import git
from factory.paths import REPO_ROOT
from factory.schemas import ScopeGuard, WorkItem

RUN_ID_PATTERN = "%Y%m%dT%H%M%SZ"


class IntakeError(RuntimeError):
    """The work item cannot be accepted for planning."""


def load_work_item(path: pathlib.Path) -> WorkItem:
    if not path.exists():
        raise IntakeError(f"no work item at {path}")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise IntakeError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise IntakeError(f"{path} must contain a mapping, got {type(raw).__name__}")
    try:
        return WorkItem.model_validate(raw)
    except ValidationError as exc:
        raise IntakeError(f"{path} is not a valid work item:\n{exc}") from exc


def check_scope(item: WorkItem) -> list[str]:
    """Static sanity checks on the declared scope.

    Catches the two mistakes that make a run meaningless before it starts: a
    scope pointing at nothing, and a scope whose allowed paths overlap its own
    forbidden paths.
    """
    problems: list[str] = []
    guard = ScopeGuard(item.scope)

    for pattern in item.scope.allowed_paths:
        root = pathlib.Path(pattern.split("*", 1)[0])
        if not (REPO_ROOT / root).exists():
            problems.append(f"allowed path {pattern} does not exist in the repository")

    for pattern in item.scope.allowed_paths:
        probe = pattern.replace("**", "probe").replace("*", "probe")
        if guard.is_forbidden(probe):
            problems.append(f"allowed path {pattern} is also forbidden")

    if item.source.type == "eval_failure" and not item.source.case_id:
        problems.append("an eval_failure work item must name the case it came from")

    return problems


def new_run_id(task_id: str, now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.UTC)
    slug = re.sub(r"[^A-Za-z0-9_-]", "-", task_id)
    return f"{slug}-{now.strftime(RUN_ID_PATTERN)}"


def intake(path: pathlib.Path, require_clean_tree: bool = True) -> tuple[WorkItem, str, str]:
    """Validate, identify, and snapshot. Returns (work item, run id, baseline sha).

    A dirty tree is refused: the factory has to be able to tell its own changes
    from someone else's, and a rejected run has to be revertible.
    """
    item = load_work_item(path)

    problems = check_scope(item)
    if problems:
        raise IntakeError("work item scope is not usable:\n  - " + "\n  - ".join(problems))

    if require_clean_tree and not git.is_clean():
        raise IntakeError(
            "working tree is dirty; commit or stash first so the factory's own "
            "changes are distinguishable:\n  - " + "\n  - ".join(git.dirty_paths())
        )

    return item, new_run_id(item.id), git.head_sha()
