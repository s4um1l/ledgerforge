"""Typed factory objects.

Every stage has an input type and an output type. A stage that cannot produce its
output type has failed — there is no "mostly worked".
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator


class State(StrEnum):
    """The factory state machine, in code rather than implied by prompts."""

    CREATED = "CREATED"
    CONTEXT_READY = "CONTEXT_READY"
    PLANNED = "PLANNED"
    BUILT = "BUILT"
    VALIDATED = "VALIDATED"
    REVIEWED = "REVIEWED"
    ACCEPTED = "ACCEPTED"

    FAILED_CONTEXT = "FAILED_CONTEXT"
    FAILED_PLAN = "FAILED_PLAN"
    FAILED_BUILD = "FAILED_BUILD"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    REJECTED_REVIEW = "REJECTED_REVIEW"
    REJECTED_REGRESSION = "REJECTED_REGRESSION"
    REJECTED_SCOPE = "REJECTED_SCOPE"

    @property
    def is_terminal(self) -> bool:
        return self is State.ACCEPTED or self.is_failure

    @property
    def is_failure(self) -> bool:
        return self.name.startswith(("FAILED_", "REJECTED_"))


HAPPY_PATH: list[State] = [
    State.CREATED,
    State.CONTEXT_READY,
    State.PLANNED,
    State.BUILT,
    State.VALIDATED,
    State.REVIEWED,
    State.ACCEPTED,
]


# --- work item -----------------------------------------------------------


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    case_id: str | None = None


class Problem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    actual_behavior: str
    expected_behavior: str


class BusinessImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: str


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_paths: list[str] = Field(min_length=1)
    forbidden_paths: list[str] = Field(default_factory=list)


class Verification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commands: list[str] = Field(min_length=1)


class RegressionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_new_failures: int = 0


class WorkItem(BaseModel):
    """The boundary between "something went wrong" and "here is a task"."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    source: Source
    problem: Problem
    business_impact: BusinessImpact
    intent: str
    scope: Scope
    acceptance_criteria: list[str] = Field(min_length=1)
    verification: Verification
    regression_policy: RegressionPolicy = Field(default_factory=RegressionPolicy)

    @field_validator("intent", "title")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @property
    def target_case_id(self) -> str | None:
        return self.source.case_id


# --- stage outputs -------------------------------------------------------


class Plan(BaseModel):
    """The planner proposes. It never edits."""

    model_config = ConfigDict(extra="forbid")

    understanding: str
    root_cause_hypothesis: str
    files_to_modify: list[str]
    steps: list[str] = Field(min_length=1)
    tests_to_add: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    smallest_change_rationale: str


class BuildResult(BaseModel):
    """What the builder says it did. The diff is captured from git, not from here."""

    model_config = ConfigDict(extra="forbid")

    changed_files: list[str]
    created_files: list[str] = Field(default_factory=list)
    summary: str
    tests_added: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)


class CommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str
    exit_code: int
    duration_seconds: float
    stdout_tail: str = ""
    stderr_tail: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class UnitTestEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: int
    failed: int
    exit_code: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.failed == 0


class TargetCaseEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case: str
    before: bool
    after: bool

    @property
    def fixed(self) -> bool:
        return self.after and not self.before


class BenchmarkCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: int
    total: int


class BenchmarkEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before: BenchmarkCount
    after: BenchmarkCount


class ValidationResult(BaseModel):
    """Evidence, gathered deterministically. No model is asked for an opinion."""

    model_config = ConfigDict(extra="forbid")

    static_checks: list[CommandResult] = Field(default_factory=list)
    unit_tests: UnitTestEvidence | None = None
    target_case: TargetCaseEvidence | None = None
    benchmark: BenchmarkEvidence | None = None
    regressions: list[str] = Field(default_factory=list)
    newly_passing: list[str] = Field(default_factory=list)
    declared_commands: list[CommandResult] = Field(default_factory=list)
    scope_violations: list[str] = Field(default_factory=list)
    stage_reached: str = ""
    error: str | None = None

    @property
    def static_ok(self) -> bool:
        return all(c.ok for c in self.static_checks)

    @property
    def declared_ok(self) -> bool:
        return all(c.ok for c in self.declared_commands)


class ReviewCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_respected: bool
    acceptance_met: bool
    tests_pass: bool
    no_regressions: bool


class Review(BaseModel):
    """The reviewer advises. It does not decide."""

    model_config = ConfigDict(extra="forbid")

    decision: str
    criteria: ReviewCriteria
    concerns: list[str] = Field(default_factory=list)
    summary: str

    @field_validator("decision")
    @classmethod
    def _known_decision(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in {"ACCEPT", "REJECT"}:
            raise ValueError("decision must be ACCEPT or REJECT")
        return value


class Decision(BaseModel):
    """The orchestrator's final call, with the gate that produced it."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool
    state: State
    gates: dict[str, bool]
    blocking_reasons: list[str] = Field(default_factory=list)


class RunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_id: str
    git_sha_before: str
    git_sha_after: str | None = None
    planner_model: str
    builder_model: str
    reviewer_model: str
    started_at: str
    finished_at: str | None = None
    duration_seconds: float = 0.0
    states: list[str] = Field(default_factory=list)
    tokens: dict = Field(default_factory=dict)
    estimated_cost: dict = Field(default_factory=dict)


# --- scope ---------------------------------------------------------------


class ScopeGuard:
    """Decides which paths a build may *modify*. Forbidden always beats allowed.

    This is a write boundary, not a read boundary. The factory is allowed to read
    the benchmark cases and the synthetic world while being forbidden to edit
    them — that asymmetry is the point. What may be *read* is whitelisted
    separately in `factory.context`.
    """

    def __init__(self, scope: Scope) -> None:
        self.allowed = list(scope.allowed_paths)
        self.forbidden = list(scope.forbidden_paths)

    @staticmethod
    def _matches(path: str, patterns: list[str]) -> bool:
        candidate = PurePosixPath(path)
        return any(candidate.full_match(pattern) for pattern in patterns)

    def is_forbidden(self, path: str) -> bool:
        return self._matches(path, self.forbidden)

    def may_modify(self, path: str) -> bool:
        return not self.is_forbidden(path) and self._matches(path, self.allowed)

    def violations(self, paths: list[str]) -> list[str]:
        return sorted(p for p in paths if not self.may_modify(p))


class ContextFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    contents: str
    truncated: bool = False


class FailureContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str | None = None
    actual: str
    expected: str
    case_input: dict | None = None


class ContextPackage(BaseModel):
    """Only what the task needs. Never the whole repository, never the answers."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    intent: str
    files: list[ContextFile] = Field(default_factory=list)
    domain_docs: list[ContextFile] = Field(default_factory=list)
    failure: FailureContext
    excluded: list[str] = Field(default_factory=list)

    @property
    def file_paths(self) -> list[str]:
        return [f.path for f in self.files]
