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


def _is_blanket(purchase_order: dict) -> bool:
    """True only for an explicit boolean marker.

    Not a truthiness test and not a reading of the free-text note: a blanket
    order is exempted from the control total comparison, so the evidence for it
    has to be a deliberate structured claim rather than prose or a stray string.
    """
    return purchase_order.get("blanket") is True


def _approval_limit() -> float | None:
    """The staff accountant limit, below which no second signature is required.

    Returns None when the policy section or key is absent or unusable, so a
    renamed key escalates rather than raising or defaulting to a number.
    """
    try:
        limit = policy("review_requirements").get("staff_accountant_limit")
    except (KeyError, AttributeError):
        return None
    if not _comparable(limit) or limit <= 0:
        return None
    return float(limit)


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

    # A blanket order has no control total by design, which is a different thing
    # from a purchase order that is missing data. There is no comparison to fail
    # closed on here, so the gate is the approval matrix instead. The invoice
    # figure must already be comparable — otherwise the amount check below would
    # be arithmetic on an unverified value — and the purchase order must carry no
    # usable total: a blanket order with a real figure is still compared normally.
    no_control_total = po_amount is None or (_comparable(po_amount) and po_amount <= 0)
    if _is_blanket(purchase_order) and _comparable(invoice_amount) and no_control_total:
        limit = _approval_limit()
        if limit is None:
            return _review(
                f"blanket purchase order {po_label} has no control total, and no usable "
                "review_requirements.staff_accountant_limit to gate the invoice against"
            )
        if invoice_amount >= limit:
            return _review(
                f"blanket purchase order {po_label} has no control total; invoice "
                f"${invoice_amount:,.2f} is at or above the ${limit:,.2f} approval limit"
            )
        # Below the approval limit there is nothing for this control to compare
        # and no policy requiring a second signature.
        return None

    # Everything below this point is a state in which the comparison cannot be
    # performed. Each fails closed, and each runs before any arithmetic so that
    # no branch divides by zero or formats a non-number as currency.
    if po_amount is None:
        return _review(
            f"purchase order {po_label} carries no amount; cannot verify invoice against it"
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
