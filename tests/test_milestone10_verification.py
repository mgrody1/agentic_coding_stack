import json
import inspect

from fastapi.testclient import TestClient
from sqlalchemy import text

import apps.conductor.main as conductor_main
from apps.conductor.db.models import create_session_factory
from shared.schemas.models import CandidatePlan, DecisionState, MicroTargets, ObjectiveVector, ReviewerVerdict

AUTH = {"Authorization": "Bearer replace_me"}


def _headers(role: str) -> dict[str, str]:
    return {**AUTH, "X-Operator-Role": role}


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
    def run_single_candidate(self, **kwargs):
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


def _execute_payload(job_id: str, idem: str):
    return {
        "job_id": job_id,
        "repo": "repo",
        "task_id": "t1",
        "base_branch": "main",
        "idempotency_key": idem,
        "decision_state": _decision().model_dump(mode="json"),
        "selected_candidate": _candidate().model_dump(mode="json"),
    }


def _package_payload(job_id: str, idem: str):
    return {
        "job_id": job_id,
        "repo": "repo",
        "idempotency_key": idem,
        "decision_state": _decision().model_dump(mode="json"),
        "chosen_candidate": _candidate().model_dump(mode="json"),
        "feasible_unchosen_candidates": [],
        "execution_result": {
            "job_id": job_id,
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
        },
    }


def _install_factory(monkeypatch, tmp_path):
    sf = create_session_factory(f"sqlite+pysqlite:///{tmp_path}/m10.db")
    monkeypatch.setattr(conductor_main, "SessionFactory", sf)


def test_policy_guards_enforced_for_cancel_retry_resume_and_replay(monkeypatch, tmp_path):
    _install_factory(monkeypatch, tmp_path)
    monkeypatch.setattr(conductor_main, "execution_service", FakeExecutionService())
    client = TestClient(conductor_main.app)

    first = client.post("/jobs/job-10/execute", json=_execute_payload("job-10", "idem-r"), headers=_headers("operator"))
    replay_forbidden = client.post("/jobs/job-10/execute", json=_execute_payload("job-10", "idem-r"), headers=_headers("viewer"))

    retry_viewer = client.post("/jobs/job-10/retry-execute", json=_execute_payload("job-10", "idem-r2"), headers=_headers("viewer"))

    with conductor_main.SessionFactory() as session:
        session.execute(
            text(
                """
                INSERT INTO execution_state(job_id, repo, task_id, stage, status, selected_candidate, artifacts, transitions, updated_at)
                VALUES ('job-10', 'repo', 't1', 'validating', 'running', '{}', '{}', '[{"stage":"prepared"},{"stage":"validating"}]', CURRENT_TIMESTAMP)
                """
            )
        )
        session.commit()
    resume_viewer = client.post(
        "/jobs/job-10/resume-execute",
        json={"checkpoint_stage": "validating", "execute_request": _execute_payload("job-10", "idem-r3")},
        headers=_headers("viewer"),
    )
    cancel_viewer = client.post("/jobs/job-10/cancel", json={"reason": "test"}, headers=_headers("viewer"))

    assert first.status_code == 200
    assert replay_forbidden.status_code == 403
    assert replay_forbidden.json()["detail"]["cause_code"] == "POLICY_ROLE_FORBIDDEN"

    assert cancel_viewer.status_code == 403
    assert retry_viewer.status_code == 403
    assert resume_viewer.status_code == 403
    assert cancel_viewer.json()["detail"]["cause_code"] == "POLICY_ROLE_FORBIDDEN"
    assert retry_viewer.json()["detail"]["cause_code"] == "POLICY_ROLE_FORBIDDEN"
    assert resume_viewer.json()["detail"]["cause_code"] == "POLICY_ROLE_FORBIDDEN"


