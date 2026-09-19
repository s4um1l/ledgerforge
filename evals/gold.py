"""The only module permitted to read `benchmark/gold/`.

Nothing in `factory/` may import this. Phase 2's context resolver enforces that
from the other side; keeping the read in exactly one place is what makes the
rule checkable at all.
"""

from __future__ import annotations

import json
import pathlib

from evals.paths import GOLD_DIR
from evals.schemas import GoldAnswer

ANSWERS_FILE = GOLD_DIR / "answers.jsonl"


def load_gold(path: pathlib.Path | None = None) -> dict[str, GoldAnswer]:
    """Load gold answers keyed by case id."""
    path = path or ANSWERS_FILE
    if not path.exists():
        raise FileNotFoundError(f"no gold answers at {path}")

    answers: dict[str, GoldAnswer] = {}
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            answer = GoldAnswer.model_validate(json.loads(line))
        except Exception as exc:  # noqa: BLE001 - want the line number in the message
            raise ValueError(f"{path}:{lineno} is not a valid gold answer: {exc}") from exc
        if answer.case_id in answers:
            raise ValueError(f"{path}:{lineno} duplicates case {answer.case_id}")
        answers[answer.case_id] = answer
    return answers
