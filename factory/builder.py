"""Builder: implements the approved plan inside the allowed scope.

Phase 2's builder replays a scripted patch. The scope enforcement around it is
real: whatever the builder touches is checked against the work item afterwards,
from the git diff rather than from the builder's own account of itself.
"""

from __future__ import annotations

from factory.fake_builds import SCRIPTED_BUILDS
from factory.schemas import BuildResult, Plan, WorkItem

MODEL = "fake:scripted-builder"


class BuildError(RuntimeError):
    pass


def build(item: WorkItem, plan: Plan) -> BuildResult:
    scripted = SCRIPTED_BUILDS.get(item.id)
    if not scripted:
        raise BuildError(
            f"no scripted build for {item.id}; Phase 2's builder cannot invent a patch"
        )
    return scripted()
