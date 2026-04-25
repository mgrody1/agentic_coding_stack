"""Milestone 6 deterministic memory write gating and persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.conductor.services.feasibility import FeasibilityService
from apps.conductor.services.frontier import FrontierService
from apps.conductor.services.package_semantics import classify_package_status
from shared.schemas.models import CandidatePlan, DecisionState, ExecutionRunResponse


@dataclass
class MemoryWriteResult:
    chosen_written: bool
    frontier_written: int
    residual_written: bool
    surprise_reasons: list[str]


class MemoryWriterService:
    def __init__(self):
        self.frontier_service = FrontierService()
        self.feasibility_service = FeasibilityService()

    def write_package(
        self,
        session: Session,
        repo: str,
        decision_state: DecisionState,
        chosen_candidate: CandidatePlan,
        feasible_unchosen: list[CandidatePlan],
        execution_result: ExecutionRunResponse,
    ) -> MemoryWriteResult:
        semantics = classify_package_status(execution_result.status)
        chosen_written = False
        if semantics.canonical_memory_allowed:
            chosen_written = self._write_chosen(session, repo, decision_state, chosen_candidate, execution_result)
        frontier_count = self._write_frontier(session, repo, chosen_candidate, feasible_unchosen)
        surprise_reasons = self.detect_surprise(execution_result)
        residual_written = False
        if surprise_reasons:
            self._write_residual(session, repo, decision_state, chosen_candidate, execution_result, surprise_reasons)
            residual_written = True

        return MemoryWriteResult(
            chosen_written=chosen_written,
            frontier_written=frontier_count,
            residual_written=residual_written,
            surprise_reasons=surprise_reasons,
        )

    def _write_chosen(
        self,
        session: Session,
        repo: str,
        decision_state: DecisionState,
        chosen_candidate: CandidatePlan,
        execution_result: ExecutionRunResponse,
    ) -> bool:
        payload = {
            "decision_state": decision_state.model_dump(mode="json"),
            "chosen_candidate": chosen_candidate.model_dump(mode="json"),
            "execution_status": execution_result.status,
            "artifacts": {
                "changed_files": execution_result.artifacts.get("changed_files", []),
                "lint_output": execution_result.artifacts.get("lint_output", {}),
                "typecheck_output": execution_result.artifacts.get("typecheck_output", {}),
                "test_output": execution_result.artifacts.get("test_output", {}),
            },
            "reviewer_verdict": execution_result.reviewer_verdict.model_dump(mode="json"),
        }
        summary_text = f"Chosen plan: {chosen_candidate.title} | status={execution_result.status}"
        session.execute(
            text("INSERT INTO chosen_memory(repo, payload, summary_text) VALUES (:repo, :payload, :summary_text)"),
            {"repo": repo, "payload": json.dumps(payload), "summary_text": summary_text},
        )
        session.commit()
        return True

    def _write_frontier(
        self,
        session: Session,
        repo: str,
        chosen_candidate: CandidatePlan,
        feasible_unchosen: list[CandidatePlan],
    ) -> int:
        if not feasible_unchosen:
            return 0

        # Frontier memory stores only feasible, non-dominated, materially distinct alternatives.
        feasible_only = [cand for cand in feasible_unchosen if self.feasibility_service.certify(cand).feasible]
        non_dominated = self.frontier_service.pareto_filter(feasible_only)
        candidates = [
            cand
            for cand in non_dominated
            if not self.frontier_service._dominates(chosen_candidate, cand)
        ]
        candidates = self._filter_materially_distinct(chosen_candidate, candidates)
        candidates = candidates[:2]

        count = 0
        for alternative in candidates:
            delta = self._objective_delta(chosen_candidate, alternative)
            payload = {
                "chosen_candidate_title": chosen_candidate.title,
                "alternative_candidate": alternative.model_dump(mode="json"),
                "relation_type": "feasible_unchosen",
                "contrastive_delta": self._contrastive_delta(chosen_candidate, alternative),
                "objective_delta": delta,
            }
            session.execute(
                text("INSERT INTO frontier_memory(repo, payload, summary_text) VALUES (:repo, :payload, :summary_text)"),
                {
                    "repo": repo,
                    "payload": json.dumps(payload),
                    "summary_text": f"Alternative vs chosen: {alternative.title} vs {chosen_candidate.title}",
                },
            )
            count += 1

        session.commit()
        return count

    def _write_residual(
        self,
        session: Session,
        repo: str,
        decision_state: DecisionState,
        chosen_candidate: CandidatePlan,
        execution_result: ExecutionRunResponse,
        surprise_reasons: list[str],
    ) -> None:
        payload = {
            "decision_state_task_id": decision_state.task_id,
            "chosen_candidate_title": chosen_candidate.title,
            "execution_status": execution_result.status,
            "surprise_reasons": surprise_reasons,
            "reviewer_verdict": execution_result.reviewer_verdict.model_dump(mode="json"),
        }
        session.execute(
            text("INSERT INTO residual_memory(repo, payload, summary_text) VALUES (:repo, :payload, :summary_text)"),
            {
                "repo": repo,
                "payload": json.dumps(payload),
                "summary_text": f"Surprise detected for {decision_state.task_id}: {', '.join(surprise_reasons)}",
            },
        )
        session.commit()

    def detect_surprise(self, execution_result: ExecutionRunResponse) -> list[str]:
        reasons: list[str] = []
        reviewer = execution_result.reviewer_verdict
        if reviewer.blocking_issues:
            reasons.append("reviewer_caught_important_issue")

        validation_outputs = [
            execution_result.artifacts.get("lint_output", {}),
            execution_result.artifacts.get("typecheck_output", {}),
            execution_result.artifacts.get("test_output", {}),
        ]
        if any(isinstance(item, dict) and item.get("ok") is False for item in validation_outputs):
            reasons.append("validation_outcome_contradicts_expectation")

        if execution_result.status != "completed":
            reasons.append("final_status_differs_from_expected_success")

        return reasons

    def _filter_materially_distinct(self, chosen: CandidatePlan, alternatives: list[CandidatePlan]) -> list[CandidatePlan]:
        unique: list[CandidatePlan] = []
        for alternative in alternatives:
            if self.frontier_service.is_near_duplicate(chosen, alternative, similarity_threshold=0.985):
                continue
            duplicate = False
            for existing in unique:
                if self.frontier_service.is_near_duplicate(alternative, existing, similarity_threshold=0.985):
                    duplicate = True
                    break
            if not duplicate:
                unique.append(alternative)
        return unique

    @staticmethod
    def _objective_delta(chosen: CandidatePlan, alternative: CandidatePlan) -> dict[str, float]:
        c = chosen.objective_vec.model_dump()
        a = alternative.objective_vec.model_dump()
        return {key: round(a[key] - c[key], 6) for key in c}

    @staticmethod
    def _contrastive_delta(chosen: CandidatePlan, alternative: CandidatePlan) -> str:
        return f"Chosen '{chosen.title}' vs alternative '{alternative.title}' with objective deltas recorded."
