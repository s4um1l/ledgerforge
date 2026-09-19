"""Configuration A: case -> frontier model -> structured candidate action.

The model both reasons and decides here. Configurations B and C keep this exact
proposal and add a decision layer on top, so the comparison isolates the decision
layer rather than the reasoning.
"""

from __future__ import annotations

import json
import pathlib

from pydantic import BaseModel, Field

from product.accounting_agent import cache, llm
from product.accounting_agent.models import Action
from product.accounting_agent.world import world_context

PROMPTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "prompts"
ARCHITECTURE = "llm_only"


class AgentProposal(BaseModel):
    """What the model proposes for one case."""

    action: Action
    account: str | None = None
    amount: float | None = None
    rationale: str = Field(default="")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


def system_prompt() -> str:
    return (PROMPTS_DIR / "agent.md").read_text()


def case_prompt(case: dict) -> str:
    return "\n".join(
        [
            world_context(),
            "",
            "---",
            "",
            f"# Case {case['id']} ({case['category']})",
            "",
            case.get("summary", ""),
            "",
            "```json",
            json.dumps(case.get("input", {}), indent=2),
            "```",
            "",
            "Decide what should happen to this case.",
        ]
    )


def propose(
    case: dict,
    model: str | None = None,
    repetition: int = 1,
    use_cache: bool = True,
) -> tuple[AgentProposal, llm.Call]:
    """Propose an action for one case, caching by everything that could change it."""
    model = model or llm.DEFAULT_MODEL
    system, prompt = system_prompt(), case_prompt(case)
    key = cache.key_for(
        model=model, system=system, prompt=prompt, repetition=repetition, schema="AgentProposal"
    )

    if use_cache and (hit := cache.read("agent", key)):
        return AgentProposal.model_validate(hit["proposal"]), llm.Call(
            model=hit["model"],
            tokens=hit["tokens"],
            cost_usd=hit["cost_usd"],
            latency_ms=hit["latency_ms"],
            cached=True,
        )

    proposal, call = llm.structured(prompt, AgentProposal, system=system, model=model)
    cache.write(
        "agent",
        key,
        {
            "case_id": case["id"],
            "repetition": repetition,
            "proposal": proposal.model_dump(mode="json"),
            "model": call.model,
            "tokens": call.tokens,
            "cost_usd": call.cost_usd,
            "latency_ms": call.latency_ms,
        },
    )
    return proposal, call


def to_run_record(case_id: str, proposal: AgentProposal, call: llm.Call, architecture: str) -> dict:
    return {
        "case_id": case_id,
        "architecture": architecture,
        "action": str(proposal.action),
        "latency_ms": call.latency_ms,
        "cost_usd": call.cost_usd,
    }
