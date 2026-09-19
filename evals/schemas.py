"""Typed objects shared by the evaluators.

These are evaluation-side types. The product has its own models; keeping them
separate means the agent cannot quietly reshape what it is graded against.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Action(StrEnum):
    """The only three things the system may decide to do."""

    AUTO = "AUTO"
    REVIEW = "REVIEW"
    REJECT = "REJECT"

    @classmethod
    def _missing_(cls, value: object) -> Action | None:
        # Tolerate the longer spellings that show up in hand-written fixtures.
        aliases = {
            "AUTO_APPROVE": cls.AUTO,
            "AUTO_POST": cls.AUTO,
            "HUMAN_REVIEW": cls.REVIEW,
        }
        if isinstance(value, str):
            return aliases.get(value.strip().upper())
        return None


class JudgmentLabels(BaseModel):
    """The five atomic judgments. One Jev `Noul` question each."""

    model_config = ConfigDict(extra="forbid")

    evidence_sufficient: bool
    sources_consistent: bool
    candidate_supported: bool
    possible_duplicate: bool
    requires_human_review: bool


class Case(BaseModel):
    """A benchmark case as the agent sees it. Carries no answer."""

    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    benchmark_version: str
    scaffold: bool = False
    summary: str = ""
    input: dict = Field(default_factory=dict)
    candidate_action: Action


class GoldAnswer(BaseModel):
    """The answer. Only the evaluator may load these."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    gold_action: Action
    labels: JudgmentLabels


class RunRecord(BaseModel):
    """What one architecture actually decided for one case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    action: Action
    architecture: str = "unknown"
    latency_ms: float | None = None
    cost_usd: float | None = None
    judgments: dict[str, float] | None = None


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    category: str
    expected: Action
    actual: Action
    passed: bool


class SuiteMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_correctness: float
    automation_coverage: float
    autonomous_error_rate: float
    human_review_rate: float
    reject_rate: float
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    total_cost_usd: float | None = None


class SuiteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    architecture: str
    passed: int
    total: int
    results: list[CaseResult]
    metrics: SuiteMetrics

    @property
    def failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed]

    def passed_case_ids(self) -> set[str]:
        return {r.case_id for r in self.results if r.passed}

    def summary_line(self) -> str:
        return f"{self.label}: {self.passed}/{self.total}"


class RunComparison(BaseModel):
    """Before/after, with regressions called out explicitly."""

    model_config = ConfigDict(extra="forbid")

    before: str
    after: str
    before_passed: int
    after_passed: int
    total: int
    newly_passing: list[str]
    newly_failing: list[str]
    unchanged_failures: list[str]

    @property
    def regressions(self) -> list[str]:
        return self.newly_failing

    @property
    def improved(self) -> bool:
        return self.after_passed > self.before_passed and not self.newly_failing
