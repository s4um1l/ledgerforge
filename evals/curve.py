"""The automation/risk curve.

Sweeps the policy engine's strictness over judgments that were already paid for
and re-routes each case offline. No model is called, which is the point: the
curve is a property of the thresholds, and thresholds are config.

    uv run python -m evals.curve

Two numbers per operating point:

    automation coverage    share of cases acted on with no human
    autonomous error rate  share of those actions that were wrong

The second is the one that gets someone fired, so it is plotted against the
first rather than reported alone.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import yaml

from evals.gold import load_gold
from evals.paths import RESULTS_DIR
from evals.schemas import Action as EvalAction
from product.accounting_agent.judges.base import Judgments
from product.accounting_agent.models import Action, ControlVerdict
from product.accounting_agent.policy import CONFIG, route

ARCHITECTURES = {"A": "llm_only", "B": "llm_judge", "C": "jev_guard"}


def operating_point(details: list[dict], letter: str, gold: dict, strictness: float) -> dict:
    """Route every case at one strictness setting and score the outcome."""
    automated = wrong_automated = correct = reviewed = rejected = 0

    for detail in details:
        result = detail["results"].get(letter)
        if not result:
            continue
        proposed = Action(detail["proposal"]["action"])
        judgments = None
        if result.get("judgments"):
            judgments = Judgments(
                values=result["judgments"]["values"], judge=result["judgments"]["judge"]
            )
        verdicts = [
            ControlVerdict(control=v["control"], action=Action(v["action"]), reason=v["reason"])
            for v in result.get("verdicts", [])
        ]
        routed = route(proposed, judgments, verdicts=verdicts, strictness=strictness).action

        expected = EvalAction(str(gold[detail["case_id"]].gold_action))
        matched = str(routed) == str(expected)
        correct += matched
        if routed is Action.AUTO:
            automated += 1
            wrong_automated += 0 if matched else 1
        elif routed is Action.REVIEW:
            reviewed += 1
        else:
            rejected += 1

    total = len(details)
    return {
        "strictness": strictness,
        "automation_coverage": round(automated / total, 4) if total else 0.0,
        "autonomous_error_rate": round(wrong_automated / automated, 4) if automated else 0.0,
        "wrong_automated": wrong_automated,
        "automated": automated,
        "human_review_rate": round(reviewed / total, 4) if total else 0.0,
        "reject_rate": round(rejected / total, 4) if total else 0.0,
        "task_correctness": round(correct / total, 4) if total else 0.0,
        "total": total,
    }


def format_curve(curves: dict) -> str:
    lines = ["", "=" * 74, "  AUTOMATION / RISK CURVE", "=" * 74]
    for name, points in curves.items():
        lines += [
            "",
            f"  {name}",
            "",
            f"  {'strictness':>10} {'coverage':>10} {'errors/auto':>12} {'wrong':>7} "
            f"{'review':>8} {'correct':>8}",
        ]
        for p in points:
            ratio = f"{p['wrong_automated']}/{p['automated']}"
            lines.append(
                f"  {p['strictness']:>10.2f} {p['automation_coverage']:>9.1%} "
                f"{p['autonomous_error_rate']:>11.1%} {ratio:>7} "
                f"{p['human_review_rate']:>7.1%} {p['task_correctness']:>7.1%}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep policy thresholds over cached judgments.")
    parser.add_argument("--detail", type=pathlib.Path, default=RESULTS_DIR / "phase7")
    parser.add_argument("--repetition", type=int, default=1)
    parser.add_argument("--out", type=pathlib.Path, default=RESULTS_DIR / "phase7" / "curve.json")
    args = parser.parse_args(argv)

    path = args.detail / f"detail_rep{args.repetition}.json"
    if not path.exists():
        print(f"no detail file at {path}; run scripts/run_architecture.py first", file=sys.stderr)
        return 1

    details = json.loads(path.read_text())
    gold = load_gold()
    strictnesses = yaml.safe_load(CONFIG.read_text())["sweep"]["strictness"]

    curves = {}
    for letter, name in ARCHITECTURES.items():
        if not any(letter in d["results"] for d in details):
            continue
        # Architecture A has no judgment layer, so its single point is the whole
        # line: there is nothing to sweep, which is itself the finding.
        points = [1.0] if letter == "A" else strictnesses
        curves[f"{letter} — {name}"] = [operating_point(details, letter, gold, s) for s in points]

    print(format_curve(curves))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(curves, indent=2) + "\n")
    print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
