"""Do not auto-approve an invoice that does not match the order it was matched to.

Both limits must hold for automation: a difference is inside tolerance only when it
is small in dollars *and* small as a fraction of the order. A comparison we cannot
evaluate — a missing amount is silent, a zero-amount order is not — never buys
autonomy.
"""

from __future__ import annotations

from product.accounting_agent.controls.policies import policy
from product.accounting_agent.models import Action, ControlVerdict

NAME = "invoice_tolerance"

# Amounts arrive as floats, so an exactly-at-the-limit case ($10,100 against a
# $10,000 PO) must not be tripped by binary representation error.
EPS = 1e-9


def _amount(document: dict) -> float | None:
    value = document.get("amount")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def check(case_input: dict, proposed: Action) -> ControlVerdict | None:
    po = case_input.get("purchase_order") or {}
    invoice = case_input.get("invoice") or {}
    po_amount, invoice_amount = _amount(po), _amount(invoice)

    # The control only speaks when it has both documents to compare.
    if po_amount is None or invoice_amount is None:
        return None

    difference = abs(invoice_amount - po_amount)
    if difference == 0:
        return None

    limits = policy(NAME)
    max_absolute = limits["max_absolute_difference"]
    max_percentage = limits["max_percentage_difference"]

    within_absolute = difference <= max_absolute + EPS
    if po_amount == 0:
        # A non-zero invoice against a zero-amount order has no ratio to test, so
        # the percentage limit cannot be satisfied and a human decides.
        relative, within_percentage = None, False
    else:
        relative = difference / abs(po_amount)
        within_percentage = relative <= max_percentage + EPS

    if within_absolute and within_percentage:
        return None

    verb = "exceeds" if invoice_amount > po_amount else "falls short of"
    share = f"{relative:.2%}" if relative is not None else "percentage undefined"
    return ControlVerdict(
        control=NAME,
        action=Action.REVIEW,
        reason=(
            f"invoice ${invoice_amount:,.2f} {verb} PO {po.get('number', 'unknown')} "
            f"${po_amount:,.2f} by ${difference:,.2f} ({share}), outside the "
            f"${max_absolute:,.2f} / {max_percentage:.2%} tolerance"
        ),
    )
