"""Milestone 5 execution/review loop with one repair cycle."""

from __future__ import annotations

import json
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

CAUSE_EXEC_SUCCESS = "EXEC_SUCCESS"
CAUSE_EXEC_REVIEW_BLOCKED = "EXEC_REVIEW_BLOCKED"
CAUSE_EXEC_REPAIR_FAILED = "EXEC_REPAIR_FAILED"
CAUSE_EXEC_REVIEW_PARSE_FAILED = "EXEC_REVIEW_PARSE_FAILED"


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
            artifacts["diagnostics"] = {"cause_code": CAUSE_EXEC_REVIEW_PARSE_FAILED}
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
                "cause_code": CAUSE_EXEC_REVIEW_PARSE_FAILED,
            }
        artifacts["reviewer_verdict"] = reviewer_verdict.model_dump(mode="json")
        self._save_state(session, job_id, repo, task_id, "reviewing", "running", selected_candidate, artifacts, "review_completed")

        repair_result: dict[str, Any] = {"attempted": False}
        if reviewer_verdict.verdict == "block":
            self._save_state(session, job_id, repo, task_id, "repairing", "running", selected_candidate, artifacts, "repair_started")
            repair_result = self._attempt_single_repair(
                repo=repo,
                task_id=task_id,
                decision_state=decision_state,
                selected_candidate=selected_candidate,
                reviewer_verdict=reviewer_verdict,
                artifacts=artifacts,
            )
            artifacts["repair_result"] = repair_result
            if repair_result.get("state") != "repair_failed":
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
                    repair_result["state"] = "repaired_and_passed" if second_verdict.verdict == "approve" else "repaired_but_still_blocked"
                except Exception as exc:
                    artifacts["review_error_after_repair"] = str(exc)
                    reviewer_verdict = ReviewerVerdict(
                        verdict="block",
                        blocking_issues=["review_parse_failed_after_repair"],
                        non_blocking_issues=[],
                        suggested_repairs=[],
                        confidence=0.0,
                    )
                    repair_result["state"] = "repaired_but_still_blocked"

        self._save_state(session, job_id, repo, task_id, "finalizing", "running", selected_candidate, artifacts, "finalizing")

        if repair_result.get("state") == "repair_failed":
            final_stage, final_status = "failed", "failed"
            cause_code = CAUSE_EXEC_REPAIR_FAILED
        elif reviewer_verdict.verdict == "approve":
            final_stage, final_status = "completed", "completed"
            cause_code = CAUSE_EXEC_SUCCESS
        elif reviewer_verdict.verdict in {"block", "revise"}:
            final_stage, final_status = "blocked", "blocked"
            cause_code = CAUSE_EXEC_REVIEW_BLOCKED
        else:
            final_stage, final_status = "failed", "failed"
            cause_code = "EXEC_UNKNOWN_FAILURE"

        artifacts["diagnostics"] = {
            "cause_code": cause_code,
            "repair_state": repair_result.get("state"),
            "review_verdict": reviewer_verdict.verdict,
        }

        self._save_state(session, job_id, repo, task_id, final_stage, final_status, selected_candidate, artifacts, "execution_finished")

        return {
            "job_id": job_id,
            "stage": final_stage,
            "status": final_status,
            "artifacts": artifacts,
            "reviewer_verdict": reviewer_verdict.model_dump(mode="json"),
            "repair_result": repair_result,
            "cause_code": cause_code,
        }

    def _attempt_single_repair(
        self,
        repo: str,
        task_id: str,
        decision_state: DecisionState,
        selected_candidate: CandidatePlan,
        reviewer_verdict: ReviewerVerdict,
        artifacts: dict[str, Any],
    ) -> dict[str, Any]:
        """Conductor-owned, bounded one-shot repair attempt.

        Exactly one modification cycle is allowed. Worker remains policy-free and
        only applies explicit file writes plus validation commands.
        """
        repair_context = {
            "decision_state_summary": decision_state.issue_summary,
            "selected_candidate": selected_candidate.model_dump(mode="json"),
            "blocking_issues": reviewer_verdict.blocking_issues,
            "current_diff": artifacts.get("diff", ""),
            "changed_files": artifacts.get("changed_files", []),
            "lint_output": artifacts.get("lint_output", {}),
            "typecheck_output": artifacts.get("typecheck_output", {}),
            "test_output": artifacts.get("test_output", {}),
            "active_overlays": artifacts.get("active_overlays", []),
        }

        try:
            plan = self._generate_repair_plan(repair_context)
        except Exception as exc:
            self.worker_client.reset_repo(repo=repo, task_id=task_id)
            return {"attempted": True, "state": "repair_failed", "reason": "repair_plan_parse_failed", "error": str(exc)}

        allowed_paths = set(selected_candidate.micro_targets.files + selected_candidate.micro_targets.tests + artifacts.get("changed_files", []))
        invalid_paths = [item.get("path", "") for item in plan if item.get("path", "") not in allowed_paths]
        if invalid_paths:
            self.worker_client.reset_repo(repo=repo, task_id=task_id)
            return {
                "attempted": True,
                "state": "repair_failed",
                "reason": "repair_path_out_of_bounds",
                "invalid_paths": invalid_paths,
                "allowed_paths": sorted(allowed_paths),
            }

        writes: list[dict[str, Any]] = []
        try:
            for item in plan:
                path = item["path"]
                content = item["content"]
                read_before = self.worker_client.read_file(repo=repo, task_id=task_id, path=path)
                write_result = self.worker_client.write_file(repo=repo, task_id=task_id, path=path, content=content)
                writes.append({"path": path, "before_len": len(read_before.get("content", "")), "bytes_written": write_result.get("bytes_written", 0)})
        except Exception as exc:
            self.worker_client.reset_repo(repo=repo, task_id=task_id)
            return {"attempted": True, "state": "repair_failed", "reason": "repair_write_failed", "error": str(exc)}

        diff_payload = self.worker_client.git_diff(repo=repo, task_id=task_id)
        if not diff_payload.get("changed_files"):
            self.worker_client.reset_repo(repo=repo, task_id=task_id)
            return {"attempted": True, "state": "repair_failed", "reason": "repair_produced_no_diff", "writes": writes}

        return {
            "attempted": True,
            "state": "repaired_but_still_blocked",
            "writes": writes,
            "repair_plan": [{"path": item["path"], "rationale": item.get("rationale", "")} for item in plan],
            "repair_diff": diff_payload.get("diff", ""),
            "repair_changed_files": diff_payload.get("changed_files", []),
        }

    def _generate_repair_plan(self, repair_context: dict[str, Any]) -> list[dict[str, str]]:
        response = self.reviewer_client.chat(
            alias="builder",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return strict JSON with key 'modifications'. "
                        "Each item: {'path': str, 'content': str, 'rationale': str}. "
                        "Only modify files that already appear in changed_files or candidate micro targets."
                    ),
                },
                {"role": "user", "content": repair_context},
            ],
            temperature=0.0,
        )
        content = response.get("choices", [{}])[0].get("message", {}).get("content", {})
        parsed = parse_model_json_content(content)
        modifications = parsed.get("modifications", []) if isinstance(parsed, dict) else []
        if not isinstance(modifications, list) or not modifications:
            raise ValueError("repair plan missing modifications")
        validated: list[dict[str, str]] = []
        for item in modifications:
            if not isinstance(item, dict):
                raise ValueError("repair modification must be object")
            path = str(item.get("path", "")).strip()
            content_text = str(item.get("content", ""))
            rationale = str(item.get("rationale", "")).strip()
            if not path:
                raise ValueError("repair modification missing path")
            validated.append({"path": path, "content": content_text, "rationale": rationale})
        return validated

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
        if row and isinstance(row[0], str):
            try:
                transitions = json.loads(row[0])
            except json.JSONDecodeError:
                transitions = []
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
                "selected_candidate": json.dumps(selected_candidate.model_dump(mode="json")),
                "artifacts": json.dumps(artifacts),
                "transitions": json.dumps(transitions),
                "updated_at": now,
            },
        )
        session.commit()
