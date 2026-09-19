"""Run one or more architectures over the frozen benchmark.

    A  llm_only    case -> model -> action
    B  llm_judge   case -> model -> candidate -> LLM judge -> policy engine
    C  jev_guard   case -> model -> candidate -> Jev -> deterministic controls -> policy

All three share the *same* cached candidate action per repetition, so what varies
between them is the decision layer and nothing else. That is the experiment.

    uv run python scripts/run_architecture.py --repetitions 3
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from product.accounting_agent import agent, cache  # noqa: E402
from product.accounting_agent.controls import apply_controls  # noqa: E402
from product.accounting_agent.judges.jev_judge import JevJudge  # noqa: E402
from product.accounting_agent.judges.llm_judge import LLMJudge  # noqa: E402
from product.accounting_agent.policy import route  # noqa: E402
from product.accounting_agent.stub_agent import load_cases  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ARCHITECTURES = {"A": "llm_only", "B": "llm_judge", "C": "jev_guard"}


def run_case(case: dict, which: set[str], repetition: int, judges: dict) -> dict:
    proposal, call = agent.propose(case, repetition=repetition)
    out: dict = {
        "case_id": case["id"],
        "proposal": proposal.model_dump(mode="json"),
        "agent_cost_usd": call.cost_usd,
        "agent_latency_ms": call.latency_ms,
        "agent_cached": call.cached,
        "results": {},
    }

    if "A" in which:
        out["results"]["A"] = {
            "action": str(proposal.action),
            "cost_usd": call.cost_usd,
            "latency_ms": call.latency_ms,
            "reasons": [],
        }

    if "B" in which:
        judgments = judges["llm"].judge(case, proposal.action)
        routing = route(proposal.action, judgments)
        out["results"]["B"] = {
            "action": str(routing.action),
            "cost_usd": round(call.cost_usd + judgments.cost_usd, 8),
            "latency_ms": round(call.latency_ms + judgments.latency_ms, 1),
            "reasons": routing.reasons,
            "judgments": judgments.to_dict(),
        }

    if "C" in which:
        _, verdicts = apply_controls(case.get("input", {}), proposal.action)
        judgments = judges["jev"].judge(case, proposal.action)
        routing = route(proposal.action, judgments, verdicts=verdicts)
        out["results"]["C"] = {
            "action": str(routing.action),
            "cost_usd": round(call.cost_usd + judgments.cost_usd, 8),
            "latency_ms": round(call.latency_ms + judgments.latency_ms, 1),
            "reasons": routing.reasons,
            "judgments": judgments.to_dict(),
            "controls_fired": [v.control for v in verdicts],
            # Stored with their actions so the threshold sweep can re-route
            # offline, without paying for a single model call again.
            "verdicts": [
                {"control": v.control, "action": str(v.action), "reason": v.reason}
                for v in verdicts
            ],
        }

    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run accounting-agent architectures.")
    parser.add_argument(
        "--architectures", nargs="+", default=["A", "B", "C"], choices=list(ARCHITECTURES)
    )
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None, help="first N cases only (smoke test)")
    parser.add_argument("--out-dir", type=pathlib.Path, default=REPO_ROOT / "results" / "phase7")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args(argv)

    which = set(args.architectures)
    judges = {
        "llm": LLMJudge(use_cache=not args.no_cache),
        "jev": JevJudge(use_cache=not args.no_cache),
    }
    cases = load_cases()
    if args.limit:
        cases = cases[: args.limit]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    for repetition in range(1, args.repetitions + 1):
        details = []
        for index, case in enumerate(cases, start=1):
            detail = run_case(case, which, repetition, judges)
            details.append(detail)
            actions = " ".join(
                f"{a}={detail['results'][a]['action']:<6}" for a in sorted(detail["results"])
            )
            print(
                f"  rep{repetition} [{index:>2}/{len(cases)}] {case['id']:<4} {actions}", flush=True
            )

        for letter in sorted(which):
            name = ARCHITECTURES[letter]
            run_path = args.out_dir / f"{name}_rep{repetition}.jsonl"
            run_path.write_text(
                "\n".join(
                    json.dumps(
                        {
                            "case_id": d["case_id"],
                            "architecture": name,
                            "action": d["results"][letter]["action"],
                            "latency_ms": d["results"][letter]["latency_ms"],
                            "cost_usd": d["results"][letter]["cost_usd"],
                        }
                    )
                    for d in details
                )
                + "\n"
            )
        (args.out_dir / f"detail_rep{repetition}.json").write_text(
            json.dumps(details, indent=2) + "\n"
        )
        print(f"  rep{repetition} written to {args.out_dir}", flush=True)

    total_cost = sum(d["results"][letter]["cost_usd"] for d in details for letter in d["results"])
    print(
        f"\n{len(cases)} cases x {args.repetitions} repetition(s) x {len(which)} architecture(s)"
        f" in {time.monotonic() - started:.0f}s"
    )
    print(
        f"cache: {cache.count('agent')} agent, {cache.count('judge_llm')} llm judge, "
        f"{cache.count('judge_jev')} jev judge"
    )
    print(f"last repetition cost ${total_cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
