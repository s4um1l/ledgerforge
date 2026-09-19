"""The five atomic judgments, as one shared question set.

Both judges — the Jev decision model and the structured-output LLM judge — are
asked *these exact strings*. Evaluation 1 is only a fair comparison if the two
receive identical criteria, so the phrasings live here rather than inside either
judge, and neither judge may reword them.

No SDK is imported. A question is text plus which primitive answers it; Phase 6
wires that to `typesafe_sdk.Noul` on one side and a JSON schema on the other.

## Why the phrasings look pedantic

Measured in the Phase 3.5 smoke test, on a case where a $4,200 purchase order and
a $4,200 invoice from the same vendor plainly agree:

    "agree on vendor, amount, dates and terms"      -> 0.48   uninformative
    "considering only the fields present, agree?"    -> 0.95   correct
    "do the amounts agree?"                          -> 0.99   correct
    "contradict on any field both of them state?"    -> 0.03   correct

A question that names fields the case does not contain is answered against the
missing fields too, and the result collapses toward 0.5. That is not the model
hedging badly — it is the question weighing four factors at once, which the
decision model is explicitly documented not to do. Every phrasing below asks
about one thing, and about evidence the case actually carries.

Keep the label *names* stable: `benchmark/gold/answers.jsonl` is keyed on them.
Phrasings may be improved; names may not, without a benchmark version bump.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Primitive(StrEnum):
    """Which answer shape a question takes.

    Observed on the wire in Phase 3.5, not read from documentation:

        noul   -> {"type": "noul", "noul": 0.0-1.0}          no confidence field
        choice -> {"choice", "probabilities", "confidence"}
        score  -> {"score", "probabilities", "confidence", "legend"}
    """

    NOUL = "noul"
    CHOICE = "choice"
    SCORE = "score"


@dataclass(frozen=True)
class Question:
    label: str
    primitive: Primitive
    instructions: str
    depends_on: tuple[str, ...] = ()
    """Evidence the case must carry for this question to be answerable.

    A question whose evidence is absent does not return "unknown" — it returns a
    number near the middle, which a threshold will happily act on. Recording the
    dependency lets the judge decline to ask rather than collect a meaningless
    probability.
    """


# The five atomic labels, in the order the gold answers list them.
ATOMIC_QUESTIONS: tuple[Question, ...] = (
    Question(
        label="evidence_sufficient",
        primitive=Primitive.NOUL,
        instructions=(
            "Is the evidence attached to this case enough to support the proposed "
            "action, without a person needing to find another document?"
        ),
    ),
    Question(
        label="sources_consistent",
        primitive=Primitive.NOUL,
        instructions=(
            "Considering only the fields that appear in more than one of these "
            "documents, do the documents agree with each other?"
        ),
    ),
    Question(
        label="candidate_supported",
        primitive=Primitive.NOUL,
        instructions=("Does the stated company policy permit the proposed action on this case?"),
    ),
    Question(
        label="possible_duplicate",
        primitive=Primitive.NOUL,
        instructions=(
            "Does the ledger shown in this case already contain the document being recorded?"
        ),
        # Without a ledger there is nothing to be a duplicate of. Asked anyway,
        # this returned 0.50-0.62 on cases carrying no ledger at all in the
        # Phase 3.5 smoke test — a number that means nothing and thresholds fine.
        depends_on=("ledger",),
    ),
    Question(
        label="requires_human_review",
        primitive=Primitive.NOUL,
        instructions=(
            "Does the stated company policy require a person to approve this action "
            "before it is recorded?"
        ),
    ),
)

BY_LABEL = {q.label: q for q in ATOMIC_QUESTIONS}
LABELS = tuple(q.label for q in ATOMIC_QUESTIONS)


def answerable(question: Question, case_input: dict) -> bool:
    """Whether the case carries the evidence this question needs."""
    return all(key in case_input for key in question.depends_on)
