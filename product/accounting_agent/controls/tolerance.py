"""Three-way match: an invoice may not exceed its purchase order.

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
