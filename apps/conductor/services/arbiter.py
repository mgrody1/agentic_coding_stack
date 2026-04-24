"""Milestone 4 arbiter contract on filtered frontier with synthesis recertification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from apps.conductor.services.feasibility import FeasibilityService
from shared.schemas.models import CandidatePlan, DecisionState


@dataclass
class ArbiterOutcome:
    status: str
    selected_candidate: CandidatePlan | None
    notes: list[str]


class ArbiterService:
    def __init__(self, omlx_client, feasibility_service: FeasibilityService):
        self.omlx_client = omlx_client
        self.feasibility_service = feasibility_service

    def decide(
        self,
        decision_state: DecisionState,
        frontier_candidates: list[CandidatePlan],
        rejected_candidates: list[dict[str, Any]],
    ) -> ArbiterOutcome:
        payload = {
            "decision_state": decision_state.model_dump(mode="json"),
            "frontier_candidates": [candidate.model_dump(mode="json") for candidate in frontier_candidates],
            "rejected_count": len(rejected_candidates),
            "instructions": "Choose one frontier candidate or propose synthesis. Do not reference rejected candidates.",
        }
        messages = [
            {"role": "system", "content": "Arbitrate only over the provided filtered frontier."},
            {"role": "user", "content": payload},
        ]

        response = self.omlx_client.chat(alias="arbiter", messages=messages, temperature=0.0)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", {})
        if not isinstance(content, dict):
            return ArbiterOutcome(status="rejected", selected_candidate=None, notes=["arbiter_response_invalid"])

        decision_type = content.get("decision_type", "reject")
        if decision_type == "choose":
            index = int(content.get("selected_index", -1))
            if index < 0 or index >= len(frontier_candidates):
                return ArbiterOutcome(status="rejected", selected_candidate=None, notes=["arbiter_selected_index_invalid"])
            return ArbiterOutcome(status="chosen", selected_candidate=frontier_candidates[index], notes=["arbiter_selected_frontier_candidate"])

        if decision_type == "synthesis":
            synthesized_payload = content.get("synthesized_candidate", {})
            try:
                synthesized = CandidatePlan.model_validate(synthesized_payload)
            except ValidationError as exc:
                return ArbiterOutcome(
                    status="rejected",
                    selected_candidate=None,
                    notes=["synthesis_schema_invalid", str(exc)],
                )

            recert = self.feasibility_service.certify(synthesized)
            if not recert.feasible:
                return ArbiterOutcome(
                    status="rejected",
                    selected_candidate=None,
                    notes=["synthesis_recertification_failed", *recert.certificate.notes],
                )
            return ArbiterOutcome(status="chosen", selected_candidate=synthesized, notes=["synthesis_recertified"])

        return ArbiterOutcome(status="rejected", selected_candidate=None, notes=["arbiter_rejected_all"])
