"""Shared pydantic schemas for conductor/worker contracts and memory types."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ObjectiveVector(BaseModel):
    correctness_confidence: float = Field(ge=0.0, le=1.0)
    reversibility: float = Field(ge=0.0, le=1.0)
    locality: float = Field(ge=0.0, le=1.0)
    maintainability: float = Field(ge=0.0, le=1.0)
    delivery_speed: float = Field(ge=0.0, le=1.0)


class MicroTargets(BaseModel):
    files: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    migration: bool = False
    config: bool = False
    endpoint: bool = False
    env_var: bool = False


class CandidatePlan(BaseModel):
    title: str
    summary: str
    role: str
    macro_vec: list[int] = Field(min_length=6, max_length=6)
    meso_tags: list[str] = Field(default_factory=list)
    micro_targets: MicroTargets
    objective_vec: ObjectiveVector
    rollback_plan: str
    test_plan: list[str] = Field(default_factory=list)
    implementation_outline: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)

    @field_validator("macro_vec")
    @classmethod
    def _validate_macro_vals(cls, vals: list[int]) -> list[int]:
        for value in vals:
            if value not in (-1, 0, 1):
                raise ValueError("macro_vec must only include -1, 0, +1")
        return vals


class FeasibilityCertificate(BaseModel):
    macro_pass: bool
    meso_pass: bool
    micro_pass: bool
    lint_plan_valid: bool
    test_plan_valid: bool
    rollback_plan_valid: bool
    migration_policy_pass: bool
    security_policy_pass: bool
    scope_policy_pass: bool
    notes: list[str] = Field(default_factory=list)


class JobCreate(BaseModel):
    repo: str
    task_id: str
    task_type: str
    title: str
    body: str
    base_branch: str = "main"


class JobStatus(BaseModel):
    id: str
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    stage: str = "created"


class MemoryQueryRequest(BaseModel):
    repo: str
    query: str
    scopes: list[str] = Field(default_factory=lambda: ["macro", "meso", "micro"])
    alias_name: str | None = None
    pair_key: str | None = None
    top_k: int = Field(default=5, ge=1, le=50)


class MemoryHit(BaseModel):
    source: str
    record_id: int
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryQueryResponse(BaseModel):
    hits: list[MemoryHit] = Field(default_factory=list)
    applied_overlays: list[str] = Field(default_factory=list)


class OverlayRecord(BaseModel):
    repo: str
    scope: Literal["alias_local", "pair_local"]
    name: str
    summary: str
    guidance: list[str] = Field(default_factory=list)
    applies_to_tasks: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class AliasOverlayUpsertRequest(BaseModel):
    repo: str
    alias_name: str
    summary: str
    guidance: list[str] = Field(default_factory=list)
    applies_to_tasks: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class PairOverlayUpsertRequest(BaseModel):
    repo: str
    pair_key: str
    summary: str
    guidance: list[str] = Field(default_factory=list)
    applies_to_tasks: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class OverlayUpsertResponse(BaseModel):
    stored: OverlayRecord


class DecisionStateBuildRequest(BaseModel):
    repo: str
    task_id: str
    title: str
    body: str
    changed_files_hint: list[str] = Field(default_factory=list)


class DecisionState(BaseModel):
    repo: str
    task_id: str
    issue_summary: str
    macro_constraints: list[str] = Field(default_factory=list)
    meso_context: list[str] = Field(default_factory=list)
    micro_context: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HealthResponse(BaseModel):
    version: str = "0.1.0"
    status: str = "ok"
    details: dict[str, Any] = Field(default_factory=dict)


class WorkerRepoRequest(BaseModel):
    repo: str
    task_id: str


class RepoPrepareRequest(WorkerRepoRequest):
    base_branch: str = "main"


class ReadFileRequest(WorkerRepoRequest):
    path: str


class WriteFileRequest(ReadFileRequest):
    content: str


class RunCommandRequest(WorkerRepoRequest):
    command_key: str
    args: list[str] = Field(default_factory=list)


class RunTestsRequest(WorkerRepoRequest):
    tests: list[str] = Field(default_factory=list)


class GitCommitRequest(WorkerRepoRequest):
    message: str




class MemoryIngestRequest(BaseModel):
    repo: str


class MemoryIngestResponse(BaseModel):
    repo: str
    ingested_rows: int

class CandidateGenerationRequest(BaseModel):
    decision_state: DecisionState
    alias_name: str | None = None
    pair_key: str | None = None


class CandidateGenerationResponse(BaseModel):
    candidates: list[CandidatePlan] = Field(default_factory=list)
    rejected: list[dict[str, Any]] = Field(default_factory=list)
    feasible_count: int = 0
    infeasible_count: int = 0
    active_overlays: list[str] = Field(default_factory=list)


class FrontierBuildRequest(BaseModel):
    candidates: list[CandidatePlan] = Field(default_factory=list)


class FrontierBuildResponse(BaseModel):
    pareto_candidates: list[CandidatePlan] = Field(default_factory=list)
    deduped_candidates: list[CandidatePlan] = Field(default_factory=list)
    medoid_candidates: list[CandidatePlan] = Field(default_factory=list)
    gram_matrix: list[list[float]] = Field(default_factory=list)


class ArbiterDecisionRequest(BaseModel):
    decision_state: DecisionState
    frontier_candidates: list[CandidatePlan] = Field(default_factory=list)
    rejected_candidates: list[dict[str, Any]] = Field(default_factory=list)


class ArbiterDecisionResponse(BaseModel):
    status: str
    selected_candidate: CandidatePlan | None = None
    notes: list[str] = Field(default_factory=list)


class ReviewerVerdict(BaseModel):
    verdict: Literal["approve", "block", "revise"]
    blocking_issues: list[str] = Field(default_factory=list)
    non_blocking_issues: list[str] = Field(default_factory=list)
    suggested_repairs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ExecutionRunRequest(BaseModel):
    job_id: str
    repo: str
    task_id: str
    base_branch: str = "main"
    idempotency_key: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    decision_state: DecisionState
    selected_candidate: CandidatePlan


class ExecutionRunResponse(BaseModel):
    job_id: str
    stage: str
    status: str
    artifacts: dict[str, Any] = Field(default_factory=dict)
    reviewer_verdict: ReviewerVerdict
    repair_result: dict[str, Any] = Field(default_factory=dict)
    cause_code: str | None = None
    replayed: bool = False
    idempotency_key: str | None = None


class ExecutionStateResponse(BaseModel):
    job_id: str
    stage: str
    status: str
    transitions: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)


class ExecutionPackageRequest(BaseModel):
    job_id: str
    repo: str
    idempotency_key: str | None = None
    decision_state: DecisionState
    chosen_candidate: CandidatePlan
    feasible_unchosen_candidates: list[CandidatePlan] = Field(default_factory=list)
    execution_result: ExecutionRunResponse


class DraftPRPayloadResponse(BaseModel):
    title: str
    body: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryWriteReport(BaseModel):
    chosen_written: bool
    frontier_written: int
    residual_written: bool
    surprise_reasons: list[str] = Field(default_factory=list)


class ExecutionPackageResponse(BaseModel):
    job_id: str
    draft_pr: DraftPRPayloadResponse
    memory_report: MemoryWriteReport
    cause_code: str | None = None
    replayed: bool = False
    idempotency_key: str | None = None


class TelemetryEvent(BaseModel):
    id: int
    job_id: str
    route: str
    phase: str
    status: str
    cause_code: str
    replayed: bool
    idempotency_key: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TelemetryListResponse(BaseModel):
    events: list[TelemetryEvent] = Field(default_factory=list)


class CancelJobRequest(BaseModel):
    reason: str = "operator_cancelled"


class JobControlResponse(BaseModel):
    job_id: str
    cancelled: bool
    reason: str | None = None
    updated_at: datetime


class ResumeExecuteRequest(BaseModel):
    execute_request: ExecutionRunRequest
    checkpoint_stage: str


class RetryPackageRequest(BaseModel):
    package_request: ExecutionPackageRequest
    allow_duplicate_side_effects: bool = False
    approval_token: str | None = None
    approval_reason_code: str | None = None


class CheckpointResponse(BaseModel):
    job_id: str
    checkpoints: list[str] = Field(default_factory=list)


class TelemetrySummaryBucket(BaseModel):
    route: str
    phase: str
    status: str
    cause_code: str
    replayed: bool
    count: int


class TelemetrySummaryResponse(BaseModel):
    buckets: list[TelemetrySummaryBucket] = Field(default_factory=list)


class InvariantCheck(BaseModel):
    name: str
    ok: bool
    cause_code: str | None = None
    details: str = ""


class InvariantReportResponse(BaseModel):
    job_id: str
    ok: bool
    checks: list[InvariantCheck] = Field(default_factory=list)


class OperatorLedgerEntry(BaseModel):
    id: int
    job_id: str
    actor_role: str
    action: str
    reason_code: str
    approved: bool
    cause_code: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class OperatorLedgerResponse(BaseModel):
    entries: list[OperatorLedgerEntry] = Field(default_factory=list)


class JobEscalationResponse(BaseModel):
    job_id: str
    failure_streak: int
    escalated: bool
    level: int
    reason_code: str
    updated_at: datetime
