from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import text

from apps.conductor.db.models import create_session_factory
from apps.conductor.services.arbiter import ArbiterService
from apps.conductor.services.candidate_generation import CandidateGenerationService
from apps.conductor.services.control_plane import ControlPlaneService
from apps.conductor.services.decision_state import DecisionStateService
from apps.conductor.services.execution import ExecutionService
from apps.conductor.services.escalation import EscalationService
from apps.conductor.services.feasibility import FeasibilityService
from apps.conductor.services.frontier import FrontierService
from apps.conductor.services.governance import GovernanceService
from apps.conductor.services.invariants import InvariantService
from apps.conductor.services.memory_writer import MemoryWriterService
from apps.conductor.services.overlay_state import OverlayStateService
from apps.conductor.services.package_semantics import classify_package_status
from apps.conductor.services.pr_writer import PRWriterService
from apps.conductor.services.reliability import (
    TelemetryService,
    derive_idempotency_key,
    stable_json_dumps,
    stable_json_loads,
)
from apps.conductor.services.retrieval import MemoryRetrievalService
from shared.clients.omlx_client import OMLXClient
from shared.clients.worker_client import WorkerClient
from shared.config.settings import ConductorSettings
from shared.schemas.models import (
    ArbiterDecisionRequest,
    ArbiterDecisionResponse,
    AliasOverlayUpsertRequest,
    CancelJobRequest,
    CandidateGenerationRequest,
    CandidateGenerationResponse,
    CheckpointResponse,
    DecisionStateBuildRequest,
    DraftPRPayloadResponse,
    ExecutionPackageRequest,
    ExecutionPackageResponse,
    ExecutionRunRequest,
    ExecutionRunResponse,
    ExecutionStateResponse,
    FrontierBuildRequest,
    FrontierBuildResponse,
    HealthResponse,
    InvariantReportResponse,
    JobCreate,
    JobControlResponse,
    JobEscalationResponse,
    JobStatus,
    MemoryIngestRequest,
    MemoryIngestResponse,
    MemoryQueryRequest,
    MemoryQueryResponse,
    MemoryWriteReport,
    OverlayUpsertResponse,
    PairOverlayUpsertRequest,
    ResumeExecuteRequest,
    RetryPackageRequest,
    OperatorLedgerResponse,
    ReviewerVerdict,
    TelemetryListResponse,
    TelemetrySummaryResponse,
)
from shared.utils.auth import require_bearer

settings = ConductorSettings()
SessionFactory = create_session_factory(settings.db_url)
omlx_client = OMLXClient(settings)
worker_client = WorkerClient(base_url=settings.worker_m2_url, token=settings.worker_token)
retrieval_service = MemoryRetrievalService(omlx_client=omlx_client)
candidate_generation_service = CandidateGenerationService(omlx_client=omlx_client)
feasibility_service = FeasibilityService()
frontier_service = FrontierService()
arbiter_service = ArbiterService(omlx_client=omlx_client, feasibility_service=feasibility_service)
execution_service = ExecutionService(worker_client=worker_client, reviewer_client=omlx_client)
pr_writer_service = PRWriterService()
memory_writer_service = MemoryWriterService()
overlay_state_service = OverlayStateService()
telemetry_service = TelemetryService()
invariant_service = InvariantService()
governance_service = GovernanceService()
escalation_service = EscalationService()
control_plane_service = ControlPlaneService(
    governance_service=governance_service,
    telemetry_service=telemetry_service,
    approval_token=settings.approval_token,
)

authored_jobs: dict[str, JobStatus] = {}

app = FastAPI(title="frontier-conductor", version="0.1.0")
VALID_CHECKPOINTS = {"prepared", "validating", "reviewing", "repairing", "finalizing", "completed", "blocked", "failed"}


def _auth(authorization: str | None = Header(default=None)) -> None:
    require_bearer(settings.api_token, authorization)


def _operator_role(x_operator_role: str | None = Header(default=None)) -> str:
    return (x_operator_role or "operator").strip().lower()


