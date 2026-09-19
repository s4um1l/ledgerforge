"""Structural checks on the benchmark itself.

Cheap to run, and they catch the failure mode where a case is edited but its gold
answer is not — which would silently change the score everything is compared to.
"""

from collections import Counter

from evals.gold import load_gold
from evals.loaders import load_cases

# Frozen as v0.1. Reconciliation carries ten because the blanket-purchase-order
# pair (R09/R10) is deliberate: one case where failing closed is right and one
# where it is over-escalation. Without both, a control that escalates everything
# scores as well as a correct one.
EXPECTED_CATEGORIES = {
    "reconciliation": 10,
    "data_entry": 7,
    "variance": 7,
    "schedules": 8,
}


def test_case_count_matches_the_category_mix():
    assert len(load_cases()) == sum(EXPECTED_CATEGORIES.values()) == 32


def test_category_mix_matches_the_spec():
    counts = Counter(c.category for c in load_cases().values())
    assert dict(counts) == EXPECTED_CATEGORIES


def test_every_case_has_exactly_one_gold_answer():
    cases, gold = load_cases(), load_gold()
    assert set(cases) == set(gold)


def test_all_cases_share_one_frozen_benchmark_version():
    cases = load_cases().values()
    versions = {c.benchmark_version for c in cases}
    assert versions == {"v0.1"}, f"mixed or unfrozen benchmark versions: {versions}"
    assert not any(c.scaffold for c in cases), "v0.1 is frozen; no case may be marked scaffold"


def test_duplicate_questions_have_evidence_to_work_from():
    """A question asked without its evidence returns a number that means nothing.

    Measured in Phase 3.5: `possible_duplicate` came back 0.50-0.62 on cases
    carrying no ledger at all. v0.1 gives most cases a ledger so the answer is
    about something.
    """
    cases = load_cases()
    with_ledger = [c for c in cases.values() if "ledger" in c.input]
    assert len(with_ledger) >= 20, f"only {len(with_ledger)} cases carry a ledger"


def test_the_benchmark_contains_over_escalation_cases():
    """Cases where the correct answer is AUTO and a cautious system gets it wrong.

    Without these, a system that sends everything to a human scores well and the
    cost side of automation is invisible.
    """
    gold = load_gold()
    cases = load_cases()
    over_escalation = [
        cid
        for cid, g in gold.items()
        if str(g.gold_action) == "AUTO" and cases[cid].candidate_action != "AUTO"
    ]
    assert len(over_escalation) >= 1, "no case punishes unnecessary escalation"


def test_r07_is_the_demo_case():
    """R07 is the tolerance failure the whole factory demo hangs on."""
    case, gold = load_cases()["R07"], load_gold()["R07"]
    assert case.candidate_action == "AUTO"
    assert gold.gold_action == "REVIEW"
    assert gold.labels.requires_human_review is True
    assert gold.labels.candidate_supported is False
