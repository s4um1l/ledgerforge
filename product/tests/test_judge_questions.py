"""The question set is shared contract, so its shape is worth pinning."""

from product.accounting_agent.judges.questions import (
    ATOMIC_QUESTIONS,
    BY_LABEL,
    LABELS,
    Primitive,
    answerable,
)


def test_the_five_labels_match_the_benchmark_keys():
    assert LABELS == (
        "evidence_sufficient",
        "sources_consistent",
        "candidate_supported",
        "possible_duplicate",
        "requires_human_review",
    )


def test_every_atomic_label_is_a_noul():
    """Each is a single true/false statement, so each is one probability."""
    assert all(q.primitive is Primitive.NOUL for q in ATOMIC_QUESTIONS)


def test_no_question_bundles_several_factors():
    """Measured: a multi-factor question collapses toward 0.5 (see module docstring)."""
    for question in ATOMIC_QUESTIONS:
        text = question.instructions.lower()
        assert " and " not in text.replace("company policy", ""), (
            f"{question.label} may be weighing more than one factor: {question.instructions}"
        )


def test_duplicate_detection_declares_its_evidence_dependency():
    assert BY_LABEL["possible_duplicate"].depends_on == ("ledger",)


def test_answerable_refuses_a_question_whose_evidence_is_missing():
    duplicate = BY_LABEL["possible_duplicate"]
    assert not answerable(duplicate, {"invoice": {"amount": 100}})
    assert answerable(duplicate, {"invoice": {"amount": 100}, "ledger": {}})


def test_questions_with_no_dependency_are_always_answerable():
    assert answerable(BY_LABEL["evidence_sufficient"], {})
