"""Planner: proposes a bounded change. It never edits a file.

Phase 2 ships a deterministic planner so orchestration can be proved without a
model. It produces a real `Plan` in the real shape, derived from the work item and
the resolved context — the contract Phase 3's model must satisfy.
"""

from __future__ import annotations

from factory.fake_builds import SCRIPTED_TARGETS
from factory.schemas import ContextPackage, Plan, ScopeGuard, WorkItem

MODEL = "fake:deterministic-planner"


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


def plan(item: WorkItem, context: ContextPackage) -> Plan:
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
