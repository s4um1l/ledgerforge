"""Refuse to post into a period the document does not belong to."""

from __future__ import annotations

from product.accounting_agent.controls import service_period
from product.accounting_agent.controls.policies import policy
from product.accounting_agent.models import Action, ControlVerdict

NAME = "month_end_cutoff"


def _work_completed(case_input: dict) -> str | None:
    """The stated completion date, read defensively; anything odd is no signal."""
    supporting = case_input.get("supporting") or {}
    if not isinstance(supporting, dict):
        return None
    return supporting.get("work_completed")


def check(case_input: dict, proposed: Action) -> ControlVerdict | None:
    settings = policy("month_end_cutoff")
    if settings.get("allow_post_period_posting", False):
        return None

    period = case_input.get("period")
    date = (case_input.get("invoice") or {}).get("date")
    if not period or not date:
        return None

    # Both are ISO, so a prefix comparison is enough: "2026-10-02" > "2026-09".
    if date[:7] > period[:7]:
        # The document was written after the cutoff. That alone does not say when
        # the work was done, and policy accrues work performed inside the period
        # rather than rejecting it. Only a stated service period ending inside the
        # month being closed earns that; everything else falls through.
        span = service_period.months(case_input)
        if settings.get("accrue_late_invoices_for_work_in_period", False) and span:
            start, end = span
            if end == period[:7] and start <= period[:7]:
                completed = service_period.month(_work_completed(case_input))
                if completed is None or completed <= period[:7]:
                    return None
                # The evidence contradicts the claim: keep the rejection.
                return ControlVerdict(
                    control=NAME,
                    action=Action.REJECT,
                    reason=(
                        f"document dated {date} claims service period "
                        f"{start}..{end}, but the work completed "
                        f"{_work_completed(case_input)}, after {period}"
                    ),
                )
        return ControlVerdict(
            control=NAME,
            action=Action.REJECT,
            reason=f"document dated {date} cannot post to {period}",
        )
    return None
