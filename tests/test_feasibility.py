from apps.conductor.services.feasibility import FeasibilityService
from shared.schemas.models import CandidatePlan, MicroTargets, ObjectiveVector


def build_candidate(test_plan=None, files=None, meso_tags=None):
    return CandidatePlan(
        title="candidate",
        summary="summary",
        role="minimal_patch",
        macro_vec=[-1, -1, 1, -1, 1, -1],
        meso_tags=meso_tags if meso_tags is not None else ["api"],
        micro_targets=MicroTargets(files=files if files is not None else ["src/a.py"]),
        objective_vec=ObjectiveVector(
            correctness_confidence=0.8,
            reversibility=0.9,
            locality=0.95,
            maintainability=0.7,
            delivery_speed=0.9,
        ),
        rollback_plan="revert commit",
        test_plan=test_plan if test_plan is not None else ["tests/test_a.py"],
    )


def test_feasibility_gate_separates_infeasible_candidates_with_reasons():
    service = FeasibilityService()
    feasible_candidate = build_candidate()
    infeasible_candidate = build_candidate(test_plan=[])

    feasible, infeasible = service.gate([feasible_candidate, infeasible_candidate])

    assert len(feasible) == 1
    assert len(infeasible) == 1
    assert infeasible[0].certificate.test_plan_valid is False
    assert any("test_plan_fail" in note for note in infeasible[0].certificate.notes)
