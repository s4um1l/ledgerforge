"""Run the factory over one work item.

    uv run python -m factory.run factory/tasks/ACCT-001.yaml
    uv run python -m factory.run factory/tasks/ACCT-001.yaml --dry-run

Exit code 0 means ACCEPTED. Anything else means the change was not accepted, which
is a successful run of the factory and an unsuccessful change.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from factory.intake import IntakeError
from factory.orchestrator import FactoryError, FactoryRun, format_decision


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the software factory over a work item.")
    parser.add_argument("task", type=pathlib.Path)
    parser.add_argument("--dry-run", action="store_true", help="stop after planning")
    parser.add_argument(
        "--keep-on-reject",
        action="store_true",
        help="leave a rejected change in the working tree instead of reverting it",
    )
    parser.add_argument(
        "--builder",
        choices=["scripted", "claude-code"],
        help="which builder to use (default: $FACTORY_BUILDER, else scripted)",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="run even with uncommitted changes (the diff will not be trustworthy)",
    )
    args = parser.parse_args(argv)

    run = FactoryRun(
        args.task,
        dry_run=args.dry_run,
        keep_on_reject=args.keep_on_reject,
        require_clean_tree=not args.allow_dirty,
        builder_backend=args.builder,
    )

    try:
        decision = run.execute()
    except (IntakeError, FactoryError) as exc:
        print(f"\nFACTORY HALTED: {exc}", file=sys.stderr)
        if run.trace:
            print(f"trace: {run.trace.dir}", file=sys.stderr)
        return 2

    assert run.trace is not None
    print(format_decision(decision, run.trace, run.validation))
    if args.dry_run:
        return 0
    return 0 if decision.accepted else 1


if __name__ == "__main__":
    sys.exit(main())
