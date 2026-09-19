"""Content-addressed cache for model calls.

Every phase from here on runs the same cases repeatedly: three repetitions of
three architectures, a judge comparison, and a rerun after the factory patches
something. Paying twice for the same call buys nothing, and worse, it makes a
rerun non-deterministic — an architecture comparison whose candidate actions
drift between runs is not a controlled experiment.

The key hashes everything that could change the answer. A missed field means a
silent stale read, so it is deliberately over-inclusive.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

CACHE_DIR = pathlib.Path(__file__).resolve().parents[2] / "results" / "cache"


def key_for(**parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def read(namespace: str, key: str) -> dict | None:
    path = CACHE_DIR / namespace / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def write(namespace: str, key: str, payload: dict) -> pathlib.Path:
    path = CACHE_DIR / namespace / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    return path


def count(namespace: str) -> int:
    directory = CACHE_DIR / namespace
    return len(list(directory.glob("*.json"))) if directory.exists() else 0
