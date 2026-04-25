import time

from fastapi.testclient import TestClient
from sqlalchemy import text

import apps.conductor.main as conductor_main
from apps.conductor.db.models import create_session_factory
from shared.schemas.models import CandidatePlan, DecisionState, MicroTargets, ObjectiveVector, ReviewerVerdict


AUTH = {"Authorization": "Bearer replace_me"}


def _candidate():
    return CandidatePlan(
        title="candidate",
        summary="summary",
        role="minimal_patch",
        macro_vec=[-1, -1, 1, -1, 1, -1],
        meso_tags=["api"],
        micro_targets=MicroTargets(files=["src/a.py"], tests=["tests/a_test.py"]),
        objective_vec=ObjectiveVector(
            correctness_confidence=0.9,
            reversibility=0.9,
            locality=0.9,
            maintainability=0.9,
            delivery_speed=0.9,
        ),
        rollback_plan="rollback",
        test_plan=["tests/a_test.py"],
    )


def _decision():
    return DecisionState(repo="repo", task_id="t1", issue_summary="issue")


class FakeExecutionService:
    def __init__(self, sleep_seconds: float = 0):
        self.calls = 0
        self.sleep_seconds = sleep_seconds

    def run_single_candidate(self, **kwargs):
        self.calls += 1
        if self.sleep_seconds:
            time.sleep(self.sleep_seconds)
        return {
            "job_id": kwargs["job_id"],
            "stage": "completed",
            "status": "completed",
            "artifacts": {"changed_files": ["src/a.py"], "diagnostics": {"cause_code": "EXEC_SUCCESS"}},
            "reviewer_verdict": ReviewerVerdict(
                verdict="approve",
                blocking_issues=[],
                non_blocking_issues=[],
                suggested_repairs=[],
                confidence=0.9,
            ).model_dump(mode="json"),
            "repair_result": {"attempted": False},
            "cause_code": "EXEC_SUCCESS",
        }


def _execute_payload(job_id: str, idem: str, timeout_seconds: int | None = None):
    return {
        "job_id": job_id,
        "repo": "repo",
        "task_id": "t1",
        "base_branch": "main",
        "idempotency_key": idem,
        "timeout_seconds": timeout_seconds,
        "decision_state": _decision().model_dump(mode="json"),
        "selected_candidate": _candidate().model_dump(mode="json"),
    }


def _install_factory(monkeypatch, tmp_path):
    sf = create_session_factory(f"sqlite+pysqlite:///{tmp_path}/m9.db")
    monkeypatch.setattr(conductor_main, "SessionFactory", sf)


def test_cancel_control_path_blocks_future_execute(monkeypatch, tmp_path):
    _install_factory(monkeypatch, tmp_path)
    monkeypatch.setattr(conductor_main, "execution_service", FakeExecutionService())
    client = TestClient(conductor_main.app)

    cancel = client.post("/jobs/job-1/cancel", json={"reason": "operator_cancel"}, headers=AUTH)
    run = client.post("/jobs/job-1/execute", json=_execute_payload("job-1", "idem-1"), headers=AUTH)

    assert cancel.status_code == 200
    assert run.status_code == 409
    assert run.json()["detail"]["cause_code"] == "EXEC_CANCELLED"


def test_retry_vs_replay_distinction(monkeypatch, tmp_path):
    _install_factory(monkeypatch, tmp_path)
    fake_exec = FakeExecutionService()
    monkeypatch.setattr(conductor_main, "execution_service", fake_exec)
    client = TestClient(conductor_main.app)

    first = client.post("/jobs/job-2/execute", json=_execute_payload("job-2", "idem-replay"), headers=AUTH)
    replay = client.post("/jobs/job-2/execute", json=_execute_payload("job-2", "idem-replay"), headers=AUTH)
    retry = client.post("/jobs/job-2/retry-execute", json=_execute_payload("job-2", "idem-retry"), headers=AUTH)

    assert first.status_code == 200
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert retry.status_code == 200 and retry.json()["replayed"] is False
    assert fake_exec.calls == 2


def test_resume_from_checkpoint_requires_valid_boundary(monkeypatch, tmp_path):
    _install_factory(monkeypatch, tmp_path)
    fake_exec = FakeExecutionService()
    monkeypatch.setattr(conductor_main, "execution_service", fake_exec)
    with conductor_main.SessionFactory() as session:
        session.execute(
            text(
                """
                INSERT INTO execution_state(job_id, repo, task_id, stage, status, selected_candidate, artifacts, transitions, updated_at)
                VALUES ('job-3', 'repo', 't1', 'validating', 'running', '{}', '{}', '[{\"stage\":\"prepared\"},{\"stage\":\"validating\"}]', CURRENT_TIMESTAMP)
                """
            )
        )
        session.commit()
    client = TestClient(conductor_main.app)
    valid = client.post(
        "/jobs/job-3/resume-execute",
        json={"checkpoint_stage": "validating", "execute_request": _execute_payload("job-3", "idem-resume")},
        headers=AUTH,
    )
    invalid = client.post(
        "/jobs/job-3/resume-execute",
        json={"checkpoint_stage": "queued", "execute_request": _execute_payload("job-3", "idem-resume-2")},
        headers=AUTH,
    )

    assert valid.status_code == 200
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["cause_code"] == "RESUME_INVALID_CHECKPOINT"


def test_timeout_consistency_marks_failed_with_timeout_cause(monkeypatch, tmp_path):
    _install_factory(monkeypatch, tmp_path)
    fake_exec = FakeExecutionService(sleep_seconds=1.05)
    monkeypatch.setattr(conductor_main, "execution_service", fake_exec)
    client = TestClient(conductor_main.app)

    timed = client.post("/jobs/job-4/execute", json=_execute_payload("job-4", "idem-timeout", timeout_seconds=1), headers=AUTH)
    assert timed.status_code == 200
    assert timed.json()["status"] == "failed"
    assert timed.json()["cause_code"] == "EXEC_TIMEOUT_EXCEEDED"


def test_telemetry_summary_low_cardinality_buckets(monkeypatch, tmp_path):
    _install_factory(monkeypatch, tmp_path)
    monkeypatch.setattr(conductor_main, "execution_service", FakeExecutionService())
    client = TestClient(conductor_main.app)

    client.post("/jobs/job-5/execute", json=_execute_payload("job-5", "idem-a"), headers=AUTH)
    client.post("/jobs/job-5/execute", json=_execute_payload("job-5", "idem-a"), headers=AUTH)
    summary = client.get("/telemetry/summary", headers=AUTH)

    assert summary.status_code == 200
    buckets = summary.json()["buckets"]
    assert len(buckets) >= 1
    assert {"route", "phase", "status", "cause_code", "replayed", "count"}.issubset(buckets[0].keys())


def test_invariant_failure_mode_returns_non_ok_report(monkeypatch, tmp_path):
    _install_factory(monkeypatch, tmp_path)
    with conductor_main.SessionFactory() as session:
        session.execute(
            text(
                """
                INSERT INTO package_idempotency(job_id, idempotency_key, status, cause_code, response_payload, updated_at)
                VALUES ('job-6', 'idem-pkg', 'completed', 'PACKAGE_OK_CANONICAL', :payload, CURRENT_TIMESTAMP)
                """
            ),
            {"payload": '{"memory_report":{"chosen_written":true}}'},
        )
        session.commit()
    client = TestClient(conductor_main.app)
    report = client.get("/jobs/job-6/invariants", headers=AUTH)
    assert report.status_code == 200
    body = report.json()
    assert body["ok"] is False
    assert any((not item["ok"]) for item in body["checks"])
