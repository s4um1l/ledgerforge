"""Tests for the invoice tolerance control."""

from product.accounting_agent.controls import tolerance
from product.accounting_agent.models import Action

R07 = {
    "purchase_order": {"number": "PO-1042", "amount": 10000.00},
    "invoice": {"number": "INV-8831", "amount": 10400.00},
}


def test_r07_overbill_requires_review():
    verdict = tolerance.check(R07, Action.AUTO)
    assert verdict and verdict.action is Action.REVIEW
    assert "outside tolerance" in verdict.reason


def test_small_absolute_and_relative_difference_may_auto_approve():
    within = {"purchase_order": {"amount": 10000.00}, "invoice": {"amount": 10050.00}}
    assert tolerance.check(within, Action.AUTO) is None


def test_difference_must_satisfy_both_limits():
    # $90 is inside the absolute limit but 9% is outside the percentage limit.
    absolute_ok = {"purchase_order": {"amount": 1000.00}, "invoice": {"amount": 1090.00}}
    assert tolerance.check(absolute_ok, Action.AUTO) is not None

    # 0.5% is inside the percentage limit but $500 is outside the absolute limit.
    percentage_ok = {"purchase_order": {"amount": 100000.00}, "invoice": {"amount": 100500.00}}
    assert tolerance.check(percentage_ok, Action.AUTO) is not None


def test_silent_without_a_purchase_order():
    """A bank deposit matched to an invoice is not a three-way match."""
    cash_application = {
        "bank_line": {"amount": 4000.00},
        "open_invoice": {"number": "INV-8806", "amount": 4500.00},
    }
    assert tolerance.check(cash_application, Action.AUTO) is None


def test_silent_on_an_empty_case():
    assert tolerance.check({}, Action.AUTO) is None
