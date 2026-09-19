"""Model backends for the factory's model-backed roles.

Two of them, for two different jobs:

`run_claude_code` drives the Claude Code CLI as an agent — it reads files, edits
them and runs tests inside a permission sandbox. That is the builder's job.

`run_structured` (Phase 3, planner and reviewer) asks for one JSON object against a
fixed schema and nothing else. That is a different job and wants a different tool.

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

from factory.paths import REPO_ROOT

BUILDER_SETTINGS = REPO_ROOT / "factory" / "builder_settings.json"
DEFAULT_BUILDER_MODEL = os.environ.get("FACTORY_BUILDER_MODEL", "claude-sonnet-5")
DEFAULT_MAX_TURNS = int(os.environ.get("FACTORY_MAX_TURNS", "40"))
TIMEOUT_SECONDS = int(os.environ.get("FACTORY_MODEL_TIMEOUT", "900"))


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
