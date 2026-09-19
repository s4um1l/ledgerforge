"""Model backends for the factory's model-backed roles.

Two of them, for two different jobs:

`run_claude_code` drives the Claude Code CLI as an agent — it reads files, edits
them and runs tests inside a permission sandbox. That is the builder's job.

`run_structured` asks for one object against a fixed schema and nothing else. The
planner and the reviewer are judged on the shape of what they return, so they use
the API's structured output rather than prose that has to be salvaged.

Neither is trusted. Whatever a model claims it did, the validator re-derives from
the git diff and from running the suite.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv
from pydantic import BaseModel

from factory.paths import REPO_ROOT

load_dotenv(REPO_ROOT / ".env")

BUILDER_SETTINGS = REPO_ROOT / "factory" / "builder_settings.json"

# Opus everywhere by default. Downgrading a role to save money is a decision for
# whoever is paying, not a default buried in the factory — override per role with
# FACTORY_BUILDER_MODEL / FACTORY_PLANNER_MODEL / FACTORY_REVIEWER_MODEL.
DEFAULT_MODEL = "claude-opus-5"
DEFAULT_BUILDER_MODEL = os.environ.get("FACTORY_BUILDER_MODEL", DEFAULT_MODEL)
DEFAULT_PLANNER_MODEL = os.environ.get("FACTORY_PLANNER_MODEL", DEFAULT_MODEL)
DEFAULT_REVIEWER_MODEL = os.environ.get("FACTORY_REVIEWER_MODEL", DEFAULT_MODEL)
DEFAULT_MAX_TURNS = int(os.environ.get("FACTORY_MAX_TURNS", "40"))
TIMEOUT_SECONDS = int(os.environ.get("FACTORY_MODEL_TIMEOUT", "900"))

# Anthropic list prices, $ per million tokens, for the trace's cost accounting.
PRICES = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


class ModelError(RuntimeError):
    pass


@dataclass
class ModelCall:
    """One model invocation, with everything the trace needs to account for it."""

    text: str
    model: str
    cost_usd: float = 0.0
    tokens: dict = field(default_factory=dict)
    num_turns: int = 0
    duration_seconds: float = 0.0
    session_id: str = ""
    permission_denials: list = field(default_factory=list)

    def metadata(self) -> dict:
        """Everything the trace needs to account for this call.

        Denials are recorded in full, not counted. What a sandboxed agent *tried*
        to do is evidence about the boundary, and a count throws it away.
        """
        return {
            "model": self.model,
            "cost_usd": self.cost_usd,
            "tokens": self.tokens,
            "num_turns": self.num_turns,
            "duration_seconds": self.duration_seconds,
            "session_id": self.session_id,
            "permission_denials": [
                {
                    "tool": denial.get("tool_name", "?"),
                    "input": str(denial.get("tool_input", ""))[:400],
                }
                for denial in self.permission_denials
            ],
        }


def extract_json(text: str) -> dict:
    """Pull one JSON object out of a model's output.

    Models wrap JSON in prose and fences however they feel. Accepting that is not
    leniency about the contract — the parsed object still has to validate against
    the schema, which is where the contract is actually enforced.
    """
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []

    depth, start = 0, None
    for index, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start : index + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise ModelError(f"no JSON object in model output:\n{text[:1000]}")


def run_claude_code(
    prompt: str,
    allowed_tools: list[str] | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    settings: str | None = None,
) -> ModelCall:
    """Run the Claude Code CLI non-interactively inside a permission sandbox.

    The sandbox is `factory/builder_settings.json`: the product tree is writable,
    the cases and the world are readable, the answers are denied to the Read tool
    *and* to the shell, and Bash is allowlisted down to the test and lint commands.
    Verified rather than assumed — see `factory/tests/test_builder_sandbox.py`.
    """
    command = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--settings",
        settings or str(BUILDER_SETTINGS),
        "--allowedTools",
        *(allowed_tools or ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]),
        "--disallowedTools",
        "WebFetch",
        "WebSearch",
        "--max-turns",
        str(max_turns or DEFAULT_MAX_TURNS),
        "--model",
        model or DEFAULT_BUILDER_MODEL,
    ]

    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ModelError(f"claude timed out after {TIMEOUT_SECONDS}s") from exc

    if completed.returncode != 0:
        raise ModelError(
            f"claude exited {completed.returncode}: {completed.stderr.strip()[-2000:]}"
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ModelError(f"claude did not return JSON: {completed.stdout[:500]}") from exc

    if payload.get("is_error"):
        raise ModelError(f"claude reported an error: {payload.get('result', '')[:500]}")

    usage = payload.get("usage") or {}
    model_usage = payload.get("modelUsage") or {}
    return ModelCall(
        text=payload.get("result", ""),
        model=", ".join(sorted(model_usage)) or (model or DEFAULT_BUILDER_MODEL),
        cost_usd=float(payload.get("total_cost_usd") or 0.0),
        tokens={
            "input": usage.get("input_tokens", 0),
            "output": usage.get("output_tokens", 0),
            "cache_read": usage.get("cache_read_input_tokens", 0),
            "cache_creation": usage.get("cache_creation_input_tokens", 0),
        },
        num_turns=int(payload.get("num_turns") or 0),
        duration_seconds=round(time.monotonic() - started, 2),
        session_id=payload.get("session_id", ""),
        permission_denials=payload.get("permission_denials") or [],
    )


def estimate_cost(model: str, tokens: dict) -> float:
    """List-price cost of one call. Cached reads are billed at a tenth of input."""
    input_price, output_price = PRICES.get(model, PRICES[DEFAULT_MODEL])
    billed_input = tokens.get("input", 0) + tokens.get("cache_creation", 0) * 1.25
    billed_input += tokens.get("cache_read", 0) * 0.1
    return round(
        (billed_input * input_price + tokens.get("output", 0) * output_price) / 1_000_000,
        6,
    )


def run_structured[T: BaseModel](
    prompt: str,
    schema: type[T],
    system: str,
    model: str | None = None,
    max_tokens: int = 16000,
) -> tuple[T, ModelCall]:
    """Ask for exactly one object of `schema`, validated by the SDK.

    This is why the planner and reviewer do not go through the CLI: their contract
    is a shape, and a shape the API guarantees beats a shape a parser hopes for.
    An invalid response raises here rather than becoming a half-populated plan the
    orchestrator has to second-guess.
    """
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ModelError(
            "ANTHROPIC_API_KEY is not set; put it in .env (gitignored) or the environment"
        )

    model = model or DEFAULT_MODEL
    client = anthropic.Anthropic()
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
        raise ModelError(f"{model} returned {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise ModelError(f"could not reach the API: {exc}") from exc

    if response.stop_reason == "refusal":
        detail = getattr(response.stop_details, "category", "unknown")
        raise ModelError(f"{model} declined the request ({detail})")

    parsed = response.parsed_output
    if parsed is None:
        raise ModelError(f"{model} returned no parseable {schema.__name__}")

    usage = response.usage
    tokens = {
        "input": usage.input_tokens,
        "output": usage.output_tokens,
        "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_creation": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }
    call = ModelCall(
        text=parsed.model_dump_json(),
        model=model,
        cost_usd=estimate_cost(model, tokens),
        tokens=tokens,
        num_turns=1,
        duration_seconds=round(time.monotonic() - started, 2),
        session_id=response.id,
    )
    return parsed, call
