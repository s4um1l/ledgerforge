"""Context resolver: assemble the smallest useful package for a task.

Two rules:

1. Only files inside the work item's allowed scope, plus the domain policy and
   the failing case's input.
2. Reads are whitelisted, not blacklisted. `READABLE_ROOTS` lists the three trees
   the factory may look at; the answers live outside all of them, so they are
   unreachable rather than merely forbidden. A whitelist cannot be defeated by
   forgetting to add an entry to a blocklist.

Note that a work item's `forbidden_paths` is a *write* boundary. The factory reads
the failing case in order to understand it and is still forbidden to edit it.
"""

from __future__ import annotations

import json
import pathlib

from factory.paths import CASES_DIR, PRODUCT_DIR, PROMPTS_DIR, REPO_ROOT, WORLD_DIR
from factory.schemas import ContextFile, ContextPackage, FailureContext, ScopeGuard, WorkItem

MAX_FILE_BYTES = 40_000

# The only trees the factory may read. Everything else — including anything that
# could constitute an answer key — is outside the resolver's reach by construction.
READABLE_ROOTS = (PRODUCT_DIR, CASES_DIR, WORLD_DIR, PROMPTS_DIR)


class ContextError(RuntimeError):
    pass


def _assert_readable(path: pathlib.Path) -> pathlib.Path:
    resolved = path.resolve()
    if not any(root == resolved or root in resolved.parents for root in READABLE_ROOTS):
        raise ContextError(f"{resolved} is outside the readable roots; the factory may not read it")
    return resolved


def _read(path: pathlib.Path) -> ContextFile:
    _assert_readable(path)
    text = path.read_text()
    truncated = len(text) > MAX_FILE_BYTES
    return ContextFile(
        path=str(path.relative_to(REPO_ROOT)),
        contents=text[:MAX_FILE_BYTES],
        truncated=truncated,
    )


def resolve_files(item: WorkItem) -> tuple[list[ContextFile], list[str]]:
    """Every existing file inside the allowed scope, minus anything forbidden."""
    guard = ScopeGuard(item.scope)
    files: list[ContextFile] = []
    excluded: list[str] = []

    for pattern in item.scope.allowed_paths:
        base = pattern.split("*", 1)[0].rstrip("/")
        root = REPO_ROOT / base
        if not root.exists():
            continue
        candidates = sorted(root.rglob("*")) if root.is_dir() else [root]
        for path in candidates:
            if not path.is_file() or path.suffix not in {".py", ".yaml", ".yml", ".md"}:
                continue
            rel = str(path.relative_to(REPO_ROOT))
            if "__pycache__" in rel:
                continue
            if not guard.may_modify(rel):
                excluded.append(rel)
                continue
            files.append(_read(path))

    return files, sorted(set(excluded))


def resolve_case_input(item: WorkItem) -> dict | None:
    """The failing case's *input*, and only its input.

    Reading the case is both allowed and necessary — you cannot diagnose a failure
    you are not permitted to look at. Editing it is forbidden, which the validator
    enforces afterwards against the actual diff.
    """
    case_id = item.target_case_id
    if not case_id:
        return None

    path = CASES_DIR / f"{case_id}.json"
    rel = str(path.relative_to(REPO_ROOT))
    if not path.exists():
        raise ContextError(f"work item names case {case_id} but {rel} does not exist")

    case = json.loads(path.read_text())
    return {
        "id": case.get("id"),
        "category": case.get("category"),
        "summary": case.get("summary"),
        "input": case.get("input"),
        "candidate_action": case.get("candidate_action"),
    }


def resolve_domain_docs(guard: ScopeGuard) -> list[ContextFile]:
    docs: list[ContextFile] = []
    for path in sorted(WORLD_DIR.glob("*")):
        if not path.is_file() or path.suffix not in {".yaml", ".yml", ".md", ".csv"}:
            continue
        if guard.is_forbidden(str(path.relative_to(REPO_ROOT))):
            continue
        docs.append(_read(path))
    return docs


def resolve(item: WorkItem) -> ContextPackage:
    guard = ScopeGuard(item.scope)
    files, excluded = resolve_files(item)
    if not files:
        raise ContextError(
            "no readable files inside the allowed scope: " + ", ".join(item.scope.allowed_paths)
        )

    package = ContextPackage(
        task_id=item.id,
        intent=item.intent,
        files=files,
        domain_docs=resolve_domain_docs(guard),
        failure=FailureContext(
            case_id=item.target_case_id,
            actual=item.problem.actual_behavior,
            expected=item.problem.expected_behavior,
            case_input=resolve_case_input(item),
        ),
        excluded=excluded,
    )

    # Belt and braces: every path in the package must sit under a readable root.
    for entry in package.files + package.domain_docs:
        _assert_readable(REPO_ROOT / entry.path)

    return package
