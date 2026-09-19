"""Refuse to post into a period the document does not belong to."""

from __future__ import annotations

from product.accounting_agent.controls.policies import policy
from product.accounting_agent.models import Action, ControlVerdict

NAME = "month_end_cutoff"


def check(case_input: dict, proposed: Action) -> ControlVerdict | None:
    if policy("month_end_cutoff").get("allow_post_period_posting", False):
        return None

    period = case_input.get("period")
    date = (case_input.get("invoice") or {}).get("date")
    if not period or not date:
        return None

    # Both are ISO, so a prefix comparison is enough: "2026-10-02" > "2026-09".
    if date[:7] > period[:7]:
        return ControlVerdict(
            control=NAME,
            action=Action.REJECT,
            reason=f"document dated {date} cannot post to {period}",
        )
    return None
