"""Git, wrapped narrowly. The factory captures evidence; it never rewrites history."""

from __future__ import annotations

import pathlib
import subprocess

from factory.paths import REPO_ROOT


class GitError(RuntimeError):
    pass


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def head_sha() -> str:
    return _git("rev-parse", "HEAD").strip()


def is_clean() -> bool:
    return not _git("status", "--porcelain").strip()


def dirty_paths() -> list[str]:
    lines = _git("status", "--porcelain").splitlines()
    return sorted(line[3:].strip() for line in lines if line.strip())


def changed_paths() -> list[str]:
    """Paths differing from HEAD, including files the builder created.

    Untracked files are marked intent-to-add so they appear in the diff without
    their contents being staged.
    """
    _git("add", "--intent-to-add", "--all")
    names = _git("diff", "HEAD", "--name-only").splitlines()
    return sorted(n.strip() for n in names if n.strip())


def diff() -> str:
    _git("add", "--intent-to-add", "--all")
    return _git("diff", "HEAD")


def revert(modified: list[str], created: list[str]) -> None:
    """Undo a rejected build. The patch survives in the trace.

    Deliberately narrow: only the paths the builder reported are touched, so a
    rejected run can never delete work the factory did not create.
    """
    for rel in created:
        path = REPO_ROOT / rel
        if path.is_file():
            path.unlink()
    if created:
        _git("reset", "--quiet", "--", *created)
    restorable = [rel for rel in modified if rel not in created and (REPO_ROOT / rel).exists()]
    if restorable:
        _git("checkout", "--", *restorable)


def write_patch(path: pathlib.Path) -> str:
    patch = diff()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(patch)
    return patch
