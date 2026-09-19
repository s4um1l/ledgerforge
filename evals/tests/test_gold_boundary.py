"""The architectural boundary, as a test.

`factory/` may read the product, the cases and the world. It may never read
`benchmark/gold/`. If this test ever fails, the factory is grading its own
homework and every result after that point is worthless.
"""

import pathlib

import pytest

from evals.paths import CASES_DIR, GOLD_DIR, REPO_ROOT, GoldAccessError, assert_not_gold


def test_assert_not_gold_blocks_the_gold_directory_and_its_contents():
    with pytest.raises(GoldAccessError):
        assert_not_gold(GOLD_DIR)
    with pytest.raises(GoldAccessError):
        assert_not_gold(GOLD_DIR / "answers.jsonl")


def test_assert_not_gold_allows_cases():
    assert assert_not_gold(CASES_DIR) == CASES_DIR.resolve()


def test_loaders_refuse_to_be_pointed_at_gold():
    from evals.loaders import load_cases, load_run

    with pytest.raises(GoldAccessError):
        load_cases(GOLD_DIR)
    with pytest.raises(GoldAccessError):
        load_run(GOLD_DIR / "answers.jsonl")


def factory_sources() -> list[pathlib.Path]:
    return [p for p in (REPO_ROOT / "factory").rglob("*.py")]


def test_no_factory_module_reaches_for_gold():
    offenders = []
    for path in factory_sources():
        text = path.read_text()
        if "evals.gold" in text or "benchmark/gold" in text or "answers.jsonl" in text:
            offenders.append(path.relative_to(REPO_ROOT))
    assert offenders == [], f"factory modules must not reference gold: {offenders}"
