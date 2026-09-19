"""The product's own model client.

Deliberately separate from `factory/llm.py`. The factory builds the product; the
product must not import the thing that edits it, or the two become one system and
the boundary this project is testing stops existing.
"""

from __future__ import annotations

import os
import pathlib
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv
from pydantic import BaseModel

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

DEFAULT_MODEL = os.environ.get("PRODUCT_MODEL", "claude-opus-5")
PRICES = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


class ProductModelError(RuntimeError):
    pass


@dataclass
class Call:
    model: str
    tokens: dict = field(default_factory=dict)
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False


def estimate_cost(model: str, tokens: dict) -> float:
    input_price, output_price = PRICES.get(model, PRICES[DEFAULT_MODEL])
    billed = tokens.get("input", 0)
    billed += tokens.get("cache_creation", 0) * 1.25 + tokens.get("cache_read", 0) * 0.1
    return round((billed * input_price + tokens.get("output", 0) * output_price) / 1e6, 8)


def structured[T: BaseModel](
    prompt: str,
    schema: type[T],
    system: str,
    model: str | None = None,
    max_tokens: int = 4000,
) -> tuple[T, Call]:
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ProductModelError("ANTHROPIC_API_KEY is not set")

    model = model or DEFAULT_MODEL
    client = anthropic.Anthropic(max_retries=4)
    started = time.monotonic()

    try:
        response = client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
            thinking={"type": "adaptive"},
        )
    except anthropic.APIStatusError as exc:
        raise ProductModelError(f"{model} returned {exc.status_code}: {exc.message}") from exc

    if response.stop_reason == "refusal":
        raise ProductModelError(f"{model} declined the request")
    if response.parsed_output is None:
        raise ProductModelError(f"{model} returned no parseable {schema.__name__}")

    usage = response.usage
    tokens = {
        "input": usage.input_tokens,
        "output": usage.output_tokens,
        "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_creation": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }
    return response.parsed_output, Call(
        model=model,
        tokens=tokens,
        cost_usd=estimate_cost(model, tokens),
        latency_ms=round((time.monotonic() - started) * 1000, 1),
    )