def _is_cancelled(session, job_id: str) -> tuple[bool, str]:
    row = session.execute(
        text("SELECT cancelled, reason FROM job_control WHERE job_id = :job_id"),
        {"job_id": job_id},
    ).fetchone()
    if not row:
        return False, ""
    return bool(row[0]), str(row[1] or "")


@app.get("/health", response_model=HealthResponse, dependencies=[Depends(_auth)])
def health() -> HealthResponse:
    endpoints = settings.omlx_endpoints().model_dump()
    return HealthResponse(details={"db_url": settings.db_url, "omlx_endpoints": endpoints, "queue_depth": len(authored_jobs)})


@app.post("/jobs", response_model=JobStatus, dependencies=[Depends(_auth)])
def create_job(request: JobCreate) -> JobStatus:
    job_id = f"{request.task_id}:{len(authored_jobs) + 1}"
    record = JobStatus(id=job_id, status="queued", stage="created")
    authored_jobs[job_id] = record
    return record


@app.get("/jobs/{job_id}", response_model=JobStatus, dependencies=[Depends(_auth)])
def get_job(job_id: str) -> JobStatus:
    job = authored_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/jobs/{job_id}/execution-state", response_model=ExecutionStateResponse, dependencies=[Depends(_auth)])
def get_execution_state(job_id: str) -> ExecutionStateResponse:
    with SessionFactory() as session:
        row = session.execute(
            text("SELECT stage, status, transitions, artifacts FROM execution_state WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="execution state not found")
    transitions = row[2] or []
    artifacts = row[3] or {}
    if isinstance(transitions, str):
        transitions = json.loads(transitions)
    if isinstance(artifacts, str):
        artifacts = json.loads(artifacts)
    return ExecutionStateResponse(job_id=job_id, stage=row[0], status=row[1], transitions=transitions, artifacts=artifacts)


@app.post("/jobs/{job_id}/execute", response_model=ExecutionRunResponse, dependencies=[Depends(_auth)])
def execute_job(job_id: str, request: ExecutionRunRequest, actor_role: str = Depends(_operator_role)) -> ExecutionRunResponse:
    if request.job_id != job_id:
        raise HTTPException(status_code=400, detail="job id mismatch")
    request_payload = request.model_dump(mode="json")
    idem_key = derive_idempotency_key("execute", request_payload, explicit_key=request.idempotency_key)
    with SessionFactory() as session:
        cancelled, cancel_reason = _is_cancelled(session, job_id)
        if cancelled:
            telemetry_service.emit(
                session=session,
                job_id=job_id,
                route="execute",
                phase="validate",
                status="blocked",
                cause_code="EXEC_CANCELLED",
                replayed=False,
                idempotency_key=idem_key,
                details={"reason": cancel_reason},
            )
            raise HTTPException(status_code=409, detail={"cause_code": "EXEC_CANCELLED", "reason": cancel_reason})
        row = session.execute(
            text(
                """
                SELECT status, response_payload, cause_code FROM execution_idempotency
                WHERE job_id = :job_id AND idempotency_key = :idempotency_key
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"job_id": job_id, "idempotency_key": idem_key},
        ).fetchone()
        if row and row[0] == "completed":
            governance_service.authorize_action(
                session=session,
                job_id=job_id,
                actor_role=actor_role,
                action="replay_execute",
                reason_code="REPLAY_KEY_MATCH",
                cause_code="EXEC_REPLAYED",
                details={"idempotency_key": idem_key},
            )
            payload = stable_json_loads(row[1], fallback={})
            telemetry_service.emit(
                session=session,
                job_id=job_id,
                route="execute",
                phase="replay",
                status="ok",
                cause_code="EXEC_REPLAYED",
                replayed=True,
                idempotency_key=idem_key,
                details={"mode": "idempotent_replay"},
            )
            payload["replayed"] = True
            payload["idempotency_key"] = idem_key
            return ExecutionRunResponse.model_validate(payload)
        if row and row[0] == "in_progress":
            governance_service.enforce_role(action="replay_execute", actor_role=actor_role)
            telemetry_service.emit(
                session=session,
                job_id=job_id,
                route="execute",
                phase="replay",
                status="blocked",
                cause_code="EXEC_REPLAY_IN_PROGRESS",
                replayed=True,
                idempotency_key=idem_key,
            )
            raise HTTPException(status_code=409, detail={"cause_code": "EXEC_REPLAY_IN_PROGRESS"})
        session.execute(
            text(
                """
                INSERT INTO execution_idempotency(job_id, idempotency_key, status, cause_code, response_payload, updated_at)
                VALUES (:job_id, :idempotency_key, 'in_progress', 'EXEC_IN_PROGRESS', '{}', :updated_at)
                """
            ),
            {"job_id": job_id, "idempotency_key": idem_key, "updated_at": datetime.now(timezone.utc).isoformat()},
        )
        session.commit()
        started_at = datetime.now(timezone.utc)
        result = execution_service.run_single_candidate(
            session=session,
            job_id=job_id,
            repo=request.repo,
            task_id=request.task_id,
            base_branch=request.base_branch,
            decision_state=request.decision_state,
            selected_candidate=request.selected_candidate,
        )
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        if request.timeout_seconds is not None and elapsed > request.timeout_seconds:
            result = {
                "job_id": result["job_id"],
                "stage": "failed",
                "status": "failed",
                "artifacts": {
                    **result["artifacts"],
                    "diagnostics": {
                        "cause_code": "EXEC_TIMEOUT_EXCEEDED",
                        "elapsed_seconds": round(elapsed, 6),
                        "timeout_seconds": request.timeout_seconds,
                    },
                },
                "reviewer_verdict": result["reviewer_verdict"],
                "repair_result": result["repair_result"],
                "cause_code": "EXEC_TIMEOUT_EXCEEDED",
            }
        response_payload = {
            "job_id": result["job_id"],
            "stage": result["stage"],
            "status": result["status"],
            "artifacts": result["artifacts"],
            "reviewer_verdict": result["reviewer_verdict"],
            "repair_result": result["repair_result"],
            "cause_code": result.get("cause_code"),
            "replayed": False,
            "idempotency_key": idem_key,
        }
        session.execute(
            text(
                """
                UPDATE execution_idempotency
                SET status = 'completed', cause_code = :cause_code, response_payload = :payload, updated_at = :updated_at
                WHERE job_id = :job_id AND idempotency_key = :idempotency_key
                """
            ),
            {
                "job_id": job_id,
                "idempotency_key": idem_key,
                "cause_code": result.get("cause_code", ""),
                "payload": stable_json_dumps(response_payload),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        session.commit()
        telemetry_service.emit(
            session=session,
            job_id=job_id,
            route="execute",
            phase="final",
            status=result["status"],
            cause_code=result.get("cause_code", "EXEC_UNKNOWN"),
            replayed=False,
            idempotency_key=idem_key,
            details={"stage": result["stage"]},
        )
        escalation_service.observe_execution_outcome(
            session=session,
            job_id=job_id,
            status=result["status"],
            cause_code=result.get("cause_code", "EXEC_UNKNOWN"),
            threshold=settings.escalation_failure_streak_threshold,
        )
        session.execute(
            text(
                """
                INSERT INTO job_control(job_id, cancelled, reason, updated_at)
                VALUES (:job_id, 0, :reason, :updated_at)
                ON CONFLICT(job_id) DO UPDATE SET
                    reason = excluded.reason,
                    updated_at = excluded.updated_at
                """
            ),
            {
                "job_id": job_id,
                "reason": f"checkpoint:{result['stage']}",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        session.commit()
    return ExecutionRunResponse(
        job_id=result["job_id"],
        stage=result["stage"],
        status=result["status"],
        artifacts=result["artifacts"],
        reviewer_verdict=ReviewerVerdict.model_validate(result["reviewer_verdict"]),
        repair_result=result["repair_result"],
        cause_code=result.get("cause_code"),
        replayed=False,
        idempotency_key=idem_key,
    )


@app.post("/jobs/{job_id}/package", response_model=ExecutionPackageResponse, dependencies=[Depends(_auth)])
def package_execution(job_id: str, request: ExecutionPackageRequest, actor_role: str = Depends(_operator_role)) -> ExecutionPackageResponse:
    if request.job_id != job_id:
        raise HTTPException(status_code=400, detail="job id mismatch")
    request_payload = request.model_dump(mode="json")
    idem_key = derive_idempotency_key("package", request_payload, explicit_key=request.idempotency_key)
    package_semantics = classify_package_status(request.execution_result.status)
    if package_semantics.rejected:
        with SessionFactory() as session:
            telemetry_service.emit(
                session=session,
                job_id=job_id,
                route="package",
                phase="validate",
                status="blocked",
                cause_code="PACKAGE_REJECTED_STATUS",
                replayed=False,
                idempotency_key=idem_key,
                details={"execution_status": request.execution_result.status},
            )
        raise HTTPException(
            status_code=409,
            detail=f"execution status '{request.execution_result.status}' is not packageable",
        )
    with SessionFactory() as session:
        row = session.execute(
            text(
                """
                SELECT status, response_payload FROM package_idempotency
                WHERE job_id = :job_id AND idempotency_key = :idempotency_key
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"job_id": job_id, "idempotency_key": idem_key},
        ).fetchone()
        if row and row[0] == "completed":
            governance_service.authorize_action(
                session=session,
                job_id=job_id,
                actor_role=actor_role,
                action="replay_package",
                reason_code="REPLAY_KEY_MATCH",
                cause_code="PACKAGE_REPLAYED",
                details={"idempotency_key": idem_key},
            )
            payload = stable_json_loads(row[1], fallback={})
            telemetry_service.emit(
                session=session,
                job_id=job_id,
                route="package",
                phase="replay",
                status="ok",
                cause_code="PACKAGE_REPLAYED",
                replayed=True,
                idempotency_key=idem_key,
            )
            payload["replayed"] = True
            payload["idempotency_key"] = idem_key
            return ExecutionPackageResponse.model_validate(payload)
        if row and row[0] == "in_progress":
            governance_service.enforce_role(action="replay_package", actor_role=actor_role)
            telemetry_service.emit(
                session=session,
                job_id=job_id,
                route="package",
                phase="replay",
                status="blocked",
                cause_code="PACKAGE_REPLAY_IN_PROGRESS",
                replayed=True,
                idempotency_key=idem_key,
            )
            raise HTTPException(status_code=409, detail={"cause_code": "PACKAGE_REPLAY_IN_PROGRESS"})
        session.execute(
            text(
                """
                INSERT INTO package_idempotency(job_id, idempotency_key, status, cause_code, response_payload, updated_at)
                VALUES (:job_id, :idempotency_key, 'in_progress', 'PACKAGE_IN_PROGRESS', '{}', :updated_at)
                """
            ),
            {"job_id": job_id, "idempotency_key": idem_key, "updated_at": datetime.now(timezone.utc).isoformat()},
        )
        session.commit()

    draft = pr_writer_service.build_draft_payload(
        repo=request.repo,
        job_id=request.job_id,
        decision_state=request.decision_state,
        chosen_candidate=request.chosen_candidate,
        alternatives=request.feasible_unchosen_candidates,
        execution_result=request.execution_result,
    )

    with SessionFactory() as session:
        memory = memory_writer_service.write_package(
            session=session,
            repo=request.repo,
            decision_state=request.decision_state,
            chosen_candidate=request.chosen_candidate,
            feasible_unchosen=request.feasible_unchosen_candidates,
            execution_result=request.execution_result,
        )
        cause_code = "PACKAGE_OK_CANONICAL" if package_semantics.mode == "canonical" else "PACKAGE_OK_DRAFT_ONLY"
        response_payload = {
            "job_id": request.job_id,
            "draft_pr": {"title": draft.title, "body": draft.body, "metadata": {**draft.metadata, "package_mode": package_semantics.mode}},
            "memory_report": {
                "chosen_written": memory.chosen_written,
                "frontier_written": memory.frontier_written,
                "residual_written": memory.residual_written,
                "surprise_reasons": memory.surprise_reasons,
            },
            "cause_code": cause_code,
            "replayed": False,
            "idempotency_key": idem_key,
        }
        session.execute(
            text(
                """
                UPDATE package_idempotency
                SET status='completed', cause_code=:cause_code, response_payload=:payload, updated_at=:updated_at
                WHERE job_id=:job_id AND idempotency_key=:idempotency_key
                """
            ),
            {
                "job_id": job_id,
                "idempotency_key": idem_key,
                "cause_code": cause_code,
                "payload": stable_json_dumps(response_payload),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        session.commit()
        telemetry_service.emit(
            session=session,
            job_id=job_id,
            route="package",
            phase="final",
            status="completed",
            cause_code=cause_code,
            replayed=False,
            idempotency_key=idem_key,
            details={"package_mode": package_semantics.mode},
        )

    return ExecutionPackageResponse(
        job_id=request.job_id,
        draft_pr=DraftPRPayloadResponse(
            title=draft.title,
            body=draft.body,
            metadata={**draft.metadata, "package_mode": package_semantics.mode},
        ),
        memory_report=MemoryWriteReport(
            chosen_written=memory.chosen_written,
            frontier_written=memory.frontier_written,
            residual_written=memory.residual_written,
            surprise_reasons=memory.surprise_reasons,
        ),
        cause_code="PACKAGE_OK_CANONICAL" if package_semantics.mode == "canonical" else "PACKAGE_OK_DRAFT_ONLY",
        replayed=False,
        idempotency_key=idem_key,
    )


@app.post("/jobs/{job_id}/cancel", response_model=JobControlResponse, dependencies=[Depends(_auth)])
def cancel_job(job_id: str, request: CancelJobRequest, actor_role: str = Depends(_operator_role)) -> JobControlResponse:
    with SessionFactory() as session:
        now = control_plane_service.cancel(session=session, job_id=job_id, reason=request.reason, actor_role=actor_role)
    return JobControlResponse(job_id=job_id, cancelled=True, reason=request.reason, updated_at=now)


@app.get("/jobs/{job_id}/checkpoints", response_model=CheckpointResponse, dependencies=[Depends(_auth)])
def get_checkpoints(job_id: str) -> CheckpointResponse:
    with SessionFactory() as session:
        row = session.execute(
            text("SELECT transitions FROM execution_state WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="execution state not found")
    transitions = stable_json_loads(row[0], fallback=[])
    stages = [item.get("stage") for item in transitions if isinstance(item, dict)]
    checkpoints = [stage for stage in stages if stage in VALID_CHECKPOINTS]
    return CheckpointResponse(job_id=job_id, checkpoints=checkpoints)


@app.post("/jobs/{job_id}/resume-execute", response_model=ExecutionRunResponse, dependencies=[Depends(_auth)])
def resume_execute(job_id: str, request: ResumeExecuteRequest, actor_role: str = Depends(_operator_role)) -> ExecutionRunResponse:
    if request.execute_request.job_id != job_id:
        raise HTTPException(status_code=400, detail="job id mismatch")
    with SessionFactory() as session:
        control_plane_service.resume_validate_and_record(
            session=session,
            job_id=job_id,
            idempotency_key=request.execute_request.idempotency_key or "",
            checkpoint_stage=request.checkpoint_stage,
            actor_role=actor_role,
        )
    return execute_job(job_id=job_id, request=request.execute_request, actor_role=actor_role)


@app.post("/jobs/{job_id}/retry-execute", response_model=ExecutionRunResponse, dependencies=[Depends(_auth)])
def retry_execute(job_id: str, request: ExecutionRunRequest, actor_role: str = Depends(_operator_role)) -> ExecutionRunResponse:
    if request.job_id != job_id:
        raise HTTPException(status_code=400, detail="job id mismatch")
    with SessionFactory() as session:
        control_plane_service.retry_execute_record(
            session=session,
            job_id=job_id,
            idempotency_key=request.idempotency_key or "",
            actor_role=actor_role,
        )
    return execute_job(job_id=job_id, request=request, actor_role=actor_role)


@app.post("/jobs/{job_id}/retry-package", response_model=ExecutionPackageResponse, dependencies=[Depends(_auth)])
def retry_package(job_id: str, request: RetryPackageRequest, actor_role: str = Depends(_operator_role)) -> ExecutionPackageResponse:
    if request.package_request.job_id != job_id:
        raise HTTPException(status_code=400, detail="job id mismatch")
    with SessionFactory() as session:
        existing = session.execute(
            text("SELECT COUNT(*) FROM package_idempotency WHERE job_id = :job_id AND status = 'completed'"),
            {"job_id": job_id},
        ).scalar_one()
        control_plane_service.retry_package_validate_and_record(
            session=session,
            job_id=job_id,
            idempotency_key=request.package_request.idempotency_key or "",
            existing_completed_count=int(existing),
            allow_duplicate_side_effects=request.allow_duplicate_side_effects,
            approval_token=request.approval_token,
            approval_reason_code=request.approval_reason_code,
            actor_role=actor_role,
        )
    return package_execution(job_id=job_id, request=request.package_request, actor_role=actor_role)


@app.post("/decision-state/build", dependencies=[Depends(_auth)])
def build_decision_state(request: DecisionStateBuildRequest):
    decision_state = DecisionStateService.build(request)
    with SessionFactory() as session:
        session.execute(
            text("INSERT INTO decision_state(repo, task_id, payload, created_at) VALUES (:repo, :task_id, :payload, :created_at)"),
            {
                "repo": decision_state.repo,
                "task_id": decision_state.task_id,
                "payload": json.dumps(decision_state.model_dump(mode="json")),
                "created_at": decision_state.created_at,
            },
        )
        session.commit()
    return decision_state


@app.post("/memory/query", response_model=MemoryQueryResponse, dependencies=[Depends(_auth)])
def query_memory(request: MemoryQueryRequest) -> MemoryQueryResponse:
    overlays: list[str] = []
    if request.alias_name:
        overlays.append(f"alias-local:{request.alias_name}")
    if request.pair_key:
        overlays.append(f"pair-local:{request.pair_key}")

    with SessionFactory() as session:
        bundle = retrieval_service.query(
            session=session,
            query=request.query,
            top_k=request.top_k,
            repo=request.repo,
            alias_name=request.alias_name,
            pair_key=request.pair_key,
        )

    return MemoryQueryResponse(hits=bundle.reranked, applied_overlays=overlays)


@app.post("/memory/overlay/alias", response_model=OverlayUpsertResponse, dependencies=[Depends(_auth)])
def upsert_alias_overlay(request: AliasOverlayUpsertRequest) -> OverlayUpsertResponse:
    with SessionFactory() as session:
        stored = overlay_state_service.upsert_alias_overlay(session=session, request=request)
    return OverlayUpsertResponse(stored=stored)


@app.post("/memory/overlay/pair", response_model=OverlayUpsertResponse, dependencies=[Depends(_auth)])
def upsert_pair_overlay(request: PairOverlayUpsertRequest) -> OverlayUpsertResponse:
    with SessionFactory() as session:
        stored = overlay_state_service.upsert_pair_overlay(session=session, request=request)
    return OverlayUpsertResponse(stored=stored)


@app.post("/memory/ingest", response_model=MemoryIngestResponse, dependencies=[Depends(_auth)])
def ingest_memory(request: MemoryIngestRequest) -> MemoryIngestResponse:
    with SessionFactory() as session:
        count = retrieval_service.refresh_fts_from_memory_tables(session=session, repo=request.repo)
    return MemoryIngestResponse(repo=request.repo, ingested_rows=count)


@app.post("/candidates/generate", response_model=CandidateGenerationResponse, dependencies=[Depends(_auth)])
def generate_candidates(request: CandidateGenerationRequest) -> CandidateGenerationResponse:
    with SessionFactory() as session:
        memory_bundle = retrieval_service.query(
            session=session,
            query=request.decision_state.issue_summary,
            top_k=3,
            repo=request.decision_state.repo,
            task_id=request.decision_state.task_id,
            alias_name=request.alias_name,
            pair_key=request.pair_key,
        )
        overlay_resolution = overlay_state_service.resolve(
            session=session,
            repo=request.decision_state.repo,
            task_id=request.decision_state.task_id,
            macro_constraints=request.decision_state.macro_constraints,
            global_memory=[hit.text for hit in memory_bundle.reranked if hit.source not in {"alias_overlay", "pair_overlay"}],
            alias_name=request.alias_name,
            pair_key=request.pair_key,
        )

    generated = candidate_generation_service.generate(
        request.decision_state,
        overlay_resolution=overlay_resolution,
    )
    feasible, infeasible = feasibility_service.gate(generated.valid_candidates)
    return CandidateGenerationResponse(
        candidates=[item.candidate for item in feasible],
        rejected=generated.rejected_candidates
        + [
            {
                "role": result.candidate.role,
                "reason": "feasibility_failed",
                "notes": result.certificate.notes,
            }
            for result in infeasible
        ],
        feasible_count=len(feasible),
        infeasible_count=len(infeasible),
        active_overlays=overlay_resolution.active_overlays,
    )


@app.post("/frontier/build", response_model=FrontierBuildResponse, dependencies=[Depends(_auth)])
def build_frontier(request: FrontierBuildRequest) -> FrontierBuildResponse:
    result = frontier_service.build_frontier(request.candidates)
    return FrontierBuildResponse(
        pareto_candidates=result.pareto_candidates,
        deduped_candidates=result.deduped_candidates,
        medoid_candidates=result.medoid_candidates,
        gram_matrix=result.gram_matrix,
    )


@app.post("/arbiter/decide", response_model=ArbiterDecisionResponse, dependencies=[Depends(_auth)])
def arbiter_decide(request: ArbiterDecisionRequest) -> ArbiterDecisionResponse:
    outcome = arbiter_service.decide(
        decision_state=request.decision_state,
        frontier_candidates=request.frontier_candidates,
        rejected_candidates=request.rejected_candidates,
    )
    return ArbiterDecisionResponse(
        status=outcome.status,
        selected_candidate=outcome.selected_candidate,
        notes=outcome.notes,
    )


@app.get("/jobs/{job_id}/telemetry", response_model=TelemetryListResponse, dependencies=[Depends(_auth)])
def get_job_telemetry(job_id: str) -> TelemetryListResponse:
    with SessionFactory() as session:
        rows = session.execute(
            text(
                """
                SELECT id, job_id, route, phase, status, cause_code, replayed, idempotency_key, details, created_at
                FROM telemetry_event
                WHERE job_id = :job_id
                ORDER BY id ASC
                """
            ),
            {"job_id": job_id},
        ).fetchall()
    return TelemetryListResponse(
        events=[
            {
                "id": int(row[0]),
                "job_id": row[1],
                "route": row[2],
                "phase": row[3],
                "status": row[4],
                "cause_code": row[5],
                "replayed": bool(row[6]),
                "idempotency_key": row[7],
                "details": stable_json_loads(row[8], fallback={}),
                "created_at": row[9],
            }
            for row in rows
        ]
    )


@app.get("/telemetry/summary", response_model=TelemetrySummaryResponse, dependencies=[Depends(_auth)])
def telemetry_summary() -> TelemetrySummaryResponse:
    with SessionFactory() as session:
        rows = session.execute(
            text(
                """
                SELECT route, phase, status, cause_code, replayed, COUNT(*)
                FROM telemetry_event
                GROUP BY route, phase, status, cause_code, replayed
                ORDER BY COUNT(*) DESC, route ASC
                """
            )
        ).fetchall()
    return TelemetrySummaryResponse(
        buckets=[
            {
                "route": row[0],
                "phase": row[1],
                "status": row[2],
                "cause_code": row[3],
                "replayed": bool(row[4]),
                "count": int(row[5]),
            }
            for row in rows
        ]
    )


@app.get("/jobs/{job_id}/invariants", response_model=InvariantReportResponse, dependencies=[Depends(_auth)])
def invariant_report(job_id: str) -> InvariantReportResponse:
    with SessionFactory() as session:
        checks = invariant_service.validate_job(session=session, job_id=job_id)
    ok = all(item.ok for item in checks)
    return InvariantReportResponse(job_id=job_id, ok=ok, checks=checks)
