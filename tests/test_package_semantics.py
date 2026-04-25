from fastapi.testclient import TestClient

from apps.conductor.main import app
from shared.schemas.models import CandidatePlan, DecisionState, MicroTargets, ObjectiveVector, ReviewerVerdict


def _candidate() -> CandidatePlan:
    return CandidatePlan(
        title="candidate",
        summary="summary",
        role="minimal_patch",
        macro_vec=[-1, -1, 1, -1, 1, -1],
        meso_tags=["api"],
        micro_targets=MicroTargets(files=["src/a.py"], tests=["tests/a.py"]),
        objective_vec=ObjectiveVector(
            correctness_confidence=0.9,
            reversibility=0.9,
            locality=0.9,
            maintainability=0.9,
            delivery_speed=0.9,
        ),
        rollback_plan="rollback",
        test_plan=["tests/a.py"],
        risk_notes=["risk"],
    )


def _decision() -> DecisionState:
    return DecisionState(repo="repo", task_id="t-1", issue_summary="issue")


def _execution_payload(status: str) -> dict:
    stage = "completed" if status == "completed" else status
    return {
        "job_id": "job-1",
        "stage": stage,
        "status": status,
        "artifacts": {
            "changed_files": ["src/a.py"],
            "diff": "diff --git",
            "lint_output": {"ok": status == "completed"},
            "typecheck_output": {"ok": status == "completed"},
            "test_output": {"ok": status == "completed"},
        },
        "reviewer_verdict": ReviewerVerdict(
            verdict="approve" if status == "completed" else "block",
            blocking_issues=[] if status == "completed" else ["blocked"],
            non_blocking_issues=[],
            suggested_repairs=[],
            confidence=0.8,
        ).model_dump(mode="json"),
        "repair_result": {"attempted": status != "completed"},
    }


def _package_payload(status: str) -> dict:
    return {
        "job_id": "job-1",
        "repo": "repo",
        "decision_state": _decision().model_dump(mode="json"),
        "chosen_candidate": _candidate().model_dump(mode="json"),
        "feasible_unchosen_candidates": [],
        "execution_result": _execution_payload(status),
    }


def test_package_endpoint_completed_status_allows_canonical_memory_writes():
    client = TestClient(app)
    response = client.post(
        "/jobs/job-1/package",
        json=_package_payload("completed"),
        headers={"Authorization": "Bearer replace_me"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["draft_pr"]["metadata"]["package_mode"] == "canonical"
    assert data["memory_report"]["chosen_written"] is True


def test_package_endpoint_blocked_status_downgrades_to_draft_only_mode():
    client = TestClient(app)
    response = client.post(
        "/jobs/job-1/package",
        json=_package_payload("blocked"),
        headers={"Authorization": "Bearer replace_me"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["draft_pr"]["metadata"]["package_mode"] == "draft_only"
    assert data["memory_report"]["chosen_written"] is False


def test_package_endpoint_rejects_in_progress_execution_status():
    client = TestClient(app)
    response = client.post(
        "/jobs/job-1/package",
        json=_package_payload("reviewing"),
        headers={"Authorization": "Bearer replace_me"},
    )
    assert response.status_code == 409
    assert "not packageable" in response.json()["detail"]

