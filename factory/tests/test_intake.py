import pathlib

import pytest

from factory.intake import IntakeError, check_scope, load_work_item, new_run_id
from factory.paths import TASKS_DIR

ACCT_001 = TASKS_DIR / "ACCT-001.yaml"

MINIMAL = """
id: ACCT-500
title: A task
source:
  type: eval_failure
  case_id: R07
problem:
  summary: something went wrong
  actual_behavior: AUTO
  expected_behavior: REVIEW
business_impact:
  severity: high
intent: fix it
scope:
  allowed_paths: [product/tests/**]
  forbidden_paths: [benchmark/gold/**]
acceptance_criteria: [it works]
verification:
  commands: [uv run pytest]
"""


def write(tmp_path: pathlib.Path, text: str) -> pathlib.Path:
    path = tmp_path / "task.yaml"
    path.write_text(text)
    return path


def test_the_shipped_work_item_is_valid():
    item = load_work_item(ACCT_001)
    assert item.id == "ACCT-001"
    assert item.target_case_id == "R07"
    assert item.regression_policy.max_new_failures == 0
    assert check_scope(item) == []


def test_missing_file():
    with pytest.raises(IntakeError, match="no work item"):
        load_work_item(pathlib.Path("factory/tasks/nope.yaml"))


def test_not_yaml(tmp_path):
    with pytest.raises(IntakeError, match="not valid YAML"):
        load_work_item(write(tmp_path, "id: [unclosed"))


def test_not_a_mapping(tmp_path):
    with pytest.raises(IntakeError, match="must contain a mapping"):
        load_work_item(write(tmp_path, "- just\n- a list\n"))


def test_missing_required_field(tmp_path):
    text = MINIMAL.replace("intent: fix it\n", "")
    with pytest.raises(IntakeError, match="not a valid work item"):
        load_work_item(write(tmp_path, text))


def test_unknown_field_is_refused(tmp_path):
    """A typo'd key must fail loudly rather than being silently ignored."""
    text = MINIMAL + "\nregresion_policy:\n  max_new_failures: 5\n"
    with pytest.raises(IntakeError, match="not a valid work item"):
        load_work_item(write(tmp_path, text))


def test_blank_intent_is_refused(tmp_path):
    text = MINIMAL.replace("intent: fix it", "intent: '   '")
    with pytest.raises(IntakeError):
        load_work_item(write(tmp_path, text))


def test_scope_must_point_at_something_real(tmp_path):
    text = MINIMAL.replace("product/tests/**", "product/imaginary/**")
    problems = check_scope(load_work_item(write(tmp_path, text)))
    assert any("does not exist" in p for p in problems)


def test_scope_cannot_allow_what_it_forbids(tmp_path):
    text = MINIMAL.replace("forbidden_paths: [benchmark/gold/**]", "forbidden_paths: [product/**]")
    problems = check_scope(load_work_item(write(tmp_path, text)))
    assert any("also forbidden" in p for p in problems)


def test_eval_failure_must_name_its_case(tmp_path):
    text = MINIMAL.replace("  case_id: R07\n", "")
    problems = check_scope(load_work_item(write(tmp_path, text)))
    assert any("must name the case" in p for p in problems)


def test_run_ids_are_unique_and_readable():
    import datetime as dt

    stamp = dt.datetime(2026, 9, 19, 14, 25, 30, tzinfo=dt.UTC)
    assert new_run_id("ACCT-001", stamp) == "ACCT-001-20260919T142530Z"
    assert new_run_id("weird/id", stamp).startswith("weird-id-")
