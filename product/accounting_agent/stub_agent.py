"""A stand-in for the model-backed agent that Phase 5 builds.

Phase 2 needs a product that *actually changes behaviour when code changes*, so
the factory loop can be proved end to end with no model in it. This stub supplies
that: it takes the benchmark's fixed candidate action as though a frontier model
had proposed it, then runs the deterministic control layer over it.

The control layer is not a stand-in. It is the real thing, and it survives into
configuration C unchanged.
"""

from __future__ import annotations

import json
import pathlib

from product.accounting_agent.controls import apply_controls
from product.accounting_agent.models import Action, Decision

ARCHITECTURE = "stub_controls"
CASES_DIR = pathlib.Path(__file__).resolve().parents[2] / "benchmark" / "cases"


def load_cases(directory: pathlib.Path | None = None) -> list[dict]:
    """Read cases. The agent never sees gold answers."""
    directory = directory or CASES_DIR
    files = sorted(directory.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no case files in {directory}")
    return [json.loads(f.read_text()) for f in files]


def decide(case: dict) -> Decision:
    proposed = Action(case["candidate_action"])
    action, verdicts = apply_controls(case.get("input") or {}, proposed)
    return Decision(case_id=case["id"], action=action, proposed=proposed, verdicts=verdicts)


def decide_all(directory: pathlib.Path | None = None) -> list[Decision]:
    return [decide(case) for case in load_cases(directory)]


def write_run(path: pathlib.Path, directory: pathlib.Path | None = None) -> list[Decision]:
    decisions = decide_all(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(d.to_run_record(ARCHITECTURE)) for d in decisions) + "\n")
    return decisions
