"""Validate a work item without running the factory.

uv run python -m factory.validate_task factory/tasks/ACCT-001.yaml
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from factory.intake import IntakeError, check_scope, load_work_item
from factory.schemas import ScopeGuard


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a factory work item.")
    parser.add_argument("task", type=pathlib.Path)
    args = parser.parse_args(argv)

    try:
        item = load_work_item(args.task)
    except IntakeError as exc:
        print(f"INVALID  {exc}", file=sys.stderr)
        return 1

    problems = check_scope(item)
    guard = ScopeGuard(item.scope)

    print(f"{item.id}  {item.title}")
    print(f"  source            {item.source.type} / {item.source.case_id or '-'}")
    print(f"  severity          {item.business_impact.severity}")
    print(f"  may modify        {', '.join(item.scope.allowed_paths)}")
    print(f"  may not modify    {', '.join(item.scope.forbidden_paths) or '(nothing declared)'}")
    print(f"  acceptance        {len(item.acceptance_criteria)} criteria")
    print(f"  verification      {len(item.verification.commands)} command(s)")
    print(f"  regression policy max {item.regression_policy.max_new_failures} new failure(s)")

    # Every path the work item declares off-limits must actually be off-limits.
    # Derived from the work item rather than hard-coded, so this module never
    # needs to name the answer key it is protecting.
    leaks = [
        pattern
        for pattern in item.scope.forbidden_paths
        if guard.may_modify(pattern.replace("**", "probe").replace("*", "probe"))
    ]
    print(f"  forbidden honoured{'':2}{'NO — ' + ', '.join(leaks) if leaks else 'yes'}")
    problems += [f"forbidden path {p} is reachable by the allowed scope" for p in leaks]

    if problems:
        print("\nINVALID")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("\nVALID — accepted for planning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
