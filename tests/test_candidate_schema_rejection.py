from apps.conductor.services.candidate_generation import CandidateGenerationService
from shared.schemas.models import DecisionState


class InvalidCandidateOMLXClient:
    def chat(self, alias, messages, **kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": {
                            "title": "bad",
                            "summary": "missing required fields",
                            "macro_vec": [0, 0, 0],
                        }
                    }
                }
            ]
        }


def test_candidate_schema_rejection_path():
    service = CandidateGenerationService(omlx_client=InvalidCandidateOMLXClient())
    decision = DecisionState(repo="repo", task_id="1", issue_summary="sum")

    result = service.generate(decision)

    assert len(result.valid_candidates) == 0
    assert len(result.rejected_candidates) == 6
    assert all(item["reason"] == "schema_validation_failed" for item in result.rejected_candidates)