def test_retry_package_requires_approval_token_and_reason_for_sensitive_retries(monkeypatch, tmp_path):
    _install_factory(monkeypatch, tmp_path)
    monkeypatch.setattr(conductor_main, "execution_service", FakeExecutionService())
    client = TestClient(conductor_main.app)

    first = client.post("/jobs/job-11/package", json=_package_payload("job-11", "idem-pkg-1"), headers=_headers("operator"))
    blocked_no_side_effects = client.post(
        "/jobs/job-11/retry-package",
        json={"package_request": _package_payload("job-11", "idem-pkg-2"), "allow_duplicate_side_effects": False},
        headers=_headers("admin"),
    )
    blocked_missing_approval = client.post(
        "/jobs/job-11/retry-package",
        json={"package_request": _package_payload("job-11", "idem-pkg-3"), "allow_duplicate_side_effects": True},
        headers=_headers("admin"),
    )
    blocked_bad_token = client.post(
        "/jobs/job-11/retry-package",
        json={
            "package_request": _package_payload("job-11", "idem-pkg-4"),
            "allow_duplicate_side_effects": True,
            "approval_token": "nope",
            "approval_reason_code": "ops_override",
        },
        headers=_headers("admin"),
    )
    blocked_bad_reason = client.post(
        "/jobs/job-11/retry-package",
        json={
            "package_request": _package_payload("job-11", "idem-pkg-5"),
            "allow_duplicate_side_effects": True,
            "approval_token": "approve_me",
            "approval_reason_code": "not_allowed",
        },
        headers=_headers("admin"),
    )
    approved = client.post(
        "/jobs/job-11/retry-package",
        json={
            "package_request": _package_payload("job-11", "idem-pkg-6"),
            "allow_duplicate_side_effects": True,
            "approval_token": "approve_me",
            "approval_reason_code": "ops_override",
        },
        headers=_headers("admin"),
    )

    assert first.status_code == 200
    assert blocked_no_side_effects.status_code == 409
    assert blocked_no_side_effects.json()["detail"]["cause_code"] == "RETRY_PACKAGE_SIDE_EFFECT_BLOCKED"
    assert blocked_missing_approval.status_code == 409
    assert blocked_missing_approval.json()["detail"]["cause_code"] == "APPROVAL_REQUIRED_FOR_DUPLICATE_PACKAGE_RETRY"
    assert blocked_bad_token.status_code == 409
    assert blocked_bad_token.json()["detail"]["cause_code"] == "APPROVAL_TOKEN_INVALID"
    assert blocked_bad_reason.status_code == 409
    assert blocked_bad_reason.json()["detail"]["cause_code"] == "APPROVAL_REASON_CODE_INVALID"
    assert approved.status_code == 200


def test_escalation_levels_increment_bound_and_reset(monkeypatch, tmp_path):
    _install_factory(monkeypatch, tmp_path)

    with conductor_main.SessionFactory() as session:
        conductor_main.escalation_service.observe_execution_outcome(
            session=session,
            job_id="job-12",
            status="failed",
            cause_code="EXEC_FAILED",
            threshold=2,
        )
        row1 = session.execute(
            text("SELECT failure_streak, escalated, level FROM job_escalation WHERE job_id = 'job-12'")
        ).fetchone()

    with conductor_main.SessionFactory() as session:
        conductor_main.escalation_service.observe_execution_outcome(
            session=session,
            job_id="job-12",
            status="blocked",
            cause_code="EXEC_BLOCKED",
            threshold=2,
        )
        row2 = session.execute(
            text("SELECT failure_streak, escalated, level FROM job_escalation WHERE job_id = 'job-12'")
        ).fetchone()

    with conductor_main.SessionFactory() as session:
        conductor_main.escalation_service.observe_execution_outcome(
            session=session,
            job_id="job-12",
            status="failed",
            cause_code="EXEC_FAILED",
            threshold=2,
        )
        row3 = session.execute(
            text("SELECT failure_streak, escalated, level FROM job_escalation WHERE job_id = 'job-12'")
        ).fetchone()

    with conductor_main.SessionFactory() as session:
        conductor_main.escalation_service.observe_execution_outcome(
            session=session,
            job_id="job-12",
            status="completed",
            cause_code="EXEC_SUCCESS",
            threshold=2,
        )
        row4 = session.execute(
            text("SELECT failure_streak, escalated, level FROM job_escalation WHERE job_id = 'job-12'")
        ).fetchone()

    assert tuple(row1) == (1, 0, 0)
    assert tuple(row2) == (2, 1, 1)
    assert tuple(row3) == (3, 1, 2)
    assert tuple(row4) == (0, 0, 0)


