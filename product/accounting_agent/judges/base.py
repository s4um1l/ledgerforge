"""What a judge is, and what every judge must return.

Both judges answer the same five questions, phrased identically, about the same
state. That is the whole design of Evaluation 1: if the two received different
criteria, the comparison would measure the prompt, not the judge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from product.accounting_agent.judges.questions import ATOMIC_QUESTIONS, LABELS, answerable
from product.accounting_agent.models import Action

# A question whose evidence is absent is not unknown — it is answered by the
# absence. "Does the ledger already contain this document?" with no ledger at all
# is False, not 0.5. Phase 3.5 measured what happens if you ask anyway: 0.50-0.62,
# a number a threshold will happily act on. Both judges apply this identically.
PRIOR_WHEN_UNANSWERABLE = {"possible_duplicate": 0.0}


@dataclass
class Judgments:
    """Five probabilities, plus what it cost to get them."""

    values: dict[str, float]
    judge: str
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    cached: bool = False
    assumed: list[str] = field(default_factory=list)
    confidence: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        missing = [label for label in LABELS if label not in self.values]
        if missing:
            raise ValueError(f"judge {self.judge} returned no value for: {', '.join(missing)}")

    def __getitem__(self, label: str) -> float:
        return self.values[label]

    def to_dict(self) -> dict:
        return {
            "judge": self.judge,
            "values": self.values,
            "confidence": self.confidence,
            "assumed": self.assumed,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "cached": self.cached,
        }


class Judge(Protocol):
    name: str

    def judge(self, case: dict, candidate: Action) -> Judgments: ...


def split_questions(case_input: dict) -> tuple[list, dict[str, float]]:
    """Which questions to ask, and which are answered by absent evidence."""
    ask, assumed = [], {}
    for question in ATOMIC_QUESTIONS:
        if answerable(question, case_input):
            ask.append(question)
        else:
            assumed[question.label] = PRIOR_WHEN_UNANSWERABLE.get(question.label, 0.5)
    return ask, assumed
