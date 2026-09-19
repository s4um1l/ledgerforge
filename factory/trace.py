"""Trace writer. Every run leaves a directory you can read a year later.

The trace is the product of a factory run at least as much as the patch is: it is
what lets someone reconstruct why a change was accepted without rerunning
anything, and what makes "an agent fixed it" into evidence.
"""

from __future__ import annotations

import json
import pathlib
import shutil

from pydantic import BaseModel

from factory.paths import TRACES_DIR

FILES = (
    "task.yaml",
    "context.json",
    "plan.json",
    "builder.json",
    "diff.patch",
    "validation.json",
    "review.json",
    "result.json",
    "metadata.json",
)


class Trace:
    def __init__(self, run_id: str, root: pathlib.Path | None = None) -> None:
        self.run_id = run_id
        self.dir = (root or TRACES_DIR) / run_id
        self.dir.mkdir(parents=True, exist_ok=True)

    def write_model(self, name: str, model: BaseModel) -> pathlib.Path:
        return self.write_json(name, model.model_dump(mode="json"))

    def write_json(self, name: str, payload: dict | list) -> pathlib.Path:
        path = self.dir / name
        path.write_text(json.dumps(payload, indent=2) + "\n")
        return path

    def write_text(self, name: str, text: str) -> pathlib.Path:
        path = self.dir / name
        path.write_text(text)
        return path

    def copy_in(self, name: str, source: pathlib.Path) -> pathlib.Path:
        path = self.dir / name
        shutil.copyfile(source, path)
        return path

    def read_json(self, name: str) -> dict:
        return json.loads((self.dir / name).read_text())

    def present(self) -> list[str]:
        return [name for name in FILES if (self.dir / name).exists()]

    def missing(self) -> list[str]:
        return [name for name in FILES if not (self.dir / name).exists()]
