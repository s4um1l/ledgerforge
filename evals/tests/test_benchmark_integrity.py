"""Structural checks on the benchmark itself.

Cheap to run, and they catch the failure mode where a case is edited but its gold
answer is not — which would silently change the score everything is compared to.
"""

from collections import Counter

from evals.gold import load_gold
from evals.loaders import load_cases

# R09 was added after the Phase 3 planner found a hole no case covered: a
# purchase order carrying no amount. A defect with no case is a gap in the
# benchmark, and closing it is human work — the factory may not edit these.
EXPECTED_CATEGORIES = {
    "reconciliation": 9,
    "data_entry": 7,
    "variance": 7,
    "schedules": 8,
}


def test_case_count_matches_the_category_mix():
    assert len(load_cases()) == sum(EXPECTED_CATEGORIES.values()) == 31


def test_category_mix_matches_the_spec():
    counts = Counter(c.category for c in load_cases().values())
    assert dict(counts) == EXPECTED_CATEGORIES


def test_every_case_has_exactly_one_gold_answer():
    cases, gold = load_cases(), load_gold()
    assert set(cases) == set(gold)


def test_all_cases_share_one_benchmark_version():
    versions = {c.benchmark_version for c in load_cases().values()}
    assert len(versions) == 1, f"mixed benchmark versions: {versions}"


def test_r07_is_the_demo_case():
    """R07 is the tolerance failure the whole factory demo hangs on."""
    case, gold = load_cases()["R07"], load_gold()["R07"]
    assert case.candidate_action == "AUTO"
    assert gold.gold_action == "REVIEW"
    assert gold.labels.requires_human_review is True
    assert gold.labels.candidate_supported is False
