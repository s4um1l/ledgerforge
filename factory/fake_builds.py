"""Scripted builds: the Phase 2 stand-in for a coding model.

Phase 2's goal is to prove the orchestration, not the intelligence — so the
"builder" here replays a patch that a human wrote, keyed by task id. Everything
around it (scope enforcement, validation, review, the decision gate, the trace)
is the real implementation and does not change when Phase 3 swaps a model in.

If a task id has no scripted build, the fake builder fails honestly rather than
pretending to have done something. Delete this module in Phase 3.
"""

from __future__ import annotations

from collections.abc import Callable

from factory.paths import REPO_ROOT
from factory.schemas import BuildResult

TOLERANCE_CONTROL = '''"""Three-way match: an invoice may not exceed its purchase order.

Tolerance comes from the customer's policy, not from this module.
"""

from __future__ import annotations

from product.accounting_agent.controls.policies import policy
from product.accounting_agent.models import Action, ControlVerdict

NAME = "invoice_tolerance"


def check(case_input: dict, proposed: Action) -> ControlVerdict | None:
    """Compare an invoice to the purchase order it is matched against.

    Scoped deliberately to cases carrying *both* a purchase order and an invoice.
    A cash-application case comparing a bank deposit to an open invoice is a
    different question with legitimate reasons to differ — a credit memo, a
    partial payment — and applying a PO tolerance to it would send correct
    automatic decisions to a human for no reason.
    """
    po = case_input.get("purchase_order") or {}
    invoice = case_input.get("invoice") or {}
    po_amount, invoice_amount = po.get("amount"), invoice.get("amount")
    if po_amount is None or invoice_amount is None:
        return None
    if not po_amount:
        return None

    limits = policy("invoice_tolerance")
    difference = abs(invoice_amount - po_amount)
    percentage = difference / po_amount

    within_absolute = difference <= limits["max_absolute_difference"]
    within_percentage = percentage <= limits["max_percentage_difference"]
    if within_absolute and within_percentage:
        return None

    return ControlVerdict(
        control=NAME,
        action=Action.REVIEW,
        reason=(
            f"invoice ${invoice_amount:,.2f} differs from PO ${po_amount:,.2f} "
            f"by ${difference:,.2f} ({percentage:.1%}), outside tolerance of "
            f"${limits['max_absolute_difference']:,} / "
            f"{limits['max_percentage_difference']:.0%}"
        ),
    )
'''

TOLERANCE_TESTS = '''"""Tests for the invoice tolerance control."""

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
'''


def _build_acct_001() -> BuildResult:
    control = REPO_ROOT / "product/accounting_agent/controls/tolerance.py"
    tests = REPO_ROOT / "product/tests/test_tolerance_control.py"
    registry = REPO_ROOT / "product/accounting_agent/controls/__init__.py"

    control.write_text(TOLERANCE_CONTROL)
    tests.write_text(TOLERANCE_TESTS)

    source = registry.read_text()
    source = source.replace(
        """from product.accounting_agent.controls import (
    capitalization,
    consistency,
    cutoff,
    duplicates,
)""",
        """from product.accounting_agent.controls import (
    capitalization,
    consistency,
    cutoff,
    duplicates,
    tolerance,
)""",
    )
    source = source.replace(
        """    duplicates.check,
    capitalization.check,
    cutoff.check,
    consistency.check,
]""",
        """    duplicates.check,
    capitalization.check,
    cutoff.check,
    consistency.check,
    tolerance.check,
]""",
    )
    registry.write_text(source)

    return BuildResult(
        changed_files=[
            "product/accounting_agent/controls/tolerance.py",
            "product/accounting_agent/controls/__init__.py",
            "product/tests/test_tolerance_control.py",
        ],
        created_files=[
            "product/accounting_agent/controls/tolerance.py",
            "product/tests/test_tolerance_control.py",
        ],
        summary=(
            "Added an invoice tolerance control that compares an invoice to its purchase "
            "order against the configured absolute and percentage limits, and registered "
            "it in the control registry."
        ),
        tests_added=["product/tests/test_tolerance_control.py"],
        known_limitations=[
            "Only fires when a case carries both a purchase order and an invoice; "
            "cash-application discrepancies are out of scope for this policy.",
            "Thresholds come from benchmark/world/policies.yaml and are not per-vendor.",
        ],
    )


SCRIPTED_BUILDS: dict[str, Callable[[], BuildResult]] = {
    "ACCT-001": _build_acct_001,
}

# What each scripted build intends to touch, so the fake planner can name files
# without being handed the patch itself.
SCRIPTED_TARGETS: dict[str, list[str]] = {
    "ACCT-001": [
        "product/accounting_agent/controls/tolerance.py",
        "product/accounting_agent/controls/__init__.py",
        "product/tests/test_tolerance_control.py",
    ],
}
