"""Decision state assembly for milestone 2."""

from __future__ import annotations

from shared.schemas.models import DecisionState, DecisionStateBuildRequest


class DecisionStateService:
    @staticmethod
    def build(request: DecisionStateBuildRequest) -> DecisionState:
        macro_constraints = [
            "No autonomous merge to main",
            "Worker executes only; conductor decides policy",
            "No weighted scalar frontier scoring in v1",
        ]
        meso_context = [f"Task type inferred from title: {request.title[:80]}"]
        micro_context = [*request.changed_files_hint]
        if not micro_context:
            micro_context.append("No changed_files_hint supplied")

        issue_summary = f"{request.title}\n\n{request.body}".strip()
        return DecisionState(
            repo=request.repo,
            task_id=request.task_id,
            issue_summary=issue_summary,
            macro_constraints=macro_constraints,
            meso_context=meso_context,
            micro_context=micro_context,
        )