def test_operator_ledger_shape_and_reason_code_on_execute_replay(monkeypatch, tmp_path):
    _install_factory(monkeypatch, tmp_path)
    monkeypatch.setattr(conductor_main, "execution_service", FakeExecutionService())
    client = TestClient(conductor_main.app)

    first = client.post("/jobs/job-13/execute", json=_execute_payload("job-13", "idem-ledger"), headers=_headers("operator"))
    replay = client.post("/jobs/job-13/execute", json=_execute_payload("job-13", "idem-ledger"), headers=_headers("operator"))

    assert first.status_code == 200
    assert replay.status_code == 200

    with conductor_main.SessionFactory() as session:
        row = session.execute(
            text(
                """
                SELECT actor_role, action, reason_code, approved, cause_code, details
                FROM operator_action_ledger WHERE job_id = :job_id ORDER BY id DESC LIMIT 1
                """
            ),
            {"job_id": "job-13"},
        ).fetchone()

    assert row is not None
    assert row[0] == "operator"
    assert row[1] == "replay_execute"
    assert row[2] == "REPLAY_KEY_MATCH"
    assert row[3] == 1
    assert row[4] == "EXEC_REPLAYED"
    assert isinstance(json.loads(row[5]), dict)


def test_operator_ledger_records_each_governed_control_action(monkeypatch, tmp_path):
    _install_factory(monkeypatch, tmp_path)
    monkeypatch.setattr(conductor_main, "execution_service", FakeExecutionService())
    client = TestClient(conductor_main.app)

    client.post("/jobs/job-14/execute", json=_execute_payload("job-14", "idem-control"), headers=_headers("operator"))
    client.post("/jobs/job-14/retry-execute", json=_execute_payload("job-14", "idem-control-2"), headers=_headers("operator"))
    with conductor_main.SessionFactory() as session:
        session.execute(
            text(
                """
                INSERT INTO execution_state(job_id, repo, task_id, stage, status, selected_candidate, artifacts, transitions, updated_at)
                VALUES ('job-14', 'repo', 't1', 'validating', 'running', '{}', '{}', '[{"stage":"prepared"},{"stage":"validating"}]', CURRENT_TIMESTAMP)
                """
            )
        )
        session.commit()
    client.post(
        "/jobs/job-14/resume-execute",
        json={"checkpoint_stage": "validating", "execute_request": _execute_payload("job-14", "idem-control-3")},
        headers=_headers("operator"),
    )
    client.post("/jobs/job-14/package", json=_package_payload("job-14", "idem-control-pkg-1"), headers=_headers("operator"))
    client.post(
        "/jobs/job-14/retry-package",
        json={
            "package_request": _package_payload("job-14", "idem-control-pkg-2"),
            "allow_duplicate_side_effects": True,
            "approval_token": "approve_me",
            "approval_reason_code": "ops_override",
        },
        headers=_headers("admin"),
    )
    client.post("/jobs/job-14/execute", json=_execute_payload("job-14", "idem-control"), headers=_headers("operator"))
    client.post("/jobs/job-14/package", json=_package_payload("job-14", "idem-control-pkg-1"), headers=_headers("operator"))
    client.post("/jobs/job-14/cancel", json={"reason": "done"}, headers=_headers("operator"))

    with conductor_main.SessionFactory() as session:
        rows = session.execute(
            text("SELECT action FROM operator_action_ledger WHERE job_id = :job_id"),
            {"job_id": "job-14"},
        ).fetchall()
    actions = {row[0] for row in rows}
    assert {"cancel", "retry_execute", "resume_execute", "retry_package", "replay_execute", "replay_package"}.issubset(actions)


def test_main_routes_delegate_governance_control_logic_to_helpers():
    cancel_src = inspect.getsource(conductor_main.cancel_job)
    resume_src = inspect.getsource(conductor_main.resume_execute)
    retry_exec_src = inspect.getsource(conductor_main.retry_execute)
    retry_pkg_src = inspect.getsource(conductor_main.retry_package)

    assert "control_plane_service.cancel" in cancel_src
    assert "control_plane_service.resume_validate_and_record" in resume_src
    assert "control_plane_service.retry_execute_record" in retry_exec_src
    assert "control_plane_service.retry_package_validate_and_record" in retry_pkg_src
