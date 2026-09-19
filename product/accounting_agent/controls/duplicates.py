"""Block anything the ledger has already seen."""

from __future__ import annotations

from product.accounting_agent.controls.policies import policy
from product.accounting_agent.models import Action, ControlVerdict

NAME = "duplicates"


def check(case_input: dict, proposed: Action) -> ControlVerdict | None:
    if not policy("duplicates").get("block_on_ledger_match", True):
        return None

    ledger = case_input.get("ledger") or {}
    if not ledger:
        return None

    documents = [
        (case_input.get("invoice") or {}).get("number"),
        (case_input.get("open_invoice") or {}).get("number"),
    ]
    memo = (case_input.get("bank_line") or {}).get("memo") or ""

    for number, state in ledger.items():
        if number in documents or number in memo:
            return ControlVerdict(
                control=NAME,
                action=Action.REVIEW,
                reason=f"{number} already in the ledger ({state})",
            )
    return None
