"""Milestone 6 draft PR payload writer (no PR API side effects)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.schemas.models import CandidatePlan, DecisionState, ExecutionRunResponse


@dataclass
class DraftPRPayload:
    title: str
    body: str
    metadata: dict[str, Any]


class PRWriterService:
    def build_draft_payload(
        self,
        repo: str,
        job_id: str,
        decision_state: DecisionState,
        chosen_candidate: CandidatePlan,
        alternatives: list[CandidatePlan],
        execution_result: ExecutionRunResponse,
    ) -> DraftPRPayload:
        reviewer = execution_result.reviewer_verdict
        reviewer_objections = reviewer.blocking_issues + reviewer.non_blocking_issues
        resolution = "resolved" if execution_result.status == "completed" else "unresolved"

        body = "\n".join(
            [
                "## Summary",
                decision_state.issue_summary,
                "",
                "## Chosen Strategy",
                chosen_candidate.summary,
                "",
                "## Alternatives Considered",
                *([f"- {alt.title}: {alt.summary}" for alt in alternatives] if alternatives else ["- None retained"]),
                "",
                "## Validation Evidence",
                f"- lint: {execution_result.artifacts.get('lint_output', {})}",
                f"- typecheck: {execution_result.artifacts.get('typecheck_output', {})}",
                f"- tests: {execution_result.artifacts.get('test_output', {})}",
                "",
                "## Reviewer Objections and Resolution",
                *([f"- {item}" for item in reviewer_objections] if reviewer_objections else ["- None"]),
                f"- resolution: {resolution}",
                "",
                "## Rollback Note",
                chosen_candidate.rollback_plan,
                "",
                "## Known Risks",
                *([f"- {risk}" for risk in chosen_candidate.risk_notes] if chosen_candidate.risk_notes else ["- None recorded"]),
            ]
        )

        title = f"[DRAFT] {repo} - {decision_state.task_id}: {chosen_candidate.title}"
        metadata = {
            "repo": repo,
            "job_id": job_id,
            "status": execution_result.status,
            "changed_files": execution_result.artifacts.get("changed_files", []),
        }
        return DraftPRPayload(title=title, body=body, metadata=metadata)
