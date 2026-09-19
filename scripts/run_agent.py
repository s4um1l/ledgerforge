"""Run the agent over the benchmark and write a run file.

    uv run python scripts/run_agent.py --out results/runs/current.jsonl

Grading is a separate command on purpose: this process never reads gold.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from product.accounting_agent.stub_agent import write_run  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the accounting agent over the benchmark.")
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=pathlib.Path("results/runs/current.jsonl"),
        help="where to write the run (default: results/runs/current.jsonl)",
    )
    args = parser.parse_args(argv)

    decisions = write_run(args.out)
    downgraded = sum(1 for d in decisions if d.was_downgraded)
    print(f"{len(decisions)} cases -> {args.out}")
    print(f"{downgraded} decision(s) restricted by a hard control")
    return 0


if __name__ == "__main__":
    sys.exit(main())
