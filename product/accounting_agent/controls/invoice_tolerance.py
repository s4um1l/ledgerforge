"""Do not automate an invoice that overbills its purchase order."""

from __future__ import annotations

from product.accounting_agent.controls.policies import policy
from product.accounting_agent.models import Action, ControlVerdict

NAME = "invoice_tolerance"


def check(case_input: dict, proposed: Action) -> ControlVerdict | None:
    purchase_order = case_input.get("purchase_order") or {}
    invoice = case_input.get("invoice") or {}
    po_amount, invoice_amount = purchase_order.get("amount"), invoice.get("amount")

    # No purchase order to match against — e.g. cash-application cases — is not
    # this control's remit.
    if po_amount is None or invoice_amount is None:
        return None

    limits = policy("invoice_tolerance")
    max_absolute = limits["max_absolute_difference"]
    max_percentage = limits["max_percentage_difference"]

    difference = abs(invoice_amount - po_amount)
    if difference <= max_absolute and (po_amount == 0 or difference / po_amount <= max_percentage):
        return None

    return ControlVerdict(
        control=NAME,
        action=Action.REVIEW,
        reason=(
            f"invoice ${invoice_amount:,.2f} differs from purchase order "
            f"${po_amount:,.2f} by ${difference:,.2f}, beyond tolerance"
        ),
    )
