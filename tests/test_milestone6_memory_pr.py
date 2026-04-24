from sqlalchemy import text

from apps.conductor.db.models import create_session_factory
from apps.conductor.services.memory_writer import MemoryWriterService
from apps.conductor.services.pr_writer import PRWriterService
from shared.schemas.models import (
    CandidatePlan,
    DecisionState,
    ExecutionRunResponse,
    MicroTargets,
    ObjectiveVector,
    ReviewerVerdict,
)


def candidate(name: str, objective=None, files=None):
    objective = objective or {
        "correctness_confidence": 0.8,
        "reversibility": 0.9,
        "locality": 0.9,
        "maintainability": 0.7,
        "delivery_speed": 0.8,
    }
    return CandidatePlan(
        title=name,
        summary=f"summary {name}",
        role="minimal_patch",
        macro_vec=[-1, -1, 1, -1, 1, -1],
        meso_tags=["api"],
        micro_targets=MicroTargets(files=files or [f"src/{name}.py"], tests=[f"tests/{name}.py"]),
        objective_vec=ObjectiveVector(**objective),
        rollback_plan="revert commit",
        test_plan=[f"tests/{name}.py"],
        risk_notes=["risk"],
    )


def execution(status="completed", reviewer=None, ok=True):
    reviewer = reviewer or ReviewerVerdict(
        verdict="approve", blocking_issues=[], non_blocking_issues=[], suggested_repairs=[], confidence=0.9
    )
    return ExecutionRunResponse(
        job_id="job-1",
        stage="completed",
        status=status,
        artifacts={
            "changed_files": ["src/a.py"],
            "diff": "diff --git",
            "lint_output": {"ok": ok},
            "typecheck_output": {"ok": ok},
            "test_output": {"ok": ok},
        },
        reviewer_verdict=reviewer,
        repair_result={"attempted": False},
    )


def test_pr_payload_composition_shape():
    writer = PRWriterService()
    payload = writer.build_draft_payload(
        repo="repo",
        job_id="job-1",
        decision_state=DecisionState(repo="repo", task_id="t1", issue_summary="issue"),
        chosen_candidate=candidate("chosen"),
        alternatives=[candidate("alt-1")],
        execution_result=execution(),
    )

    assert payload.title.startswith("[DRAFT]")
    assert "## Summary" in payload.body
    assert "## Chosen Strategy" in payload.body
    assert "## Alternatives Considered" in payload.body
    assert "## Validation Evidence" in payload.body
    assert "## Reviewer Objections and Resolution" in payload.body
    assert "## Rollback Note" in payload.body
    assert "## Known Risks" in payload.body


def test_chosen_memory_write_occurs_when_expected_and_no_raw_transcript_persisted():
    service = MemoryWriterService()
    SessionFactory = create_session_factory("sqlite+pysqlite:///:memory:")

    with SessionFactory() as session:
        result = service.write_package(
            session=session,
            repo="repo",
            decision_state=DecisionState(repo="repo", task_id="t1", issue_summary="issue"),
            chosen_candidate=candidate("chosen"),
            feasible_unchosen=[],
            execution_result=execution(),
        )
        row = session.execute(text("SELECT payload FROM chosen_memory")).fetchone()

    assert result.chosen_written is True
    payload = row[0]
    assert "messages" not in str(payload)
    assert "prompt" not in str(payload)


def test_frontier_memory_gating_rejects_duplicate_or_dominated_alternatives():
    service = MemoryWriterService()
    SessionFactory = create_session_factory("sqlite+pysqlite:///:memory:")
    chosen = candidate("chosen", objective={
        "correctness_confidence": 0.95,
        "reversibility": 0.95,
        "locality": 0.95,
        "maintainability": 0.95,
        "delivery_speed": 0.95,
    })
    duplicate_like = candidate("dup", files=["src/chosen.py"], objective={
        "correctness_confidence": 0.95,
        "reversibility": 0.95,
        "locality": 0.95,
        "maintainability": 0.95,
        "delivery_speed": 0.95,
    })
    dominated = candidate("dominated", objective={
        "correctness_confidence": 0.70,
        "reversibility": 0.70,
        "locality": 0.70,
        "maintainability": 0.70,
        "delivery_speed": 0.70,
    })

    infeasible = dominated.model_copy(update={"test_plan": []})

    with SessionFactory() as session:
        result = service.write_package(
            session=session,
            repo="repo",
            decision_state=DecisionState(repo="repo", task_id="t1", issue_summary="issue"),
            chosen_candidate=chosen,
            feasible_unchosen=[duplicate_like, infeasible],
            execution_result=execution(),
        )

    assert result.frontier_written == 0


def test_residual_not_written_on_ordinary_success():
    service = MemoryWriterService()
    SessionFactory = create_session_factory("sqlite+pysqlite:///:memory:")

    with SessionFactory() as session:
        result = service.write_package(
            session=session,
            repo="repo",
            decision_state=DecisionState(repo="repo", task_id="t1", issue_summary="issue"),
            chosen_candidate=candidate("chosen"),
            feasible_unchosen=[],
            execution_result=execution(status="completed", ok=True),
        )
        residual_rows = session.execute(text("SELECT COUNT(*) FROM residual_memory")).scalar_one()

    assert result.residual_written is False
    assert residual_rows == 0


def test_residual_written_on_surprise():
    service = MemoryWriterService()
    SessionFactory = create_session_factory("sqlite+pysqlite:///:memory:")
    blocked_reviewer = ReviewerVerdict(
        verdict="block",
        blocking_issues=["missed regression"],
        non_blocking_issues=[],
        suggested_repairs=["add regression test"],
        confidence=0.8,
    )

    with SessionFactory() as session:
        result = service.write_package(
            session=session,
            repo="repo",
            decision_state=DecisionState(repo="repo", task_id="t1", issue_summary="issue"),
            chosen_candidate=candidate("chosen"),
            feasible_unchosen=[],
            execution_result=execution(status="blocked", reviewer=blocked_reviewer, ok=False),
        )
        residual_rows = session.execute(text("SELECT COUNT(*) FROM residual_memory")).scalar_one()

    assert result.residual_written is True
    assert residual_rows == 1
    assert "reviewer_caught_important_issue" in result.surprise_reasons
