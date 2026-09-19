"""Paths the factory is allowed to know about.

The factory may read the product, the benchmark cases and the synthetic world.
It may not read the answers. That directory is not named here, and a test in
`evals/tests/test_gold_boundary.py` fails if any module under `factory/` so much
as mentions it.
"""

from __future__ import annotations

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

PRODUCT_DIR = REPO_ROOT / "product"
CASES_DIR = REPO_ROOT / "benchmark" / "cases"
WORLD_DIR = REPO_ROOT / "benchmark" / "world"
TASKS_DIR = REPO_ROOT / "factory" / "tasks"
TRACES_DIR = REPO_ROOT / "factory" / "traces"
RESULTS_DIR = REPO_ROOT / "results"
PROMPTS_DIR = REPO_ROOT / "prompts"
