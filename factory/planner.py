"""Planner: proposes a bounded change. It never edits a file.

Two backends. `scripted` is the deterministic Phase 2 planner, kept because it
makes the orchestration testable for free. `api` asks a model for a `Plan` through
structured output, so an unusable shape fails at the boundary instead of becoming a
half-populated plan the builder has to interpret.

Either way the plan is checked against the work item's scope before any code runs:
a plan that proposes editing what it may not edit is rejected on the spot.
"""

from __future__ import annotations

import json
import os

from factory import llm
from factory.fake_builds import SCRIPTED_TARGETS
from factory.paths import PROMPTS_DIR
from factory.schemas import ContextPackage, Plan, ScopeGuard, WorkItem

SCRIPTED_MODEL = "fake:deterministic-planner"
DEFAULT_BACKEND = os.environ.get("FACTORY_PLANNER", "scripted")

last_call: llm.ModelCall | None = None


class PlanError(RuntimeError):
    pass


def check_plan(plan: Plan, item: WorkItem) -> list[str]:
    """A plan that proposes editing outside scope is rejected before any code runs."""
    guard = ScopeGuard(item.scope)
    return [
        f"plan proposes editing {path}, outside allowed scope"
        for path in plan.files_to_modify
        if not guard.may_modify(path)
    ]


def _prompt(item: WorkItem, context: ContextPackage) -> str:
    """Everything the planner needs and nothing it should not have."""
    lines = [
        f"# Work item {item.id}: {item.title}",
        "",
        f"**Intent.** {item.intent}",
        "",
        f"**Observed.** {item.problem.summary}",
        "",
        f"The system returned `{context.failure.actual}` where policy requires "
        f"`{context.failure.expected}`.",
        "",
        f"**Severity.** {item.business_impact.severity}",
        "",
        "**Acceptance criteria.**",
        *[f"- {c}" for c in item.acceptance_criteria],
        "",
        "**You may propose modifying only these paths.**",
        *[f"- `{p}`" for p in item.scope.allowed_paths],
        "",
        "**These may not be modified by anyone.**",
        *[f"- `{p}`" for p in item.scope.forbidden_paths],
        "",
        f"**Regression policy.** At most {item.regression_policy.max_new_failures} "
        "newly failing case(s).",
    ]

    if context.failure.case_input:
        lines += [
            "",
            f"## The failing case ({context.failure.case_id})",
            "",
            "```json",
            json.dumps(context.failure.case_input, indent=2),
            "```",
        ]

    lines += ["", "## The customer's machine-readable policy", ""]
    for doc in context.domain_docs:
        lines += [f"### `{doc.path}`", "", "```yaml", doc.contents, "```", ""]

    lines += ["## The code in scope", ""]
    for file in context.files:
        language = "python" if file.path.endswith(".py") else ""
        lines += [f"### `{file.path}`", "", f"```{language}", file.contents, "```", ""]

    return "\n".join(lines)


def plan_with_api(item: WorkItem, context: ContextPackage) -> Plan:
    global last_call
    system = (PROMPTS_DIR / "planner.md").read_text()
    try:
        result, call = llm.run_structured(
            _prompt(item, context),
            Plan,
            system=system,
            model=llm.DEFAULT_PLANNER_MODEL,
        )
    except llm.ModelError as exc:
        raise PlanError(str(exc)) from exc

    last_call = call
    print(
        f"  planner: {call.duration_seconds}s, "
        f"${call.cost_usd:.4f} list-price equivalent ({call.model})"
    )
    return result


def plan_scripted(item: WorkItem, context: ContextPackage) -> Plan:
    targets = SCRIPTED_TARGETS.get(item.id)
    if not targets:
        raise PlanError(
            f"no deterministic plan for {item.id}; Phase 2's planner only knows "
            f"scripted tasks ({', '.join(sorted(SCRIPTED_TARGETS)) or 'none'})"
        )

    case = context.failure
    evidence = ""
    if case.case_input:
        amounts = case.case_input.get("input", {})
        po = (amounts.get("purchase_order") or {}).get("amount")
        invoice = (amounts.get("invoice") or {}).get("amount")
        if po and invoice:
            evidence = f" Case {case.case_id} invoices ${invoice:,.2f} against a ${po:,.2f} order."

    existing_controls = [
        p for p in context.file_paths if "/controls/" in p and not p.endswith("__init__.py")
    ]

    return Plan(
        understanding=(
            f"{item.title}. The agent returned {case.actual} where policy requires "
            f"{case.expected}.{evidence}"
        ),
        root_cause_hypothesis=(
            "The control layer has no check comparing an invoice to the purchase order it "
            "is matched against, so an overbill inside no other control's remit reaches the "
            "policy engine as an automatable action. The threshold already exists in the "
            "customer policy; nothing reads it."
        ),
        files_to_modify=list(targets),
        steps=[
            "Add a control module that reads the invoice_tolerance limits from the "
            "customer policy rather than hard-coding them.",
            "Return REVIEW when a difference exceeds either the absolute or the "
            "percentage limit; stay silent otherwise.",
            "Register the control in the existing registry so the diff shows it being added.",
            "Add unit tests covering the target case, both limits independently, and the "
            "cases the control must not touch.",
        ],
        tests_to_add=[
            "tolerance control sends the target case to review",
            "a difference inside both limits still auto-approves",
            "each limit is sufficient on its own to require review",
            "cash-application cases with no purchase order are untouched",
        ],
        risks=[
            "A control scoped too broadly would send correct automatic decisions to a "
            "human — a case comparing a bank deposit to an invoice can legitimately "
            "differ because of a credit memo.",
            "Reading thresholds from code instead of policy would make the "
            "automation/risk sweep impossible later.",
        ],
        smallest_change_rationale=(
            f"The control layer is already a registry of {len(existing_controls)} independent "
            "checks, each of which may only reduce autonomy. Adding one module plus its "
            "registration is the smallest change that fixes the failure, because no "
            "existing control's behaviour has to change and no caller has to be touched. "
            "The alternative — teaching an existing control about purchase orders — would "
            "widen that control's remit and put currently-passing cases at risk."
        ),
    )


BACKENDS = {
    "scripted": plan_scripted,
    "api": plan_with_api,
}

MODELS = {
    "scripted": SCRIPTED_MODEL,
    "api": llm.DEFAULT_PLANNER_MODEL,
}

MODEL = MODELS[DEFAULT_BACKEND]


def plan(item: WorkItem, context: ContextPackage, backend: str | None = None) -> Plan:
    name = backend or DEFAULT_BACKEND
    if name not in BACKENDS:
        raise PlanError(f"unknown planner backend {name!r}; have {', '.join(BACKENDS)}")
    return BACKENDS[name](item, context)
