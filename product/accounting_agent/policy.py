"""The policy engine: neither model executes, this routes.

Two rules hold no matter which architecture is running:

1. Nothing may *increase* autonomy. The model proposes, controls and judgments
   may only restrict. A REVIEW never becomes an AUTO because a judge felt good
   about it.
2. Thresholds come from config, never from a prompt. That is what makes the
   automation/risk curve producible — sweep the file, re-route the same cached
   judgments, no model calls at all.
"""

from __future__ import annotations

import functools
import pathlib
from dataclasses import dataclass, field

import yaml

from product.accounting_agent.judges.base import Judgments
from product.accounting_agent.models import SEVERITY, Action, ControlVerdict

CONFIG = pathlib.Path(__file__).resolve().parents[2] / "config" / "automation.yaml"


@functools.lru_cache(maxsize=1)
def load_config(path: pathlib.Path | None = None) -> dict:
    return yaml.safe_load((path or CONFIG).read_text())


def thresholds(strictness: float = 1.0) -> dict[str, float]:
    """Scale the configured thresholds toward permissive.

    `strictness` 1.0 is the configured operating point. 0.0 disables every
    judgment gate, so the only things that can still restrict are the model's own
    proposal and the deterministic controls. Sweeping it between the two traces
    the automation/risk curve.
    """
    base = load_config()["thresholds"]
    return {
        # "at least this confident" gates relax toward 0
        "evidence_sufficient_min": base["evidence_sufficient_min"] * strictness,
        "candidate_supported_min": base["candidate_supported_min"] * strictness,
        "sources_consistent_min": base["sources_consistent_min"] * strictness,
        # "no more than this suspicious" gates relax toward 1
        "possible_duplicate_max": 1.0 - (1.0 - base["possible_duplicate_max"]) * strictness,
        "requires_human_review_max": 1.0 - (1.0 - base["requires_human_review_max"]) * strictness,
    }


@dataclass
class Routing:
    action: Action
    proposed: Action
    reasons: list[str] = field(default_factory=list)
    control_action: Action | None = None

    @property
    def restricted(self) -> bool:
        return SEVERITY[self.action] > SEVERITY[self.proposed]


def _restrict(current: Action, candidate: Action) -> Action:
    return candidate if SEVERITY[candidate] > SEVERITY[current] else current


def route(
    proposed: Action,
    judgments: Judgments | None = None,
    verdicts: list[ControlVerdict] | None = None,
    strictness: float = 1.0,
) -> Routing:
    """Combine a proposal, deterministic controls and probabilistic judgments."""
    action, reasons = proposed, []
    control_action: Action | None = None

    for verdict in verdicts or []:
        control_action = _restrict(control_action or Action.AUTO, verdict.action)
        if SEVERITY[verdict.action] > SEVERITY[action]:
            reasons.append(f"control {verdict.control}: {verdict.reason}")
        action = _restrict(action, verdict.action)

    if judgments is not None:
        limits = thresholds(strictness)
        gates = [
            ("evidence_sufficient", "<", limits["evidence_sufficient_min"]),
            ("candidate_supported", "<", limits["candidate_supported_min"]),
            ("sources_consistent", "<", limits["sources_consistent_min"]),
            ("possible_duplicate", ">", limits["possible_duplicate_max"]),
            ("requires_human_review", ">", limits["requires_human_review_max"]),
        ]
        for label, direction, limit in gates:
            value = judgments[label]
            tripped = value < limit if direction == "<" else value > limit
            if tripped:
                reasons.append(f"{label}={value:.2f} {direction} {limit:.2f}")
                action = _restrict(action, Action.REVIEW)

    return Routing(action=action, proposed=proposed, reasons=reasons, control_action=control_action)
