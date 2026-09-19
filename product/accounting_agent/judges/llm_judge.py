"""A structured-output LLM judge: the thing Jev is being compared against.

It gets the same five questions, the same wording, the same state, and is asked
for the same probabilities. The only difference from the Jev judge is what
produces the numbers.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, create_model

from product.accounting_agent import cache, llm
from product.accounting_agent.judges.base import Judgments, split_questions
from product.accounting_agent.models import Action
from product.accounting_agent.world import world_context

NAME = "llm_judge"

SYSTEM = """You are a judgement layer inside an accounting automation system.

You do not decide what happens to the case. You answer specific questions about
it, each as a probability between 0 and 1, and code downstream applies thresholds
to your numbers.

Because thresholds are applied to them, your probabilities must be calibrated: if
you say 0.90, you should be right about nine times in ten. Do not cluster at 0.9
and 0.95 out of politeness. A genuinely uncertain case deserves a number near 0.5,
and a clear one deserves a number near 0 or 1.

Answer only about the evidence actually present. A field that is absent is not a
field that disagrees.
"""


def _schema(labels: list[str]) -> type[BaseModel]:
    fields = {
        label: (float, Field(ge=0.0, le=1.0, description=f"probability for {label}"))
        for label in labels
    }
    return create_model("JudgeAnswers", **fields)


def _prompt(case: dict, candidate: Action, questions: list) -> str:
    lines = [
        world_context(),
        "",
        "---",
        "",
        f"# Case {case['id']} ({case['category']})",
        "",
        "```json",
        json.dumps(case.get("input", {}), indent=2),
        "```",
        "",
        f"# The proposed action is `{candidate}`",
        "",
        "# Questions",
        "",
    ]
    for question in questions:
        lines.append(f"- **{question.label}**: {question.instructions}")
    lines += [
        "",
        "Give each one a probability between 0 and 1 that the statement is true.",
    ]
    return "\n".join(lines)


class LLMJudge:
    name = NAME

    def __init__(self, model: str | None = None, use_cache: bool = True) -> None:
        self.model = model or llm.DEFAULT_MODEL
        self.use_cache = use_cache

    def judge(self, case: dict, candidate: Action) -> Judgments:
        questions, assumed = split_questions(case.get("input", {}))
        labels = [q.label for q in questions]
        prompt = _prompt(case, candidate, questions)
        key = cache.key_for(
            judge=NAME, model=self.model, system=SYSTEM, prompt=prompt, labels=labels
        )

        if self.use_cache and (hit := cache.read("judge_llm", key)):
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

        answers, call = llm.structured(prompt, _schema(labels), system=SYSTEM, model=self.model)
        values = {label: float(getattr(answers, label)) for label in labels}
        cache.write(
            "judge_llm",
            key,
            {
                "case_id": case["id"],
                "candidate": str(candidate),
                "values": values,
                "latency_ms": call.latency_ms,
                "cost_usd": call.cost_usd,
                "model": call.model,
            },
        )
        values.update(assumed)
        return Judgments(
            values=values,
            judge=NAME,
            latency_ms=call.latency_ms,
            cost_usd=call.cost_usd,
            assumed=sorted(assumed),
        )
