from apps.conductor.services.candidate_generation import BUILDER_ROLES, CandidateGenerationService
from shared.schemas.models import DecisionState


class StubOMLXClient:
    def chat(self, alias, messages, **kwargs):
        role_line = [line for line in messages[1]["content"].split("\n") if line.startswith("role=")][0]
        role = role_line.split("=", 1)[1]
        payload = {
            "title": f"plan for {role}",
            "summary": "safe local patch",
            "role": role,
            "macro_vec": [-1, -1, 1, -1, 1, -1],
            "meso_tags": ["api"],
            "micro_targets": {
                "files": ["src/a.py"],
                "tests": ["tests/test_a.py"],
                "migration": False,
                "config": False,
                "endpoint": True,
                "env_var": False,
            },
            "objective_vec": {
                "correctness_confidence": 0.8,
                "reversibility": 0.9,
                "locality": 0.9,
                "maintainability": 0.7,
                "delivery_speed": 0.85,
            },
            "rollback_plan": "revert commit",
            "test_plan": ["tests/test_a.py"],
            "implementation_outline": ["edit", "test"],
            "risk_notes": ["small risk"],
        }
        return {"choices": [{"message": {"content": payload}}]}


class JsonStringOMLXClient(StubOMLXClient):
    def chat(self, alias, messages, **kwargs):
        response = super().chat(alias, messages, **kwargs)
        response["choices"][0]["message"]["content"] = (
            "```json\n" + __import__("json").dumps(response["choices"][0]["message"]["content"]) + "\n```"
        )
        return response


def test_candidate_generation_returns_fixed_six_roles():
    service = CandidateGenerationService(omlx_client=StubOMLXClient())
    decision = DecisionState(repo="repo", task_id="1", issue_summary="sum")

    result = service.generate(decision)

    assert len(result.valid_candidates) == 6
    assert len(result.rejected_candidates) == 0
    assert {cand.role for cand in result.valid_candidates} == set(BUILDER_ROLES)


def test_candidate_generation_parses_fenced_json_string():
    service = CandidateGenerationService(omlx_client=JsonStringOMLXClient())
    decision = DecisionState(repo="repo", task_id="1", issue_summary="sum")

    result = service.generate(decision)

    assert len(result.valid_candidates) == 6
    assert len(result.rejected_candidates) == 0
