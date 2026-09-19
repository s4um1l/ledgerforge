"""Loads the customer's machine-readable policy.

Controls read their thresholds from here. Nothing hard-codes a number, so
sweeping thresholds is a config change rather than a code change.
"""

from __future__ import annotations

import functools
import pathlib

import yaml

POLICY_FILE = pathlib.Path(__file__).resolve().parents[3] / "benchmark" / "world" / "policies.yaml"


@functools.lru_cache(maxsize=1)
def load_policies(path: pathlib.Path | None = None) -> dict:
    path = path or POLICY_FILE
    if not path.exists():
        raise FileNotFoundError(f"no policy file at {path}")
    return yaml.safe_load(path.read_text())


def policy(name: str) -> dict:
    policies = load_policies()
    if name not in policies:
        raise KeyError(f"no policy section named {name!r} in {POLICY_FILE.name}")
    return policies[name]
