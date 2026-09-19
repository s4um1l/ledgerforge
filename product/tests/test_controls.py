"""Tests for the deterministic control layer."""

import pytest

from product.accounting_agent.controls import (
    REGISTRY,
    apply_controls,
    capitalization,
    consistency,
    cutoff,
    duplicates,
)
from product.accounting_agent.models import SEVERITY, Action


def test_duplicates_blocks_a_ledger_match_by_invoice_number():
    verdict = duplicates.check(
        {"invoice": {"number": "INV-8840"}, "ledger": {"INV-8840": "posted 2026-09-02"}},
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


def test_duplicates_blocks_a_ledger_match_found_in_a_bank_memo():
    verdict = duplicates.check(
        {"bank_line": {"memo": "ACH INV-8790"}, "ledger": {"INV-8790": "cleared 2026-07-31"}},
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


def test_duplicates_is_silent_without_a_ledger():
    assert duplicates.check({"invoice": {"number": "INV-1"}}, Action.AUTO) is None


def test_capitalization_fires_above_threshold_with_a_description():
    verdict = capitalization.check(
        {"invoice": {"amount": 6200.00, "description": "4x MacBook Pro"}}, Action.AUTO
    )
    assert verdict and verdict.action is Action.REVIEW


def test_capitalization_ignores_an_amount_with_no_description():
    """An amount alone is not evidence of an asset — R07 must not trip this."""
    assert capitalization.check({"invoice": {"amount": 10400.00}}, Action.AUTO) is None


def test_capitalization_ignores_small_purchases():
    assert (
        capitalization.check({"invoice": {"amount": 299.00, "description": "seats"}}, Action.AUTO)
        is None
    )


def test_cutoff_rejects_a_document_dated_after_the_period():
    verdict = cutoff.check({"invoice": {"date": "2026-10-02"}, "period": "2026-09"}, Action.AUTO)
    assert verdict and verdict.action is Action.REJECT


def test_cutoff_allows_a_document_inside_the_period():
    inside = {"invoice": {"date": "2026-09-30"}, "period": "2026-09"}
    assert cutoff.check(inside, Action.AUTO) is None


def test_consistency_flags_contradictory_commentary():
    verdict = consistency.check(
        {"commentary": ["vendor price increase", "timing only, reverses next month"]}, Action.AUTO
    )
    assert verdict and verdict.action is Action.REVIEW


def test_consistency_accepts_a_single_explanation():
    assert consistency.check({"commentary": "two deals slipped to Q4"}, Action.AUTO) is None


def test_most_restrictive_verdict_wins():
    action, verdicts = apply_controls(
        {
            "invoice": {
                "number": "INV-1",
                "date": "2026-10-02",
                "amount": 9000,
                "description": "x",
            },
            "ledger": {"INV-1": "posted"},
            "period": "2026-09",
        },
        Action.AUTO,
    )
    assert action is Action.REJECT
    assert len(verdicts) == 3


def test_controls_can_only_reduce_autonomy():
    """The invariant that makes this layer safe to extend.

    A control may take AUTO down to REVIEW or REJECT. Nothing may ever move a
    decision back up, so adding a control cannot increase autonomous risk.
    """
    inputs = [
        {},
        {"invoice": {"number": "INV-1"}, "ledger": {"INV-1": "posted"}},
        {"invoice": {"date": "2026-12-01"}, "period": "2026-09"},
        {"commentary": ["a", "b"]},
        {"invoice": {"amount": 99999, "description": "server rack"}},
    ]
    for case_input in inputs:
        for proposed in Action:
            action, _ = apply_controls(case_input, proposed)
            assert SEVERITY[action] >= SEVERITY[proposed], (case_input, proposed, action)


@pytest.mark.parametrize("control", REGISTRY)
def test_every_control_tolerates_an_empty_case(control):
    assert control({}, Action.AUTO) is None
