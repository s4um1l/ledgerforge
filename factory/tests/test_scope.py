from factory.schemas import Scope, ScopeGuard


def guard(allowed: list[str], forbidden: list[str] | None = None) -> ScopeGuard:
    return ScopeGuard(Scope(allowed_paths=allowed, forbidden_paths=forbidden or []))


def test_allowed_glob_matches_nested_files():
    g = guard(["product/accounting_agent/controls/**"])
    assert g.may_modify("product/accounting_agent/controls/tolerance.py")
    assert g.may_modify("product/accounting_agent/controls/nested/deep.py")
    assert not g.may_modify("product/accounting_agent/agent.py")


def test_forbidden_beats_allowed():
    """The rule that makes a broad allowance safe to write."""
    g = guard(["product/**", "benchmark/**"], ["benchmark/gold/**"])
    assert g.may_modify("product/accounting_agent/agent.py")
    assert g.may_modify("benchmark/cases/R07.json")
    assert not g.may_modify("benchmark/gold/answers.jsonl")


def test_paths_outside_every_pattern_are_denied_by_default():
    g = guard(["product/tests/**"])
    assert not g.may_modify("evals/metrics.py")
    assert not g.may_modify("pyproject.toml")


def test_violations_lists_only_offending_paths():
    g = guard(["product/tests/**"], ["evals/**"])
    violations = g.violations(["product/tests/test_x.py", "evals/metrics.py", "README.md"])
    assert violations == ["README.md", "evals/metrics.py"]
