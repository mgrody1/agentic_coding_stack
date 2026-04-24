from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import text

from apps.conductor.db.models import create_session_factory
from apps.conductor.services.arbiter import ArbiterService
from apps.conductor.services.candidate_generation import CandidateGenerationService
from apps.conductor.services.decision_state import DecisionStateService
from apps.conductor.services.execution import ExecutionService
from apps.conductor.services.feasibility import FeasibilityService
from apps.conductor.services.frontier import FrontierService
from apps.conductor.services.memory_writer import MemoryWriterService
from apps.conductor.services.pr_writer import PRWriterService
from apps.conductor.services.retrieval import MemoryRetrievalService
from shared.clients.omlx_client import OMLXClient
from shared.clients.worker_client import WorkerClient
from shared.config.settings import ConductorSettings
from shared.schemas.models import (
    ArbiterDecisionRequest,
    ArbiterDecisionResponse,
    CandidateGenerationRequest,
    CandidateGenerationResponse,
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
    JobCreate,
    JobStatus,
    MemoryIngestRequest,
    MemoryIngestResponse,
    MemoryQueryRequest,
    MemoryQueryResponse,
    MemoryWriteReport,
    ReviewerVerdict,
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

authored_jobs: dict[str, JobStatus] = {}

app = FastAPI(title="frontier-conductor", version="0.1.0")


def _auth(authorization: str | None = Header(default=None)) -> None:
    require_bearer(settings.api_token, authorization)


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
    return ExecutionStateResponse(job_id=job_id, stage=row[0], status=row[1], transitions=row[2] or [], artifacts=row[3] or {})


@app.post("/jobs/{job_id}/execute", response_model=ExecutionRunResponse, dependencies=[Depends(_auth)])
def execute_job(job_id: str, request: ExecutionRunRequest) -> ExecutionRunResponse:
    if request.job_id != job_id:
        raise HTTPException(status_code=400, detail="job id mismatch")
    with SessionFactory() as session:
        result = execution_service.run_single_candidate(
            session=session,
            job_id=job_id,
            repo=request.repo,
            task_id=request.task_id,
            base_branch=request.base_branch,
            decision_state=request.decision_state,
            selected_candidate=request.selected_candidate,
        )
    return ExecutionRunResponse(
        job_id=result["job_id"],
        stage=result["stage"],
        status=result["status"],
        artifacts=result["artifacts"],
        reviewer_verdict=ReviewerVerdict.model_validate(result["reviewer_verdict"]),
        repair_result=result["repair_result"],
    )


@app.post("/jobs/{job_id}/package", response_model=ExecutionPackageResponse, dependencies=[Depends(_auth)])
def package_execution(job_id: str, request: ExecutionPackageRequest) -> ExecutionPackageResponse:
    if request.job_id != job_id:
        raise HTTPException(status_code=400, detail="job id mismatch")

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

    return ExecutionPackageResponse(
        job_id=request.job_id,
        draft_pr=DraftPRPayloadResponse(title=draft.title, body=draft.body, metadata=draft.metadata),
        memory_report=MemoryWriteReport(
            chosen_written=memory.chosen_written,
            frontier_written=memory.frontier_written,
            residual_written=memory.residual_written,
            surprise_reasons=memory.surprise_reasons,
        ),
    )


@app.post("/decision-state/build", dependencies=[Depends(_auth)])
def build_decision_state(request: DecisionStateBuildRequest):
    decision_state = DecisionStateService.build(request)
    with SessionFactory() as session:
        session.execute(
            text("INSERT INTO decision_state(repo, task_id, payload, created_at) VALUES (:repo, :task_id, :payload, :created_at)"),
            {
                "repo": decision_state.repo,
                "task_id": decision_state.task_id,
                "payload": decision_state.model_dump(mode="json"),
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
        bundle = retrieval_service.query(session=session, query=request.query, top_k=request.top_k)

    return MemoryQueryResponse(hits=bundle.reranked, applied_overlays=overlays)


@app.post("/memory/ingest", response_model=MemoryIngestResponse, dependencies=[Depends(_auth)])
def ingest_memory(request: MemoryIngestRequest) -> MemoryIngestResponse:
    with SessionFactory() as session:
        count = retrieval_service.refresh_fts_from_memory_tables(session=session, repo=request.repo)
    return MemoryIngestResponse(repo=request.repo, ingested_rows=count)


@app.post("/candidates/generate", response_model=CandidateGenerationResponse, dependencies=[Depends(_auth)])
def generate_candidates(request: CandidateGenerationRequest) -> CandidateGenerationResponse:
    generated = candidate_generation_service.generate(request.decision_state)
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
