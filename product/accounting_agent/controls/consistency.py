"""Do not automate when the evidence contradicts itself."""

from __future__ import annotations

from product.accounting_agent.models import Action, ControlVerdict

NAME = "source_consistency"


def check(case_input: dict, proposed: Action) -> ControlVerdict | None:
    commentary = case_input.get("commentary")
    if isinstance(commentary, list) and len(commentary) > 1:
        return ControlVerdict(
            control=NAME,
            action=Action.REVIEW,
            reason=f"{len(commentary)} conflicting explanations for the same figure",
        )
    return None
