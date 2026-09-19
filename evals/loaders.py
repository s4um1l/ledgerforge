"""Loaders for everything that is *not* an answer: cases and run records."""

from __future__ import annotations

import json
import pathlib

from evals.paths import CASES_DIR, assert_not_gold
from evals.schemas import Case, RunRecord


def load_cases(path: pathlib.Path | None = None) -> dict[str, Case]:
    """Load benchmark cases keyed by id. Never reads gold."""
    directory = assert_not_gold(path or CASES_DIR)
    files = sorted(directory.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no case files in {directory}")

    cases: dict[str, Case] = {}
    for file in files:
        case = Case.model_validate(json.loads(file.read_text()))
        if case.id in cases:
            raise ValueError(f"{file} duplicates case id {case.id}")
        cases[case.id] = case
    return cases


def load_run(path: pathlib.Path) -> list[RunRecord]:
    """Load one run's decisions from a .jsonl file."""
    path = assert_not_gold(path)
    if not path.exists():
        raise FileNotFoundError(f"no run file at {path}")

    records: list[RunRecord] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            record = RunRecord.model_validate(json.loads(line))
        except Exception as exc:  # noqa: BLE001 - want the line number in the message
            raise ValueError(f"{path}:{lineno} is not a valid run record: {exc}") from exc
        if record.case_id in seen:
            raise ValueError(f"{path}:{lineno} duplicates case {record.case_id}")
        seen.add(record.case_id)
        records.append(record)
    return records
