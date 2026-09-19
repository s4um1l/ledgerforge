"""The Jev judge: a decision-only model, asked the same five questions.

Observed in Phase 3.5 and relied on here: a `noul` answer carries the probability
and nothing else — there is no confidence field to read. Choice and Score have
one; Noul does not. That is why the five atomic labels are thresholded on the
probability directly.
"""

from __future__ import annotations

import os
import time

from product.accounting_agent import cache
from product.accounting_agent.judges.base import Judgments, split_questions
from product.accounting_agent.models import Action

NAME = "jev_judge"
INPUT_PRICE_PER_MTOK = 0.042

# Both judges must receive the same world, or the comparison measures what each
# was told rather than how each judges. Jev takes structured state where the LLM
# judge takes prose, so the same content travels as named fields instead of
# markdown — but it is the same content. An early smoke run with policy-only
# state had Jev scoring a clean recurring subscription at evidence_sufficient
# 0.23 against the LLM judge's 0.95; most of that gap was the missing world, not
# the model.


def _state(case: dict, candidate: Action) -> dict:
    from product.accounting_agent.world import WORLD_DIR

    return {
        "company_overview": (WORLD_DIR / "company.md").read_text(),
        "company_policy": (WORLD_DIR / "policies.yaml").read_text(),
        "chart_of_accounts": (WORLD_DIR / "chart_of_accounts.csv").read_text(),
        "case_id": case.get("id"),
        "case_category": case.get("category"),
        "case_summary": case.get("summary", ""),
        "case_evidence": case.get("input", {}),
        "proposed_action": str(candidate),
    }


class JevJudge:
    name = NAME

    def __init__(self, model: str | None = None, use_cache: bool = True) -> None:
        self.model = model
        self.use_cache = use_cache

    def judge(self, case: dict, candidate: Action) -> Judgments:
        import typesafe_sdk as ts

        if not os.environ.get("TYPESAFE_API_KEY"):
            raise RuntimeError("TYPESAFE_API_KEY is not set")

        questions, assumed = split_questions(case.get("input", {}))
        state = _state(case, candidate)
        asked = {q.label: ts.Noul(instructions=q.instructions) for q in questions}
        key = cache.key_for(
            judge=NAME,
            model=self.model or "jev-latest",
            state=state,
            instructions={q.label: q.instructions for q in questions},
        )

        if self.use_cache and (hit := cache.read("judge_jev", key)):
            values = dict(hit["values"])
            values.update(assumed)
            return Judgments(
                values=values,
                judge=NAME,
                latency_ms=hit["latency_ms"],
                cost_usd=hit["cost_usd"],
                cached=True,
                assumed=sorted(assumed),
            )

        client = ts.TypeSafeClient()
        started = time.monotonic()
        response = client.system_one(state, asked, model=self.model)
        latency_ms = round((time.monotonic() - started) * 1000, 1)

        values = {label: float(answer.noul) for label, answer in response.nouls.items()}
        cost = round(response.usage.input_tokens / 1e6 * INPUT_PRICE_PER_MTOK, 8)
        cache.write(
            "judge_jev",
            key,
            {
                "case_id": case["id"],
                "candidate": str(candidate),
                "values": values,
                "latency_ms": latency_ms,
                "cost_usd": cost,
                "model_served": response.model,
                "usage": response.usage.model_dump(),
            },
        )
        values.update(assumed)
        return Judgments(
            values=values,
            judge=NAME,
            latency_ms=latency_ms,
            cost_usd=cost,
            assumed=sorted(assumed),
        )
