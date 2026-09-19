"""Hard controls: deterministic code, no model, no probabilities.

A control may only ever make the system *less* autonomous. It can take AUTO down
to REVIEW or REJECT; it can never promote a decision. That asymmetry is what makes
the layer safe to add to: a new control cannot increase autonomous risk.

The registry is explicit rather than auto-discovered, so adding a control is a
visible diff a reviewer can read.
"""

from __future__ import annotations

from collections.abc import Callable

from product.accounting_agent.controls import (
    capitalization,
    consistency,
    cutoff,
    duplicates,
)
from product.accounting_agent.models import SEVERITY, Action, ControlVerdict

Control = Callable[[dict, Action], ControlVerdict | None]

REGISTRY: list[Control] = [
    duplicates.check,
    capitalization.check,
    cutoff.check,
    consistency.check,
]


def apply_controls(case_input: dict, proposed: Action) -> tuple[Action, list[ControlVerdict]]:
    """Run every control. The most restrictive verdict wins."""
    verdicts = [v for v in (control(case_input, proposed) for control in REGISTRY) if v]
    action = proposed
    for verdict in verdicts:
        if SEVERITY[verdict.action] > SEVERITY[action]:
            action = verdict.action
    return action, verdicts
