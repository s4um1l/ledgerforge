"""The policy engine's invariants."""

import pytest

from product.accounting_agent.judges.base import Judgments
from product.accounting_agent.models import SEVERITY, Action, ControlVerdict
from product.accounting_agent.policy import route, thresholds

CONFIDENT = {
    "evidence_sufficient": 0.99,
    "sources_consistent": 0.99,
    "candidate_supported": 0.99,
    "possible_duplicate": 0.01,
    "requires_human_review": 0.01,
}


def judgments(**overrides) -> Judgments:
    return Judgments(values={**CONFIDENT, **overrides}, judge="test")


def test_a_confident_judgment_leaves_an_auto_alone():
    assert route(Action.AUTO, judgments()).action is Action.AUTO


@pytest.mark.parametrize(
    "override",
    [
        {"evidence_sufficient": 0.5},
        {"candidate_supported": 0.5},
        {"sources_consistent": 0.1},
        {"possible_duplicate": 0.99},
        {"requires_human_review": 0.99},
    ],
)
def test_each_gate_can_stop_automation_alone(override):
    assert route(Action.AUTO, judgments(**override)).action is Action.REVIEW


def test_nothing_may_increase_autonomy():
    """The invariant the whole architecture rests on."""
    confident = judgments()
    for proposed in Action:
        result = route(proposed, confident)
        assert SEVERITY[result.action] >= SEVERITY[proposed]


def test_a_control_outranks_a_confident_judgment():
    verdict = ControlVerdict(control="duplicates", action=Action.REJECT, reason="already posted")
    result = route(Action.AUTO, judgments(), verdicts=[verdict])
    assert result.action is Action.REJECT


def test_strictness_zero_disables_the_judgment_gates_only():
    doubtful = judgments(evidence_sufficient=0.0, requires_human_review=1.0)
    assert route(Action.AUTO, doubtful, strictness=1.0).action is Action.REVIEW
    assert route(Action.AUTO, doubtful, strictness=0.0).action is Action.AUTO

    # ...but a control still stops it, because controls are not probabilistic.
    verdict = ControlVerdict(control="cutoff", action=Action.REJECT, reason="closed period")
    assert route(Action.AUTO, doubtful, verdicts=[verdict], strictness=0.0).action is Action.REJECT


def test_thresholds_move_monotonically_with_strictness():
    strict, loose = thresholds(1.0), thresholds(0.5)
    assert loose["evidence_sufficient_min"] < strict["evidence_sufficient_min"]
    assert loose["possible_duplicate_max"] > strict["possible_duplicate_max"]
    assert thresholds(0.0)["evidence_sufficient_min"] == 0.0
    assert thresholds(0.0)["requires_human_review_max"] == 1.0


def test_routing_records_why_it_restricted():
    result = route(Action.AUTO, judgments(requires_human_review=0.95))
    assert result.restricted
    assert any("requires_human_review" in r for r in result.reasons)
