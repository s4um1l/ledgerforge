"""Builder: implements the approved plan inside the allowed scope.

Two backends:

    scripted     replays a patch a human wrote; keeps the tests hermetic and the
                 orchestration provable without spending anything
    claude-code  drives the Claude Code CLI as an agent inside a permission
                 sandbox, which is what Phase 3 is for

Neither is trusted. Scope is checked afterwards from the git diff, not from the
builder's own account of what it touched, and a builder that edits outside its
scope is rejected however plausible its summary sounds.
"""

from __future__ import annotations

import json
import os

from factory import llm
from factory.fake_builds import SCRIPTED_BUILDS
from factory.paths import PROMPTS_DIR
from factory.schemas import BuildResult, ContextPackage, Plan, WorkItem

SCRIPTED_MODEL = "fake:scripted-builder"
DEFAULT_BACKEND = os.environ.get("FACTORY_BUILDER", "scripted")

# Populated by the model-backed backend so the orchestrator can record what the
# call actually cost.
last_call: llm.ModelCall | None = None


class BuildError(RuntimeError):
    pass


def _prompt(item: WorkItem, plan: Plan, context: ContextPackage) -> str:
    role = (PROMPTS_DIR / "builder.md").read_text()
    case = context.failure

    lines = [
        role,
        "",
        "---",
        "",
        "# This task",
        "",
        f"## Work item {item.id}: {item.title}",
        "",
        f"**Intent.** {item.intent}",
        "",
        f"**Observed.** {item.problem.summary}",
        f"The system returned `{case.actual}` where policy requires `{case.expected}`.",
        "",
        "**Acceptance criteria.**",
        *[f"- {c}" for c in item.acceptance_criteria],
        "",
        "**You may modify only these paths.**",
        *[f"- `{p}`" for p in item.scope.allowed_paths],
        "",
        "**You may not modify these paths.**",
        *[f"- `{p}`" for p in item.scope.forbidden_paths],
        "",
        "## Approved plan",
        "",
        f"**Root cause.** {plan.root_cause_hypothesis}",
        "",
        "**Steps.**",
        *[f"{i}. {s}" for i, s in enumerate(plan.steps, start=1)],
        "",
        "**Tests to add.**",
        *[f"- {t}" for t in plan.tests_to_add],
        "",
        "**Risks the plan identified.**",
        *[f"- {r}" for r in plan.risks],
        "",
        f"**Why this is the smallest change.** {plan.smallest_change_rationale}",
        "",
        "## Files already in scope",
        "",
        *[f"- `{p}`" for p in context.file_paths],
        "",
        "Read them before you write anything.",
    ]

    if case.case_input:
        lines += [
            "",
            f"## The failing case ({case.case_id})",
            "",
            "```json",
            json.dumps(case.case_input, indent=2),
            "```",
            "",
            "This is the case input only. You have no access to the expected answers,",
            "and the run is invalid if you obtain them.",
        ]

    lines += [
        "",
        "## When you are done",
        "",
        "Run the product test suite, then print the JSON object described above and",
        "nothing else after it.",
    ]
    return "\n".join(lines)


def build_scripted(item: WorkItem, plan: Plan, context: ContextPackage) -> BuildResult:
    scripted = SCRIPTED_BUILDS.get(item.id)
    if not scripted:
        raise BuildError(
            f"no scripted build for {item.id}; the scripted builder cannot invent a patch"
        )
    return scripted()


def build_with_claude_code(item: WorkItem, plan: Plan, context: ContextPackage) -> BuildResult:
    global last_call
    try:
        call = llm.run_claude_code(_prompt(item, plan, context))
    except llm.ModelError as exc:
        raise BuildError(str(exc)) from exc

    last_call = call
    if call.permission_denials:
        attempted = {d.get("tool_name", "?") for d in call.permission_denials}
        print(
            f"  builder was denied {len(call.permission_denials)} tool call(s) "
            f"({', '.join(sorted(attempted))})"
        )

    try:
        payload = llm.extract_json(call.text)
    except llm.ModelError as exc:
        raise BuildError(f"builder returned no usable JSON: {exc}") from exc

    payload.pop("model", None)
    try:
        result = BuildResult.model_validate(payload)
    except Exception as exc:
        raise BuildError(f"builder output does not match the contract: {exc}") from exc

    # Models report their own work loosely — a created file often appears only in
    # `created_files`. Normalise rather than complain: the self-report feeds the
    # revert path, while scope is checked from the git diff regardless.
    result.changed_files = sorted(set(result.changed_files) | set(result.created_files))

    print(
        f"  builder: {call.num_turns} turns, {call.duration_seconds}s, "
        f"${call.cost_usd:.4f} list-price equivalent"
    )
    return result


BACKENDS = {
    "scripted": build_scripted,
    "claude-code": build_with_claude_code,
}

MODELS = {
    "scripted": SCRIPTED_MODEL,
    "claude-code": llm.DEFAULT_BUILDER_MODEL,
}

MODEL = MODELS[DEFAULT_BACKEND]


def build(
    item: WorkItem,
    plan: Plan,
    context: ContextPackage,
    backend: str | None = None,
) -> BuildResult:
    name = backend or DEFAULT_BACKEND
    if name not in BACKENDS:
        raise BuildError(f"unknown builder backend {name!r}; have {', '.join(BACKENDS)}")
    return BACKENDS[name](item, plan, context)
