from sqlalchemy import text

from apps.conductor.db.models import create_session_factory
from apps.conductor.services.execution import ExecutionService
from shared.schemas.models import CandidatePlan, DecisionState, MicroTargets, ObjectiveVector


class RepairWorkerClient:
    def __init__(self, no_diff_after_write: bool = False):
        self.files = {"src/a.py": "old", "tests/a_test.py": "old-test"}
        self.reset_calls = 0
        self.lint_calls = 0
        self.typecheck_calls = 0
        self.test_calls = 0
        self.no_diff_after_write = no_diff_after_write

    def prepare_repo(self, repo, task_id, base_branch):
        return {"worktree_path": f"/tmp/{task_id}", "branch_name": f"task/{task_id}"}

    def run_lint(self, repo, task_id):
        self.lint_calls += 1
        return {"ok": True}

    def run_typecheck(self, repo, task_id):
        self.typecheck_calls += 1
        return {"ok": True}

    def run_tests(self, repo, task_id, tests):
        self.test_calls += 1
        return {"ok": True, "tests": tests}

    def git_diff(self, repo, task_id):
        if self.no_diff_after_write:
            return {"diff": "", "changed_files": []}
        changed = [path for path, content in self.files.items() if content.startswith("new")]
        return {"diff": "diff --git a b" if changed else "", "changed_files": changed}

    def read_file(self, repo, task_id, path):
        return {"content": self.files.get(path, ""), "path": path}

    def write_file(self, repo, task_id, path, content):
        self.files[path] = content
        return {"ok": True, "path": path, "bytes_written": len(content)}

    def reset_repo(self, repo, task_id):
        self.reset_calls += 1
        return {"ok": True}

    def run_command(self, repo, task_id, command_key, args):
        return {"ok": True}


class RepairReviewerClient:
    def __init__(self, review_sequence, modifications):
        self.review_sequence = list(review_sequence)
        self.modifications = modifications
        self.review_calls = 0
        self.repair_calls = 0

    def chat(self, alias, messages, **kwargs):
        if alias == "builder":
            self.repair_calls += 1
            return {"choices": [{"message": {"content": {"modifications": self.modifications}}}]}
        item = self.review_sequence[min(self.review_calls, len(self.review_sequence) - 1)]
        self.review_calls += 1
        return {"choices": [{"message": {"content": item}}]}


def _candidate():
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
            maintainability=0.8,
            delivery_speed=0.8,
        ),
        rollback_plan="rollback",
        test_plan=["tests/a_test.py"],
    )


def _decision():
    return DecisionState(repo="repo", task_id="t1", issue_summary="issue")


def test_real_single_repair_attempt_applies_modification_and_reruns_validation():
    SessionFactory = create_session_factory("sqlite+pysqlite:///:memory:")
    worker = RepairWorkerClient()
    reviewer = RepairReviewerClient(
        review_sequence=[
            {"verdict": "block", "blocking_issues": ["bug"], "non_blocking_issues": [], "suggested_repairs": [], "confidence": 0.7},
            {"verdict": "approve", "blocking_issues": [], "non_blocking_issues": [], "suggested_repairs": [], "confidence": 0.9},
        ],
        modifications=[{"path": "src/a.py", "content": "new content", "rationale": "fix"}],
    )
    service = ExecutionService(worker_client=worker, reviewer_client=reviewer)
    with SessionFactory() as session:
        result = service.run_single_candidate(
            session=session,
            job_id="job-1",
            repo="repo",
            task_id="t1",
            base_branch="main",
            decision_state=_decision(),
            selected_candidate=_candidate(),
        )

    assert reviewer.repair_calls == 1
    assert result["repair_result"]["state"] == "repaired_and_passed"
    assert result["repair_result"]["repair_changed_files"] == ["src/a.py"]
    assert worker.lint_calls >= 2
    assert worker.typecheck_calls >= 2
    assert worker.test_calls >= 2
    assert result["status"] == "completed"


def test_repair_rejects_out_of_bounds_file_and_fails_cleanly():
    SessionFactory = create_session_factory("sqlite+pysqlite:///:memory:")
    worker = RepairWorkerClient()
    reviewer = RepairReviewerClient(
        review_sequence=[{"verdict": "block", "blocking_issues": ["bug"], "non_blocking_issues": [], "suggested_repairs": [], "confidence": 0.7}],
        modifications=[{"path": "src/not-allowed.py", "content": "new content", "rationale": "fix"}],
    )
    service = ExecutionService(worker_client=worker, reviewer_client=reviewer)
    with SessionFactory() as session:
        result = service.run_single_candidate(
            session=session,
            job_id="job-2",
            repo="repo",
            task_id="t2",
            base_branch="main",
            decision_state=_decision(),
            selected_candidate=_candidate(),
        )
        row = session.execute(text("SELECT stage, status FROM execution_state WHERE job_id='job-2'")).fetchone()

    assert result["repair_result"]["state"] == "repair_failed"
    assert result["status"] == "failed"
    assert worker.reset_calls == 1
    assert row[0] == "failed"
    assert row[1] == "failed"


def test_repair_requires_diff_artifact():
    SessionFactory = create_session_factory("sqlite+pysqlite:///:memory:")
    worker = RepairWorkerClient(no_diff_after_write=True)
    reviewer = RepairReviewerClient(
        review_sequence=[{"verdict": "block", "blocking_issues": ["bug"], "non_blocking_issues": [], "suggested_repairs": [], "confidence": 0.7}],
        modifications=[{"path": "src/a.py", "content": "new content", "rationale": "fix"}],
    )
    service = ExecutionService(worker_client=worker, reviewer_client=reviewer)
    with SessionFactory() as session:
        result = service.run_single_candidate(
            session=session,
            job_id="job-3",
            repo="repo",
            task_id="t3",
            base_branch="main",
            decision_state=_decision(),
            selected_candidate=_candidate(),
        )

    assert result["repair_result"]["state"] == "repair_failed"
    assert result["repair_result"]["reason"] == "repair_produced_no_diff"
    assert result["status"] == "failed"
