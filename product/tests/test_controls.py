"""Tests for the deterministic control layer."""

import pytest

from product.accounting_agent.controls import (
    REGISTRY,
    apply_controls,
    capitalization,
    consistency,
    cutoff,
    duplicates,
    invoice_tolerance,
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


def test_invoice_tolerance_sends_the_target_case_to_review():
    """R07: a $10,400 invoice against a $10,000 PO is a 4% overbill."""
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-1042", "amount": 10000.0},
            "invoice": {"number": "INV-8831", "amount": 10400.0, "vendor": "Cloudspan"},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


def test_invoice_tolerance_auto_approves_inside_both_limits():
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-1", "amount": 10000.0},
            "invoice": {"number": "INV-1", "amount": 10050.0},
        },
        Action.AUTO,
    )
    assert verdict is None


def test_invoice_tolerance_fires_on_absolute_limit_alone():
    """$150 over is within 1% of a $20,000 PO but still exceeds the $100 cap."""
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-2", "amount": 20000.0},
            "invoice": {"number": "INV-2", "amount": 20150.0},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


def test_invoice_tolerance_fires_on_percentage_limit_alone():
    """2% over a $1,000 PO is only $20, inside the $100 cap, but exceeds 1%."""
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-3", "amount": 1000.0},
            "invoice": {"number": "INV-3", "amount": 1020.0},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


def test_invoice_tolerance_ignores_cases_with_no_purchase_order():
    assert (
        invoice_tolerance.check(
            {"bank_line": {"amount": 500}, "invoice": {"amount": 480}}, Action.AUTO
        )
        is None
    )


def test_invoice_tolerance_reviews_a_zero_amount_purchase_order():
    """R09: a blanket PO carrying no amount cannot satisfy the percentage test."""
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {
                "number": "PO-1100",
                "amount": 0.0,
                "note": "blanket order, amount agreed per release",
            },
            "invoice": {"number": "INV-8901", "amount": 50.0, "vendor": "Cloudspan"},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


def test_invoice_tolerance_reviews_a_negative_purchase_order_amount():
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-1101", "amount": -500.0},
            "invoice": {"number": "INV-8902", "amount": 50.0},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


def test_invoice_tolerance_reviews_a_purchase_order_with_no_amount_key():
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-1102", "note": "blanket order"},
            "invoice": {"number": "INV-8903", "amount": 50.0},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


@pytest.mark.parametrize("amount", ["TBD", "1,200.00"])
def test_invoice_tolerance_reviews_a_non_numeric_invoice_amount(amount):
    """A present-but-incomparable amount must not slip through, or crash."""
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-1103", "amount": 10000.0},
            "invoice": {"number": "INV-8904", "amount": amount},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW
    assert repr(amount) in verdict.reason


def test_invoice_tolerance_reviews_a_boolean_purchase_order_amount():
    """`isinstance(True, int)` must not let a bool through as the number 1."""
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-1104", "amount": True},
            "invoice": {"number": "INV-8905", "amount": 1.0},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


def test_invoice_tolerance_reviews_a_boolean_invoice_amount():
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-1105", "amount": 1.0},
            "invoice": {"number": "INV-8906", "amount": True},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


def test_invoice_tolerance_still_ignores_a_case_with_no_purchase_order_key():
    """Non-three-way-match cases stay untouched by the fail-closed rules."""
    assert (
        invoice_tolerance.check(
            {"bank_line": {"amount": 500, "memo": "ACH"}, "invoice": {"amount": 480}},
            Action.AUTO,
        )
        is None
    )


def test_invoice_tolerance_ignores_a_purchase_order_with_no_invoice_amount():
    """An absent invoice figure is deliberately not in this control's remit."""
    assert (
        invoice_tolerance.check(
            {
                "purchase_order": {"number": "PO-1106", "amount": 10000.0},
                "invoice": {"number": "INV-8907", "vendor": "Cloudspan"},
            },
            Action.AUTO,
        )
        is None
    )


def test_invoice_tolerance_auto_approves_a_real_purchase_order_inside_both_limits():
    """$50 and 0.5% against a real PO still auto-approves after the restructure."""
    assert (
        invoice_tolerance.check(
            {
                "purchase_order": {"number": "PO-1107", "amount": 10000.0},
                "invoice": {"number": "INV-8908", "amount": 10050.0},
            },
            Action.AUTO,
        )
        is None
    )


def test_invoice_tolerance_limits_are_inclusive_at_the_boundary():
    """Exactly $100 and exactly 1% is inside tolerance, not over it."""
    assert (
        invoice_tolerance.check(
            {
                "purchase_order": {"number": "PO-1108", "amount": 10000.0},
                "invoice": {"number": "INV-8909", "amount": 10100.0},
            },
            Action.AUTO,
        )
        is None
    )


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
