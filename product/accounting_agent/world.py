"""The synthetic company, as the agent and the judges see it.

Loaded once and cached: every case in a sweep shares the same world text, so it
is also the stable prefix a prompt cache can work with.
"""

from __future__ import annotations

import functools
import pathlib

WORLD_DIR = pathlib.Path(__file__).resolve().parents[2] / "benchmark" / "world"


@functools.lru_cache(maxsize=1)
def world_context() -> str:
    company = (WORLD_DIR / "company.md").read_text()
    policies = (WORLD_DIR / "policies.yaml").read_text()
    accounts = (WORLD_DIR / "chart_of_accounts.csv").read_text()
    return "\n".join(
        [
            "# The company",
            "",
            company,
            "",
            "# Machine-readable policy",
            "",
            "```yaml",
            policies,
            "```",
            "",
            "# Chart of accounts",
            "",
            "```csv",
            accounts,
            "```",
        ]
    )
