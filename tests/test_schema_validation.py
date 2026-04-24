import pytest
from pydantic import ValidationError

from shared.schemas.models import CandidatePlan, MicroTargets, ObjectiveVector


def test_candidate_plan_validates_macro_vec_range():
    with pytest.raises(ValidationError):
        CandidatePlan(
            title="t",
            summary="s",
            role="minimal_patch",
            macro_vec=[-1, 0, 1, 2, 0, 1],
            meso_tags=["api"],
            micro_targets=MicroTargets(),
            objective_vec=ObjectiveVector(
                correctness_confidence=0.8,
                reversibility=0.7,
                locality=0.9,
                maintainability=0.6,
                delivery_speed=0.8,
            ),
            rollback_plan="revert",
        )
