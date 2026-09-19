"""Inspect a previous run.

uv run python -m factory.inspect                      # list runs
uv run python -m factory.inspect ACCT-001-20260919T...
"""

from __future__ import annotations

import argparse
import sys

from factory.paths import TRACES_DIR
from factory.trace import Trace


def list_runs() -> int:
    runs = sorted(p for p in TRACES_DIR.iterdir() if p.is_dir())
    if not runs:
        print("no runs yet")
        return 0
    for path in runs:
        trace = Trace(path.name)
        verdict = "?"
        try:
            result = trace.read_json("result.json")
            verdict = "ACCEPTED" if result.get("accepted") else str(result.get("state", "REJECTED"))
        except (FileNotFoundError, ValueError):
            verdict = "incomplete"
        print(f"{path.name}  {verdict}")
    return 0


def show(run_id: str) -> int:
    trace = Trace(run_id)
    if not trace.dir.exists():
        print(f"no such run: {run_id}", file=sys.stderr)
        return 1

    meta = trace.read_json("metadata.json") if (trace.dir / "metadata.json").exists() else {}
    print(f"run {run_id}")
    if meta:
        print(f"  task           {meta.get('task_id')}")
        print(f"  baseline sha   {meta.get('git_sha_before', '')[:10]}")
        print(f"  models         planner={meta.get('planner_model')}")
        print(f"                 builder={meta.get('builder_model')}")
        print(f"                 reviewer={meta.get('reviewer_model')}")
        print(f"  duration       {meta.get('duration_seconds')}s")
        print(f"  states         {' -> '.join(meta.get('states', []))}")

    if (trace.dir / "validation.json").exists():
        v = trace.read_json("validation.json")
        if v.get("benchmark"):
            b = v["benchmark"]
            print(
                f"  benchmark      {b['before']['passed']}/{b['before']['total']}"
                f" -> {b['after']['passed']}/{b['after']['total']}"
            )
        if v.get("target_case"):
            t = v["target_case"]
            print(
                f"  target case    {t['case']}  "
                f"{'PASS' if t['before'] else 'FAIL'} -> {'PASS' if t['after'] else 'FAIL'}"
            )
        print(f"  regressions    {', '.join(v.get('regressions') or []) or '(none)'}")

    if (trace.dir / "review.json").exists():
        r = trace.read_json("review.json")
        print(f"  reviewer       {r['decision']}: {r['summary']}")

    if (trace.dir / "result.json").exists():
        result = trace.read_json("result.json")
        print(f"  DECISION       {result.get('state')}")
        for reason in result.get("blocking_reasons") or []:
            print(f"    ! {reason}")

    print(f"  files          {', '.join(trace.present())}")
    if trace.missing():
        print(f"  MISSING        {', '.join(trace.missing())}")
    print(f"  path           {trace.dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect factory runs.")
    parser.add_argument("run_id", nargs="?", help="omit to list every run")
    args = parser.parse_args(argv)
    return show(args.run_id) if args.run_id else list_runs()


if __name__ == "__main__":
    sys.exit(main())
