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
    def __init__(self):
        self.calls = 0

    def run_single_candidate(self, **kwargs):
        self.calls += 1
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


class FakeMemoryWriter:
    def __init__(self):
        self.calls = 0

    def write_package(self, **kwargs):
        self.calls += 1
        return type(
            "R",
            (),
            {
                "chosen_written": True,
                "frontier_written": 0,
                "residual_written": False,
                "surprise_reasons": [],
            },
        )()


def _execute_payload(idem_key: str | None = None):
    return {
        "job_id": "job-1",
        "repo": "repo",
        "task_id": "t1",
        "base_branch": "main",
        "idempotency_key": idem_key,
        "decision_state": _decision().model_dump(mode="json"),
        "selected_candidate": _candidate().model_dump(mode="json"),
    }


def _package_payload(status: str, idem_key: str | None = None):
    return {
        "job_id": "job-1",
        "repo": "repo",
        "idempotency_key": idem_key,
        "decision_state": _decision().model_dump(mode="json"),
        "chosen_candidate": _candidate().model_dump(mode="json"),
        "feasible_unchosen_candidates": [],
        "execution_result": {
            "job_id": "job-1",
            "stage": status,
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
        },
    }


def _install_test_session_factory(monkeypatch, tmp_path):
    sf = create_session_factory(f"sqlite+pysqlite:///{tmp_path}/m8.db")
    monkeypatch.setattr(conductor_main, "SessionFactory", sf)


def test_execute_endpoint_idempotent_replay(monkeypatch, tmp_path):
    _install_test_session_factory(monkeypatch, tmp_path)
    fake_exec = FakeExecutionService()
    monkeypatch.setattr(conductor_main, "execution_service", fake_exec)
    client = TestClient(conductor_main.app)

    first = client.post("/jobs/job-1/execute", json=_execute_payload("idem-exec-1"), headers=AUTH)
    second = client.post("/jobs/job-1/execute", json=_execute_payload("idem-exec-1"), headers=AUTH)

    assert first.status_code == 200
    assert second.status_code == 200
    assert fake_exec.calls == 1
    assert first.json()["replayed"] is False
    assert second.json()["replayed"] is True
    assert second.json()["cause_code"] == "EXEC_SUCCESS"


def test_execute_replay_in_progress_returns_conflict(monkeypatch, tmp_path):
    _install_test_session_factory(monkeypatch, tmp_path)
    with conductor_main.SessionFactory() as session:
        session.execute(
            text(
                """
                INSERT INTO execution_idempotency(job_id, idempotency_key, status, cause_code, response_payload, updated_at)
                VALUES ('job-2', 'idem-exec-2', 'in_progress', 'EXEC_IN_PROGRESS', '{}', CURRENT_TIMESTAMP)
                """
            )
        )
        session.commit()
    client = TestClient(conductor_main.app)
    payload = _execute_payload("idem-exec-2")
    payload["job_id"] = "job-2"
    response = client.post("/jobs/job-2/execute", json=payload, headers=AUTH)
    assert response.status_code == 409
    assert response.json()["detail"]["cause_code"] == "EXEC_REPLAY_IN_PROGRESS"


def test_package_endpoint_idempotent_replay_prevents_duplicate_memory_write(monkeypatch, tmp_path):
    _install_test_session_factory(monkeypatch, tmp_path)
    fake_writer = FakeMemoryWriter()
    monkeypatch.setattr(conductor_main, "memory_writer_service", fake_writer)
    client = TestClient(conductor_main.app)

    first = client.post("/jobs/job-1/package", json=_package_payload("completed", "idem-pkg-1"), headers=AUTH)
    second = client.post("/jobs/job-1/package", json=_package_payload("completed", "idem-pkg-1"), headers=AUTH)

    assert first.status_code == 200
    assert second.status_code == 200
    assert fake_writer.calls == 1
    assert first.json()["replayed"] is False
    assert second.json()["replayed"] is True
    assert second.json()["cause_code"] == "PACKAGE_OK_CANONICAL"


def test_telemetry_shape_and_cause_codes(monkeypatch, tmp_path):
    _install_test_session_factory(monkeypatch, tmp_path)
    fake_exec = FakeExecutionService()
    monkeypatch.setattr(conductor_main, "execution_service", fake_exec)
    client = TestClient(conductor_main.app)

    run = client.post("/jobs/job-1/execute", json=_execute_payload("idem-exec-telemetry"), headers=AUTH)
    assert run.status_code == 200

    telemetry = client.get("/jobs/job-1/telemetry", headers=AUTH)
    assert telemetry.status_code == 200
    events = telemetry.json()["events"]
    assert len(events) >= 1
    assert {"route", "phase", "status", "cause_code", "replayed", "idempotency_key", "details"}.issubset(events[0].keys())
    assert any(item["cause_code"] == "EXEC_SUCCESS" for item in events)


def test_package_rejected_status_emits_stable_cause_code(monkeypatch, tmp_path):
    _install_test_session_factory(monkeypatch, tmp_path)
    client = TestClient(conductor_main.app)

    rejected = client.post("/jobs/job-1/package", json=_package_payload("reviewing", "idem-pkg-reject"), headers=AUTH)
    assert rejected.status_code == 409

    telemetry = client.get("/jobs/job-1/telemetry", headers=AUTH)
    assert telemetry.status_code == 200
    assert any(item["cause_code"] == "PACKAGE_REJECTED_STATUS" for item in telemetry.json()["events"])


def test_execution_state_json_round_trip_consistency(monkeypatch, tmp_path):
    _install_test_session_factory(monkeypatch, tmp_path)
    client = TestClient(conductor_main.app)
    with conductor_main.SessionFactory() as session:
        session.execute(
            text(
                """
                INSERT INTO execution_state(job_id, repo, task_id, stage, status, selected_candidate, artifacts, transitions, updated_at)
                VALUES ('job-json', 'repo', 't1', 'completed', 'completed', :selected_candidate, :artifacts, :transitions, CURRENT_TIMESTAMP)
                """
            ),
            {
                "selected_candidate": '{"title":"candidate"}',
                "artifacts": '{"changed_files":["src/a.py"]}',
                "transitions": '[{"stage":"completed","status":"completed"}]',
            },
        )
        session.commit()

    state = client.get("/jobs/job-json/execution-state", headers=AUTH)
    assert state.status_code == 200
    body = state.json()
    assert isinstance(body["transitions"], list)
    assert isinstance(body["artifacts"], dict)
