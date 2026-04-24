"""Milestone 5 execution/review loop with one repair cycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.schemas.models import CandidatePlan, DecisionState, ReviewerVerdict
from shared.utils.parsing import parse_model_json_content


STAGE_ORDER = (
    "queued",
    "prepared",
    "implementing",
    "validating",
    "reviewing",
    "repairing",
    "finalizing",
    "completed",
    "blocked",
    "failed",
)


@dataclass
class ExecutionArtifacts:
    changed_files: list[str]
    diff: str
    lint_output: dict[str, Any]
    typecheck_output: dict[str, Any]
    test_output: dict[str, Any]
    reviewer_verdict: dict[str, Any]
    repair_result: dict[str, Any]


class ExecutionService:
    def __init__(self, worker_client, reviewer_client):
        self.worker_client = worker_client
        self.reviewer_client = reviewer_client

    def run_single_candidate(
        self,
        session: Session,
        job_id: str,
        repo: str,
        task_id: str,
        base_branch: str,
        decision_state: DecisionState,
        selected_candidate: CandidatePlan,
    ) -> dict[str, Any]:
        self._save_state(session, job_id, repo, task_id, "queued", "running", selected_candidate, {}, "job_queued")

        prepare = self.worker_client.prepare_repo(repo=repo, task_id=task_id, base_branch=base_branch)
        self._save_state(session, job_id, repo, task_id, "prepared", "running", selected_candidate, {"prepare": prepare}, "worktree_prepared")

        self._save_state(session, job_id, repo, task_id, "implementing", "running", selected_candidate, {}, "implementation_started")

        lint_output = self.worker_client.run_lint(repo=repo, task_id=task_id)
        typecheck_output = self.worker_client.run_typecheck(repo=repo, task_id=task_id)
        test_output = self.worker_client.run_tests(repo=repo, task_id=task_id, tests=selected_candidate.test_plan)
        diff_payload = self.worker_client.git_diff(repo=repo, task_id=task_id)

        changed_files = diff_payload.get("changed_files", [])
        diff_text = diff_payload.get("diff", "")

        artifacts = {
            "changed_files": changed_files,
            "diff": diff_text,
            "lint_output": lint_output,
            "typecheck_output": typecheck_output,
            "test_output": test_output,
        }
        self._save_state(session, job_id, repo, task_id, "validating", "running", selected_candidate, artifacts, "validation_completed")

        try:
            reviewer_verdict = self._review(decision_state, selected_candidate, artifacts)
        except Exception as exc:
            artifacts["review_error"] = str(exc)
            self._save_state(session, job_id, repo, task_id, "failed", "failed", selected_candidate, artifacts, "review_parse_failed")
            return {
                "job_id": job_id,
                "stage": "failed",
                "status": "failed",
                "artifacts": artifacts,
                "reviewer_verdict": {
                    "verdict": "block",
                    "blocking_issues": ["review_parse_failed"],
                    "non_blocking_issues": [],
                    "suggested_repairs": [],
                    "confidence": 0.0,
                },
                "repair_result": {"attempted": False},
            }
        artifacts["reviewer_verdict"] = reviewer_verdict.model_dump(mode="json")
        self._save_state(session, job_id, repo, task_id, "reviewing", "running", selected_candidate, artifacts, "review_completed")

        repair_result: dict[str, Any] = {"attempted": False}
        if reviewer_verdict.verdict == "block":
            self._save_state(session, job_id, repo, task_id, "repairing", "running", selected_candidate, artifacts, "repair_started")
            repair_result = self.worker_client.run_command(
                repo=repo,
                task_id=task_id,
                command_key="test",
                args=["--repair", "1"],
            )
            artifacts["repair_result"] = repair_result
            lint_output = self.worker_client.run_lint(repo=repo, task_id=task_id)
            typecheck_output = self.worker_client.run_typecheck(repo=repo, task_id=task_id)
            test_output = self.worker_client.run_tests(repo=repo, task_id=task_id, tests=selected_candidate.test_plan)
            diff_payload = self.worker_client.git_diff(repo=repo, task_id=task_id)
            artifacts.update(
                {
                    "lint_output": lint_output,
                    "typecheck_output": typecheck_output,
                    "test_output": test_output,
                    "changed_files": diff_payload.get("changed_files", []),
                    "diff": diff_payload.get("diff", ""),
                }
            )
            try:
                second_verdict = self._review(decision_state, selected_candidate, artifacts)
                artifacts["reviewer_verdict_after_repair"] = second_verdict.model_dump(mode="json")
                reviewer_verdict = second_verdict
            except Exception as exc:
                artifacts["review_error_after_repair"] = str(exc)
                reviewer_verdict = ReviewerVerdict(
                    verdict="block",
                    blocking_issues=["review_parse_failed_after_repair"],
                    non_blocking_issues=[],
                    suggested_repairs=[],
                    confidence=0.0,
                )

        self._save_state(session, job_id, repo, task_id, "finalizing", "running", selected_candidate, artifacts, "finalizing")

        if reviewer_verdict.verdict == "approve":
            final_stage, final_status = "completed", "completed"
        elif reviewer_verdict.verdict in {"block", "revise"}:
            final_stage, final_status = "blocked", "blocked"
        else:
            final_stage, final_status = "failed", "failed"

        self._save_state(session, job_id, repo, task_id, final_stage, final_status, selected_candidate, artifacts, "execution_finished")

        return {
            "job_id": job_id,
            "stage": final_stage,
            "status": final_status,
            "artifacts": artifacts,
            "reviewer_verdict": reviewer_verdict.model_dump(mode="json"),
            "repair_result": repair_result,
        }

    def _review(self, decision_state: DecisionState, selected_candidate: CandidatePlan, artifacts: dict[str, Any]) -> ReviewerVerdict:
        reviewer_payload = {
            "decision_state_summary": decision_state.issue_summary,
            "selected_candidate": selected_candidate.model_dump(mode="json"),
            "diff": artifacts.get("diff", ""),
            "changed_files": artifacts.get("changed_files", []),
            "lint_output": artifacts.get("lint_output", {}),
            "typecheck_output": artifacts.get("typecheck_output", {}),
            "test_output": artifacts.get("test_output", {}),
        }
        response = self.reviewer_client.chat(
            alias="reviewer",
            messages=[
                {"role": "system", "content": "Return strict JSON for reviewer verdict."},
                {"role": "user", "content": reviewer_payload},
            ],
            temperature=0.0,
        )
        content = response.get("choices", [{}])[0].get("message", {}).get("content", {})
        parsed = parse_model_json_content(content)
        return ReviewerVerdict.model_validate(parsed)

    @staticmethod
    def _save_state(
        session: Session,
        job_id: str,
        repo: str,
        task_id: str,
        stage: str,
        status: str,
        selected_candidate: CandidatePlan,
        artifacts: dict[str, Any],
        note: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        row = session.execute(
            text("SELECT transitions FROM execution_state WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        transitions = list(row[0]) if row and row[0] else []
        transitions.append({"stage": stage, "status": status, "at": now, "note": note})

        session.execute(
            text(
                """
                INSERT INTO execution_state(job_id, repo, task_id, stage, status, selected_candidate, artifacts, transitions, updated_at)
                VALUES (:job_id, :repo, :task_id, :stage, :status, :selected_candidate, :artifacts, :transitions, :updated_at)
                ON CONFLICT(job_id) DO UPDATE SET
                    stage = excluded.stage,
                    status = excluded.status,
                    selected_candidate = excluded.selected_candidate,
                    artifacts = excluded.artifacts,
                    transitions = excluded.transitions,
                    updated_at = excluded.updated_at
                """
            ),
            {
                "job_id": job_id,
                "repo": repo,
                "task_id": task_id,
                "stage": stage,
                "status": status,
                "selected_candidate": selected_candidate.model_dump(mode="json"),
                "artifacts": artifacts,
                "transitions": transitions,
                "updated_at": now,
            },
        )
        session.commit()
