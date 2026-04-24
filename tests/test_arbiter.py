from apps.conductor.services.arbiter import ArbiterService
from apps.conductor.services.feasibility import FeasibilityService
from shared.schemas.models import CandidatePlan, DecisionState, MicroTargets, ObjectiveVector


def build_candidate(name: str, test_plan=None):
    return CandidatePlan(
        title=name,
        summary=name,
        role="minimal_patch",
        macro_vec=[-1, -1, 1, -1, 1, -1],
        meso_tags=["api"],
        micro_targets=MicroTargets(files=[f"src/{name}.py"], tests=[f"tests/{name}.py"]),
        objective_vec=ObjectiveVector(
            correctness_confidence=0.8,
            reversibility=0.9,
            locality=0.9,
            maintainability=0.7,
            delivery_speed=0.8,
        ),
        rollback_plan="revert commit",
        test_plan=test_plan if test_plan is not None else [f"tests/{name}.py"],
    )


class CaptureArbiterClient:
    def __init__(self, response_content):
        self.response_content = response_content
        self.last_messages = None

    def chat(self, alias, messages, **kwargs):
        self.last_messages = messages
        return {"choices": [{"message": {"content": self.response_content}}]}


def test_arbiter_input_excludes_rejected_candidates():
    frontier = [build_candidate("frontier-1"), build_candidate("frontier-2")]
    rejected = [{"role": "refactor_first", "reason": "feasibility_failed"}]
    client = CaptureArbiterClient(response_content={"decision_type": "choose", "selected_index": 0})
    service = ArbiterService(client, FeasibilityService())

    outcome = service.decide(
        decision_state=DecisionState(repo="repo", task_id="1", issue_summary="sum"),
        frontier_candidates=frontier,
        rejected_candidates=rejected,
    )

    assert outcome.status == "chosen"
    user_payload = client.last_messages[1]["content"]
    assert len(user_payload["frontier_candidates"]) == 2
    assert "rejected_candidates" not in user_payload
    assert user_payload["rejected_count"] == 1


def test_arbiter_synthesis_must_be_revalidated_before_acceptance():
    bad_synthesis = build_candidate("synth", test_plan=[]).model_dump(mode="json")
    client = CaptureArbiterClient(response_content={"decision_type": "synthesis", "synthesized_candidate": bad_synthesis})
    service = ArbiterService(client, FeasibilityService())

    outcome = service.decide(
        decision_state=DecisionState(repo="repo", task_id="1", issue_summary="sum"),
        frontier_candidates=[build_candidate("frontier")],
        rejected_candidates=[],
    )

    assert outcome.status == "rejected"
    assert any("synthesis_recertification_failed" in note for note in outcome.notes)
