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

S02_INPUT = {
    "invoice": {
        "number": "MS-7741",
        "vendor": "Meridian Staffing",
        "amount": 8000.0,
        "date": "2026-10-03",
        "description": "contract engineering, Sept 1-30",
    },
    "service_period": "2026-09-01..2026-09-30",
    "supporting": {
        "signed_sow": "SOW-88",
        "timesheets_received": True,
        "work_completed": "2026-09-30",
    },
    "proposed_entry": {"debit": "6300", "credit": "2100", "amount": 8000.0},
    "ledger": {"recent_postings": []},
    "policy_ref": "month_end_cutoff",
    "period": "2026-09",
}


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


def test_cutoff_allows_a_document_inside_the_period_that_states_a_service_period():
    """The in-period path is untouched: the new branch is never reached."""
    inside = {
        "invoice": {"date": "2026-09-28"},
        "service_period": "2026-09-01..2026-09-30",
        "period": "2026-09",
    }
    assert cutoff.check(inside, Action.AUTO) is None


def test_cutoff_accrues_a_late_invoice_for_work_performed_in_the_period():
    """S02: dated 2026-10-03, work done 1-30 September, so it accrues."""
    assert cutoff.check(S02_INPUT, Action.AUTO) is None


def test_cutoff_accrues_a_service_period_stated_as_a_dict():
    accrual = {
        "invoice": {"date": "2026-10-03"},
        "service_period": {"start": "2026-09-01", "end": "2026-09-30"},
        "period": "2026-09",
    }
    assert cutoff.check(accrual, Action.AUTO) is None


def test_cutoff_accrues_a_service_period_stated_as_a_bare_month():
    accrual = {
        "invoice": {"date": "2026-10-03"},
        "service_period": "2026-09",
        "period": "2026-09",
    }
    assert cutoff.check(accrual, Action.AUTO) is None


def test_cutoff_accrues_a_service_period_that_opened_before_the_closing_month():
    accrual = {
        "invoice": {"date": "2026-10-03"},
        "service_period": "2026-08-15..2026-09-30",
        "period": "2026-09",
    }
    assert cutoff.check(accrual, Action.AUTO) is None


