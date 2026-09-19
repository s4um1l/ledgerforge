"""Do not automate an invoice that overbills its purchase order.

An invoice that *cannot* be compared to its purchase order is not the same thing
as one that compares cleanly. Both used to leave this control silent, and silence
reads as approval. Anything unevaluable now fails closed to REVIEW.
"""

from __future__ import annotations

import math

from product.accounting_agent.controls.policies import policy
from product.accounting_agent.models import Action, ControlVerdict

NAME = "invoice_tolerance"


def _comparable(value) -> bool:
    """True only for a real, finite number.

    Booleans are excluded despite being ints, and numeric strings are excluded
    deliberately: an amount we would have to parse is an amount we have not
    verified, which is exactly the case that belongs in front of a human.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return math.isfinite(float(value))


def _review(reason: str) -> ControlVerdict:
    return ControlVerdict(control=NAME, action=Action.REVIEW, reason=reason)


def check(case_input: dict, proposed: Action) -> ControlVerdict | None:
    purchase_order = case_input.get("purchase_order") or {}

    # No purchase order to match against — e.g. cash-application cases — is not
    # this control's remit.
    if not purchase_order:
        return None

    invoice_amount = (case_input.get("invoice") or {}).get("amount")
    # A purchase order with no invoice figure to check against it is likewise
    # outside this control: there is nothing here claiming to be a match.
    if invoice_amount is None:
        return None

    po_amount = purchase_order.get("amount")
    po_label = purchase_order.get("number") or "with no number"

    # Everything below this point is a state in which the comparison cannot be
    # performed. Each fails closed, and each runs before any arithmetic so that
    # no branch divides by zero or formats a non-number as currency.
    if po_amount is None:
        return _review(
            f"purchase order {po_label} carries no amount; "
            "cannot verify invoice against it"
        )
    if not _comparable(po_amount):
        return _review(
            f"purchase order {po_label} amount {po_amount!r} is not a comparable "
            "number; cannot verify invoice against it"
        )
    if not _comparable(invoice_amount):
        return _review(
            f"invoice amount {invoice_amount!r} is not a comparable number; "
            f"cannot verify it against purchase order {po_label}"
        )
    if po_amount <= 0:
        return _review(
            f"purchase order {po_label} amount ${po_amount:,.2f} is not a positive "
            "figure to compare against"
        )

    limits = policy("invoice_tolerance")
    max_absolute = limits["max_absolute_difference"]
    max_percentage = limits["max_percentage_difference"]

    difference = abs(invoice_amount - po_amount)
    if difference <= max_absolute and difference / po_amount <= max_percentage:
        return None

    return ControlVerdict(
        control=NAME,
        action=Action.REVIEW,
        reason=(
            f"invoice ${invoice_amount:,.2f} differs from purchase order "
            f"${po_amount:,.2f} by ${difference:,.2f}, beyond tolerance"
        ),
    )
