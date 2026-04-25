"""Milestone 3 candidate generation using fixed builder roles."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from apps.conductor.services.overlay_state import OverlayResolution
from shared.schemas.models import CandidatePlan, DecisionState
from shared.utils.parsing import parse_model_json_content


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

    def generate(
        self,
        decision_state: DecisionState,
        overlay_resolution: OverlayResolution | None = None,
    ) -> CandidateGenerationResult:
        valid: list[CandidatePlan] = []
        rejected: list[dict] = []

        for role in BUILDER_ROLES:
            messages = self._build_messages(
                decision_state=decision_state,
                role=role,
                overlay_resolution=overlay_resolution,
            )
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

    def _build_messages(
        self,
        decision_state: DecisionState,
        role: str,
        overlay_resolution: OverlayResolution | None = None,
    ) -> list[dict[str, str]]:
        prompt = (
            "Generate exactly one CandidatePlan JSON object for the assigned fixed role. "
            "Do not use weighted scalar frontier scoring; keep objective_vec as 5 separate values. "
            "Workers execute code only; do not delegate policy decisions to workers."
        )
        overlay_lines: list[str] = []
        if overlay_resolution:
            # Overlays are advisory only and never override hard/global constraints.
            overlay_lines = [
                f"active_overlays={overlay_resolution.active_overlays}",
                *overlay_resolution.as_prompt_lines(),
            ]
        user = (
            f"role={role}\n"
            f"repo={decision_state.repo}\n"
            f"task_id={decision_state.task_id}\n"
            f"issue_summary={decision_state.issue_summary}\n"
            f"macro_constraints={decision_state.macro_constraints}\n"
            f"meso_context={decision_state.meso_context}\n"
            f"micro_context={decision_state.micro_context}\n"
            f"{chr(10).join(overlay_lines)}"
        )
        return [{"role": "system", "content": prompt}, {"role": "user", "content": user}]

    @staticmethod
    def _extract_candidate_payload(response: dict, role: str) -> dict:
        # Supports OpenAI-compatible chat payload shape.
        content = response.get("choices", [{}])[0].get("message", {}).get("content")
        payload = parse_model_json_content(content)
        payload.setdefault("role", role)
        return payload
