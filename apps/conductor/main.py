from __future__ import annotations

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from apps.conductor.db.models import create_session_factory
from apps.conductor.services.arbiter import ArbiterService
from apps.conductor.services.candidate_generation import CandidateGenerationService
from apps.conductor.services.decision_state import DecisionStateService
from apps.conductor.services.feasibility import FeasibilityService
from apps.conductor.services.frontier import FrontierService
from apps.conductor.services.retrieval import MemoryRetrievalService
from shared.clients.omlx_client import OMLXClient
from shared.config.settings import ConductorSettings
from shared.schemas.models import (
    ArbiterDecisionRequest,
    ArbiterDecisionResponse,
    CandidateGenerationRequest,
    CandidateGenerationResponse,
    DecisionStateBuildRequest,
    FrontierBuildRequest,
    FrontierBuildResponse,
    HealthResponse,
    JobCreate,
    JobStatus,
    MemoryQueryRequest,
    MemoryQueryResponse,
)

settings = ConductorSettings()
SessionFactory = create_session_factory(settings.db_url)
omlx_client = OMLXClient(settings)
retrieval_service = MemoryRetrievalService(omlx_client=omlx_client)
candidate_generation_service = CandidateGenerationService(omlx_client=omlx_client)
feasibility_service = FeasibilityService()
frontier_service = FrontierService()
arbiter_service = ArbiterService(omlx_client=omlx_client, feasibility_service=feasibility_service)

authored_jobs: dict[str, JobStatus] = {}

app = FastAPI(title="frontier-conductor", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    endpoints = settings.omlx_endpoints().model_dump()
    return HealthResponse(details={"db_url": settings.db_url, "omlx_endpoints": endpoints, "queue_depth": len(authored_jobs)})


@app.post("/jobs", response_model=JobStatus)
def create_job(request: JobCreate) -> JobStatus:
    job_id = f"{request.task_id}:{len(authored_jobs) + 1}"
    record = JobStatus(id=job_id, status="queued", stage="created")
    authored_jobs[job_id] = record
    return record


@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str) -> JobStatus:
    job = authored_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.post("/decision-state/build")
def build_decision_state(request: DecisionStateBuildRequest):
    decision_state = DecisionStateService.build(request)
    with SessionFactory() as session:
        # Persist compact structured payload; no raw transcript storage.
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


@app.post("/memory/query", response_model=MemoryQueryResponse)
def query_memory(request: MemoryQueryRequest) -> MemoryQueryResponse:
    overlays: list[str] = []
    if request.alias_name:
        overlays.append(f"alias-local:{request.alias_name}")
    if request.pair_key:
        overlays.append(f"pair-local:{request.pair_key}")

    with SessionFactory() as session:
        bundle = retrieval_service.query(session=session, query=request.query, top_k=request.top_k)

    return MemoryQueryResponse(hits=bundle.reranked, applied_overlays=overlays)


@app.post("/candidates/generate", response_model=CandidateGenerationResponse)
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


@app.post("/frontier/build", response_model=FrontierBuildResponse)
def build_frontier(request: FrontierBuildRequest) -> FrontierBuildResponse:
    result = frontier_service.build_frontier(request.candidates)
    return FrontierBuildResponse(
        pareto_candidates=result.pareto_candidates,
        deduped_candidates=result.deduped_candidates,
        medoid_candidates=result.medoid_candidates,
        gram_matrix=result.gram_matrix,
    )


@app.post("/arbiter/decide", response_model=ArbiterDecisionResponse)
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
