"""Send likely fixed assets to a human instead of expensing them."""

from __future__ import annotations

from product.accounting_agent.controls.policies import policy
from product.accounting_agent.models import Action, ControlVerdict

NAME = "capitalization"


def check(case_input: dict, proposed: Action) -> ControlVerdict | None:
    invoice = case_input.get("invoice") or {}
    amount, description = invoice.get("amount"), invoice.get("description")

    # A described purchase is one we can reason about; an amount alone is not
    # enough to call something an asset.
    if amount is None or not description:
        return None

    threshold = policy("capitalization")["threshold"]
    if amount < threshold:
        return None

    return ControlVerdict(
        control=NAME,
        action=Action.REVIEW,
        reason=f"${amount:,.2f} is at or above the ${threshold:,} capitalization threshold",
    )
