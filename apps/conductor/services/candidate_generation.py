"""Milestone 3 candidate generation using fixed builder roles."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from shared.schemas.models import CandidatePlan, DecisionState


BUILDER_ROLES: tuple[str, ...] = (
    "minimal_patch",
    "test_first",
    "rollback_first",
    "refactor_first",
    "architecture_clean",
    "perf_aware",
)


@dataclass
class CandidateGenerationResult:
    valid_candidates: list[CandidatePlan]
    rejected_candidates: list[dict]


class CandidateGenerationService:
    def __init__(self, omlx_client):
        self.omlx_client = omlx_client

    def generate(self, decision_state: DecisionState) -> CandidateGenerationResult:
        valid: list[CandidatePlan] = []
        rejected: list[dict] = []

        for role in BUILDER_ROLES:
            messages = self._build_messages(decision_state=decision_state, role=role)
            response = self.omlx_client.chat(alias="builder", messages=messages, temperature=0.2)
            payload = self._extract_candidate_payload(response=response, role=role)
            try:
                candidate = CandidatePlan.model_validate(payload)
                valid.append(candidate)
            except ValidationError as exc:
                rejected.append(
                    {
                        "role": role,
                        "reason": "schema_validation_failed",
                        "errors": exc.errors(),
                        "raw_payload": payload,
                    }
                )

        return CandidateGenerationResult(valid_candidates=valid, rejected_candidates=rejected)

    def _build_messages(self, decision_state: DecisionState, role: str) -> list[dict[str, str]]:
        prompt = (
            "Generate exactly one CandidatePlan JSON object for the assigned fixed role. "
            "Do not use weighted scalar frontier scoring; keep objective_vec as 5 separate values. "
            "Workers execute code only; do not delegate policy decisions to workers."
        )
        user = (
            f"role={role}\n"
            f"repo={decision_state.repo}\n"
            f"task_id={decision_state.task_id}\n"
            f"issue_summary={decision_state.issue_summary}\n"
            f"macro_constraints={decision_state.macro_constraints}\n"
            f"meso_context={decision_state.meso_context}\n"
            f"micro_context={decision_state.micro_context}"
        )
        return [{"role": "system", "content": prompt}, {"role": "user", "content": user}]

    @staticmethod
    def _extract_candidate_payload(response: dict, role: str) -> dict:
        # Supports OpenAI-compatible chat payload shape.
        content = response.get("choices", [{}])[0].get("message", {}).get("content")
        if isinstance(content, dict):
            payload = content
        else:
            payload = {}
        payload.setdefault("role", role)
        return payload
