"""Phase 3.5 — Jev smoke test. The output of this script is knowledge, not code.

Runs `Choice`, `Noul` and `Score` in one call against three trivial accounting
states, persists the complete raw HTTP response unmodified, and records
probabilities, latency, tokens and cost.

Deliberately not an abstraction. Nothing imports this; Phase 6 writes the real
judge once the response shape has been *observed* rather than read about.

    TYPESAFE_API_KEY=... uv run python scripts/jev_smoke.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

# $ per million input tokens; output is free.
INPUT_PRICE_PER_MTOK = 0.042
OUT_DIR = REPO_ROOT / "results" / "jev_smoke"

POLICY = (
    "invoice_tolerance: a difference of $100 or less AND 1% or less may be "
    "auto-approved; anything larger requires human review."
)


# The five atomic labels the benchmark already uses, one Noul each, plus one
# Choice and one Score so all three primitives are exercised in a single call.
# Phrasings are the ones the LLM judge will receive verbatim in Phase 6 — the
# comparison is only fair if both judges are asked the same thing.
def questions(ts):
    return {
        "evidence_sufficient": ts.Noul(
            instructions=(
                "Is the evidence attached to this case sufficient to support the "
                "proposed accounting action without a human looking at it?"
            )
        ),
        "sources_consistent": ts.Noul(
            instructions=(
                "Do the documents in this case agree with each other on vendor, "
                "amount, dates and terms?"
            )
        ),
        "candidate_supported": ts.Noul(
            instructions=(
                "Is the proposed action supported by the evidence and the stated company policy?"
            )
        ),
        "possible_duplicate": ts.Noul(
            instructions=("Does this case look like a document that has already been recorded?")
        ),
        "requires_human_review": ts.Noul(
            instructions=("Does the stated company policy require a human to approve this action?")
        ),
        "failure_class": ts.Choice(
            instructions="If the proposed action is wrong, what kind of error is it?",
            criteria={
                "tolerance_breach": "The amount difference exceeds the configured tolerance.",
                "duplicate": "The same document has already been recorded.",
                "unevaluable": "The documents cannot be compared at all.",
                "none": "The proposed action appears correct.",
            },
        ),
        "materiality": ts.Score(
            instructions="How material is this discrepancy to the monthly close?",
            criteria=[
                "Immaterial, below any review threshold",
                "Noticeable but routine",
                "Material, would change a reported figure",
            ],
        ),
    }


CASES = {
    "R07_overbill": {
        "purchase_order": {"number": "PO-1042", "amount": 10000.00},
        "invoice": {"number": "INV-8831", "amount": 10400.00, "vendor": "Cloudspan"},
        "proposed_action": "AUTO",
        "policy": POLICY,
    },
    "R01_clean_match": {
        "purchase_order": {"number": "PO-1001", "amount": 4200.00},
        "invoice": {"number": "INV-8801", "amount": 4200.00, "vendor": "Northwind"},
        "proposed_action": "AUTO",
        "policy": POLICY,
    },
    # Deliberately ambiguous: the PO carries no amount, so the comparison the
    # policy asks for cannot be performed. A calibrated judge should be visibly
    # unsure here rather than confidently either way.
    "R09_blanket_po": {
        "purchase_order": {"number": "PO-1100", "amount": 0.0, "note": "blanket order"},
        "invoice": {"number": "INV-8901", "amount": 50.00, "vendor": "Cloudspan"},
        "proposed_action": "AUTO",
        "policy": POLICY,
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3.5 Jev smoke test.")
    parser.add_argument("--model", default=None, help="model route (default: jev-latest)")
    args = parser.parse_args()

    if not os.environ.get("TYPESAFE_API_KEY"):
        print(
            "TYPESAFE_API_KEY is not set. Put it in .env (gitignored) or the "
            "environment. Refusing to continue.",
            file=sys.stderr,
        )
        return 1

    import typesafe_sdk as ts

    client = ts.TypeSafeClient()
    record: dict = {
        "run_at": dt.datetime.now(dt.UTC).isoformat(),
        "sdk_version": getattr(ts, "__version__", "unknown"),
        "model_requested": args.model or ts.constants.DEFAULT_MODEL,
        "cases": {},
    }

    for name, state in CASES.items():
        asked = questions(ts)
        started = time.monotonic()
        response = client.system_one(state, asked, model=args.model)
        latency_ms = round((time.monotonic() - started) * 1000, 1)

        raw = response.raw_http_response
        raw_body = raw.json() if hasattr(raw, "json") else None
        usage = response.usage
        cost = round((usage.input_tokens / 1_000_000) * INPUT_PRICE_PER_MTOK, 8)

        record["cases"][name] = {
            "state": state,
            "questions": {k: v.model_dump() for k, v in asked.items()},
            "raw_response": raw_body,
            "model_served": response.model,
            "request_id": response.request_id,
            "latency_ms": latency_ms,
            "usage": usage.model_dump(),
            "estimated_cost_usd": cost,
        }

        print(f"\n=== {name} ===")
        print(
            f"  served by {response.model}  {latency_ms}ms  "
            f"{usage.input_tokens} in / {usage.output_tokens} out  ${cost:.8f}"
        )
        for key, answer in response.nouls.items():
            print(f"  noul   {key:<24} {answer.noul:.4f}")
        for key, answer in response.choices.items():
            dist = ", ".join(f"{k}={v:.3f}" for k, v in sorted(answer.probabilities.items()))
            print(f"  choice {key:<24} {answer.choice}  confidence={answer.confidence:.4f}")
            print(f"         distribution: {dist}")
        for key, answer in response.scores.items():
            print(f"  score  {key:<24} {answer.score:.4f}  confidence={answer.confidence:.4f}")
            print(f"         legend: {answer.legend}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    path = OUT_DIR / f"{stamp}.json"
    path.write_text(json.dumps(record, indent=2, default=str) + "\n")

    total = sum(c["estimated_cost_usd"] for c in record["cases"].values())
    print(f"\n{len(record['cases'])} case(s), ${total:.8f} total")
    print(f"raw responses persisted to {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
