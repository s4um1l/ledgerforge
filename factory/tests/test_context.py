import pytest

from factory.context import READABLE_ROOTS, ContextError, _assert_readable, resolve
from factory.intake import load_work_item
from factory.paths import REPO_ROOT, TASKS_DIR


def package():
    return resolve(load_work_item(TASKS_DIR / "ACCT-001.yaml"))


def test_resolves_only_files_inside_the_allowed_scope():
    paths = package().file_paths
    assert paths
    assert all(
        p.startswith(("product/accounting_agent/controls/", "product/tests/")) for p in paths
    )


def test_includes_the_customer_policy():
    docs = [d.path for d in package().domain_docs]
    assert "benchmark/world/policies.yaml" in docs


def test_includes_the_failing_case_input_but_not_an_answer():
    """Reading the case is necessary; the case file carries no answer to read."""
    case = package().failure.case_input
    assert case["id"] == "R07"
    assert case["input"]["purchase_order"]["amount"] == 10000.0
    assert case["input"]["invoice"]["amount"] == 10400.0
    assert "gold_action" not in case
    assert "labels" not in case


def test_failure_carries_the_observed_and_expected_behaviour():
    failure = package().failure
    assert (failure.actual, failure.expected) == ("AUTO", "REVIEW")


def test_reads_are_whitelisted_not_blacklisted():
    """Anything outside the three readable trees is refused by construction."""
    with pytest.raises(ContextError, match="outside the readable roots"):
        _assert_readable(REPO_ROOT / "pyproject.toml")
    with pytest.raises(ContextError, match="outside the readable roots"):
        _assert_readable(REPO_ROOT / "benchmark" / "gold" / "answers.jsonl")


def test_the_readable_roots_are_the_documented_three_plus_prompts():
    names = sorted(p.name for p in READABLE_ROOTS)
    assert names == ["cases", "product", "prompts", "world"]
