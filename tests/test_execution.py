from sqlalchemy import text

from apps.conductor.db.models import create_session_factory
from apps.conductor.services.execution import ExecutionService
from shared.schemas.models import CandidatePlan, DecisionState, MicroTargets, ObjectiveVector


class FakeWorkerClient:
    def __init__(self):
        self.run_command_calls = 0

    def prepare_repo(self, repo, task_id, base_branch):
        return {"worktree_path": f"/tmp/{task_id}", "branch_name": f"task/{task_id}"}

    def run_lint(self, repo, task_id):
        return {"ok": True, "stdout": "lint ok"}

    def run_typecheck(self, repo, task_id):
        return {"ok": True, "stdout": "typecheck ok"}

    def run_tests(self, repo, task_id, tests):
        return {"ok": True, "stdout": "tests ok", "tests": tests}

    def git_diff(self, repo, task_id):
        return {"diff": "diff --git a b", "changed_files": ["src/a.py", "tests/a_test.py"]}

    def run_command(self, repo, task_id, command_key, args):
        self.run_command_calls += 1
        return {"ok": True, "command_key": command_key, "args": args, "stdout": "repair command"}


class FakeReviewerClient:
    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.calls = 0

    def chat(self, alias, messages, **kwargs):
        result = self.verdicts[min(self.calls, len(self.verdicts) - 1)]
        self.calls += 1
        return {"choices": [{"message": {"content": result}}]}


def make_candidate():
    return CandidatePlan(
        title="candidate",
        summary="summary",
        role="minimal_patch",
        macro_vec=[-1, -1, 1, -1, 1, -1],
        meso_tags=["api"],
        micro_targets=MicroTargets(files=["src/a.py"], tests=["tests/a_test.py"]),
        objective_vec=ObjectiveVector(
            correctness_confidence=0.8,
            reversibility=0.9,
            locality=0.9,
            maintainability=0.7,
            delivery_speed=0.85,
        ),
        rollback_plan="revert commit",
        test_plan=["tests/a_test.py"],
    )


def make_decision():
    return DecisionState(repo="repo", task_id="t1", issue_summary="fix issue")


def test_execution_stage_transitions_success_path():
    SessionFactory = create_session_factory("sqlite+pysqlite:///:memory:")
    worker = FakeWorkerClient()
    reviewer = FakeReviewerClient(
        [
            {
                "verdict": "approve",
                "blocking_issues": [],
                "non_blocking_issues": ["minor naming"],
                "suggested_repairs": [],
                "confidence": 0.9,
            }
        ]
    )
    service = ExecutionService(worker_client=worker, reviewer_client=reviewer)

    with SessionFactory() as session:
        result = service.run_single_candidate(
            session=session,
            job_id="job-1",
            repo="repo",
            task_id="t1",
            base_branch="main",
            decision_state=make_decision(),
            selected_candidate=make_candidate(),
        )
        row = session.execute(text("SELECT transitions FROM execution_state WHERE job_id='job-1'")).fetchone()

    stages = [entry["stage"] for entry in row[0]]
    assert stages == ["queued", "prepared", "implementing", "validating", "reviewing", "finalizing", "completed"]
    assert result["status"] == "completed"


def test_execution_reviewer_block_triggers_exactly_one_repair_cycle():
    SessionFactory = create_session_factory("sqlite+pysqlite:///:memory:")
    worker = FakeWorkerClient()
    reviewer = FakeReviewerClient(
        [
            {
                "verdict": "block",
                "blocking_issues": ["test gap"],
                "non_blocking_issues": [],
                "suggested_repairs": ["add missing test"],
                "confidence": 0.8,
            },
            {
                "verdict": "block",
                "blocking_issues": ["still blocked"],
                "non_blocking_issues": [],
                "suggested_repairs": [],
                "confidence": 0.7,
            },
        ]
    )
    service = ExecutionService(worker_client=worker, reviewer_client=reviewer)

    with SessionFactory() as session:
        result = service.run_single_candidate(
            session=session,
            job_id="job-2",
            repo="repo",
            task_id="t2",
            base_branch="main",
            decision_state=make_decision(),
            selected_candidate=make_candidate(),
        )

    assert worker.run_command_calls == 1
    assert reviewer.calls == 2
    assert result["status"] == "blocked"


def test_execution_artifact_capture_shape():
    SessionFactory = create_session_factory("sqlite+pysqlite:///:memory:")
    worker = FakeWorkerClient()
    reviewer = FakeReviewerClient(
        [
            {
                "verdict": "approve",
                "blocking_issues": [],
                "non_blocking_issues": [],
                "suggested_repairs": [],
                "confidence": 0.95,
            }
        ]
    )
    service = ExecutionService(worker_client=worker, reviewer_client=reviewer)

    with SessionFactory() as session:
        result = service.run_single_candidate(
            session=session,
            job_id="job-3",
            repo="repo",
            task_id="t3",
            base_branch="main",
            decision_state=make_decision(),
            selected_candidate=make_candidate(),
        )

    artifacts = result["artifacts"]
    assert "changed_files" in artifacts
    assert "diff" in artifacts
    assert "lint_output" in artifacts
    assert "typecheck_output" in artifacts
    assert "test_output" in artifacts
    assert "reviewer_verdict" in artifacts