def test_cutoff_still_rejects_work_performed_after_the_cutoff():
    """S04's shape: dated after the period and worked after it too."""
    verdict = cutoff.check(
        {
            "invoice": {"number": "MS-7742", "amount": 4400.0, "date": "2026-10-02"},
            "service_period": "2026-10-01..2026-10-02",
            "period": "2026-09",
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REJECT
    assert "cannot post to" in verdict.reason


def test_cutoff_still_rejects_with_no_service_period_stated():
    """With nothing said about the work, the invoice date is all there is."""
    verdict = cutoff.check({"invoice": {"date": "2026-10-02"}, "period": "2026-09"}, Action.AUTO)
    assert verdict and verdict.action is Action.REJECT


@pytest.mark.parametrize(
    "stated",
    ["Q3", "sometime in September", "2026-09-01..", "2026-13", "2026-02-30", 42, True, None, []],
)
def test_cutoff_still_rejects_an_unparseable_service_period(stated):
    """A period we cannot read is not a period we can accrue against."""
    verdict = cutoff.check(
        {"invoice": {"date": "2026-10-02"}, "service_period": stated, "period": "2026-09"},
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REJECT


def test_cutoff_still_rejects_a_service_period_straddling_the_cutoff():
    """Half the work falls in October, so it is not a clean September accrual."""
    verdict = cutoff.check(
        {
            "invoice": {"date": "2026-10-20"},
            "service_period": "2026-09-15..2026-10-15",
            "period": "2026-09",
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REJECT


def test_cutoff_still_rejects_a_service_period_wholly_before_the_period():
    """Deliberately conservative: a prior-period item is a human's call."""
    verdict = cutoff.check(
        {
            "invoice": {"date": "2026-10-02"},
            "service_period": "2026-07-01..2026-07-31",
            "period": "2026-09",
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REJECT


def test_cutoff_still_rejects_an_inverted_service_period():
    verdict = cutoff.check(
        {
            "invoice": {"date": "2026-10-02"},
            "service_period": "2026-09-30..2026-09-01",
            "period": "2026-09",
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REJECT


def test_cutoff_still_rejects_when_the_completion_date_contradicts_the_service_period():
    """The claim says September; the supporting evidence says October."""
    verdict = cutoff.check(
        {
            "invoice": {"date": "2026-10-20"},
            "service_period": "2026-09-01..2026-09-30",
            "supporting": {"work_completed": "2026-10-11"},
            "period": "2026-09",
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REJECT
    assert "2026-10-11" in verdict.reason


@pytest.mark.parametrize("completed", ["finished at month end", None, [], "2026-09"])
def test_cutoff_accrues_when_the_completion_date_carries_no_contradiction(completed):
    """Unreadable or in-period completion evidence is no signal, not a veto."""
    accrual = {
        "invoice": {"date": "2026-10-03"},
        "service_period": "2026-09-01..2026-09-30",
        "supporting": {"work_completed": completed},
        "period": "2026-09",
    }
    assert cutoff.check(accrual, Action.AUTO) is None


def test_cutoff_tolerates_a_non_mapping_supporting_block():
    accrual = {
        "invoice": {"date": "2026-10-03"},
        "service_period": "2026-09-01..2026-09-30",
        "supporting": ["SOW-88"],
        "period": "2026-09",
    }
    assert cutoff.check(accrual, Action.AUTO) is None


def test_capitalization_ignores_a_charge_for_a_stated_service_period():
    """S02: $8,000 of labour consumed in September is an expense, not an asset."""
    assert (
        capitalization.check(
            {
                "invoice": {"amount": 8000.0, "description": "contract engineering, Sept 1-30"},
                "service_period": "2026-09-01..2026-09-30",
            },
            Action.AUTO,
        )
        is None
    )


def test_capitalization_still_fires_when_the_service_period_is_unparseable():
    """The exemption rests on a period we can actually read."""
    verdict = capitalization.check(
        {
            "invoice": {"amount": 6200.00, "description": "4x MacBook Pro"},
            "service_period": "Q3",
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


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


def test_invoice_tolerance_auto_approves_a_small_invoice_on_a_blanket_order():
    """R10: a marked blanket order has no control total, and $50 needs no signature."""
    assert (
        invoice_tolerance.check(
            {
                "purchase_order": {"number": "PO-1100", "amount": 0.0, "blanket": True},
                "invoice": {"number": "INV-8902", "amount": 50.0, "vendor": "Cloudspan"},
            },
            Action.AUTO,
        )
        is None
    )


def test_invoice_tolerance_reviews_a_large_invoice_on_a_blanket_order():
    """R09: the blanket exemption is bounded by the approval limit."""
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-1100", "amount": 0.0, "blanket": True},
            "invoice": {"number": "INV-8901", "amount": 12400.0, "vendor": "Cloudspan"},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW
    assert "approval limit" in verdict.reason


def test_invoice_tolerance_blanket_limit_is_inclusive_at_the_boundary():
    """At the limit requires review, not merely above it."""
    limit = invoice_tolerance._approval_limit()
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-1109", "amount": 0.0, "blanket": True},
            "invoice": {"number": "INV-8910", "amount": limit},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


def test_invoice_tolerance_treats_an_absent_amount_on_a_blanket_order_like_zero():
    """Once the marker is present, absence and zero are the same absence of a total."""
    assert (
        invoice_tolerance.check(
            {
                "purchase_order": {"number": "PO-1110", "blanket": True},
                "invoice": {"number": "INV-8911", "amount": 50.0},
            },
            Action.AUTO,
        )
        is None
    )


def test_invoice_tolerance_does_not_exempt_a_blanket_order_claimed_only_in_prose():
    """The explicit marker exempts; the free-text note does not."""
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {
                "number": "PO-1111",
                "amount": 0.0,
                "note": "blanket order, amount agreed per release",
            },
            "invoice": {"number": "INV-8912", "amount": 50.0},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


@pytest.mark.parametrize("marker", ["true", "yes", 1, False])
def test_invoice_tolerance_reviews_a_malformed_blanket_marker(marker):
    """The marker check is a strict boolean identity, so anything else fails closed."""
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-1112", "amount": 0.0, "blanket": marker},
            "invoice": {"number": "INV-8913", "amount": 50.0},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


def test_invoice_tolerance_reviews_an_unparseable_amount_on_a_blanket_order():
    """An amount we would have to parse stays unevaluable even on a blanket order."""
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-1113", "amount": "TBD", "blanket": True},
            "invoice": {"number": "INV-8914", "amount": 50.0},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


def test_invoice_tolerance_reviews_an_unparseable_invoice_on_a_blanket_order():
    """The exemption never reaches arithmetic on an invoice figure we cannot verify."""
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-1114", "amount": 0.0, "blanket": True},
            "invoice": {"number": "INV-8915", "amount": "TBD"},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


def test_invoice_tolerance_still_compares_a_blanket_order_that_has_a_real_amount():
    """The marker exempts a missing control total, not the tolerance test itself."""
    verdict = invoice_tolerance.check(
        {
            "purchase_order": {"number": "PO-1115", "amount": 10000.0, "blanket": True},
            "invoice": {"number": "INV-8916", "amount": 10400.0},
        },
        Action.AUTO,
    )
    assert verdict and verdict.action is Action.REVIEW


def test_invoice_tolerance_auto_approves_a_blanket_order_with_a_real_amount_in_limits():
    assert (
        invoice_tolerance.check(
            {
                "purchase_order": {"number": "PO-1116", "amount": 10000.0, "blanket": True},
                "invoice": {"number": "INV-8917", "amount": 10050.0},
            },
            Action.AUTO,
        )
        is None
    )


def test_the_staff_accountant_limit_straddles_the_two_blanket_cases():
    """A policy edit that would silently flip R09 or R10 must fail loudly here."""
    limit = invoice_tolerance._approval_limit()
    assert limit is not None
    assert 50.0 < limit <= 12400.0


def test_apply_controls_leaves_the_small_blanket_invoice_on_auto():
    """End-to-end at the control layer, on R10's full input."""
    action, verdicts = apply_controls(
        {
            "purchase_order": {
                "number": "PO-1100",
                "vendor": "Cloudspan",
                "amount": 0.0,
                "blanket": True,
                "note": "blanket order, amount agreed per release",
            },
            "invoice": {
                "number": "INV-8902",
                "vendor": "Cloudspan",
                "amount": 50.0,
                "date": "2026-09-26",
                "description": "overage, 2 GB egress",
            },
            "ledger": {
                "recent_postings": [
                    {
                        "document": "INV-8871",
                        "party": "Cloudspan",
                        "amount": 42.0,
                        "date": "2026-08-27",
                        "state": "posted",
                    }
                ]
            },
            "policy_ref": "review_requirements",
            "period": "2026-09",
        },
        Action.AUTO,
    )
    assert action is Action.AUTO
    assert verdicts == []


def test_apply_controls_leaves_the_accrued_late_invoice_on_auto():
    """End-to-end at the control layer, on S02's full input."""
    action, verdicts = apply_controls(S02_INPUT, Action.AUTO)
    assert action is Action.AUTO
    assert verdicts == []


def test_apply_controls_still_rejects_work_performed_after_the_period():
    """S04's shape stays out: nothing about it was performed in September."""
    action, verdicts = apply_controls(
        {
            "invoice": {
                "number": "MS-7742",
                "vendor": "Meridian Staffing",
                "amount": 4400.0,
                "date": "2026-10-02",
                "description": "contract engineering, Oct 1-2",
            },
            "service_period": "2026-10-01..2026-10-02",
            "supporting": {"signed_sow": "SOW-88", "work_completed": "2026-10-02"},
            "ledger": {"recent_postings": []},
            "policy_ref": "month_end_cutoff",
            "period": "2026-09",
        },
        Action.AUTO,
    )
    assert action is Action.REJECT
    assert [v.control for v in verdicts] == [cutoff.NAME]


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
        S02_INPUT,
    ]
    for case_input in inputs:
        for proposed in Action:
            action, _ = apply_controls(case_input, proposed)
            assert SEVERITY[action] >= SEVERITY[proposed], (case_input, proposed, action)


@pytest.mark.parametrize("control", REGISTRY)
def test_every_control_tolerates_an_empty_case(control):
    assert control({}, Action.AUTO) is None
