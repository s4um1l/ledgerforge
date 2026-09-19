"""Product-side types.

`Action` is deliberately redefined here rather than imported from `evals`. The
thing being measured and the thing doing the measuring do not share types, so the
agent cannot reshape its own grading surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Action(StrEnum):
    AUTO = "AUTO"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


# Ordered by how much autonomy they grant. A control may only move a decision
# down this list, never up.
SEVERITY = {Action.AUTO: 0, Action.REVIEW: 1, Action.REJECT: 2}


@dataclass(frozen=True)
class ControlVerdict:
    """One deterministic control's opinion about a proposed action."""

    control: str
    action: Action
    reason: str


@dataclass
class Decision:
    """What the agent decided, and the audit trail for why."""

    case_id: str
    action: Action
    proposed: Action
    verdicts: list[ControlVerdict] = field(default_factory=list)

    @property
    def was_downgraded(self) -> bool:
        return SEVERITY[self.action] > SEVERITY[self.proposed]

    def to_run_record(self, architecture: str) -> dict:
        return {
            "case_id": self.case_id,
            "architecture": architecture,
            "action": str(self.action),
            "controls_fired": [v.control for v in self.verdicts],
        }
