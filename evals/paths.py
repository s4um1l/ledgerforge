"""Canonical repository paths, and the one boundary that matters.

`factory/` may read the product, the cases and the world. It may never read
`benchmark/gold/`. That rule is enforced here rather than trusted to prompts:
anything wanting gold has to go through `evals.gold`, which is the only module
that names `GOLD_DIR`.
"""

from __future__ import annotations

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

BENCHMARK_DIR = REPO_ROOT / "benchmark"
CASES_DIR = BENCHMARK_DIR / "cases"
WORLD_DIR = BENCHMARK_DIR / "world"
GOLD_DIR = BENCHMARK_DIR / "gold"

PRODUCT_DIR = REPO_ROOT / "product"
FIXTURES_DIR = REPO_ROOT / "evals" / "fixtures"
RESULTS_DIR = REPO_ROOT / "results"
TRACES_DIR = REPO_ROOT / "factory" / "traces"


class GoldAccessError(RuntimeError):
    """Raised when something outside the evaluator reaches for gold answers."""


def assert_not_gold(path: pathlib.Path) -> pathlib.Path:
    """Guard for any code path that must not touch answers."""
    resolved = pathlib.Path(path).resolve()
    if resolved == GOLD_DIR or GOLD_DIR in resolved.parents:
        raise GoldAccessError(
            f"{resolved} is under benchmark/gold/. Only the evaluator may read gold answers."
        )
    return resolved
