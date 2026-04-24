from apps.conductor.services.frontier import FrontierService
from shared.schemas.models import CandidatePlan, MicroTargets, ObjectiveVector


def make_candidate(name: str, objective: dict[str, float], macro=None, meso=None, files=None):
    return CandidatePlan(
        title=name,
        summary=name,
        role="minimal_patch",
        macro_vec=macro if macro is not None else [-1, -1, 1, -1, 1, -1],
        meso_tags=meso if meso is not None else ["api"],
        micro_targets=MicroTargets(files=files if files is not None else [f"src/{name}.py"], tests=[f"tests/{name}.py"]),
        objective_vec=ObjectiveVector(**objective),
        rollback_plan="revert commit",
        test_plan=[f"tests/{name}.py"],
    )


def test_pareto_dominance_filtering():
    service = FrontierService()
    dominant = make_candidate("dominant", {"correctness_confidence": 0.9, "reversibility": 0.9, "locality": 0.9, "maintainability": 0.9, "delivery_speed": 0.9})
    dominated = make_candidate("dominated", {"correctness_confidence": 0.8, "reversibility": 0.7, "locality": 0.7, "maintainability": 0.8, "delivery_speed": 0.8})
    non_dominated = make_candidate("other", {"correctness_confidence": 0.7, "reversibility": 0.95, "locality": 0.7, "maintainability": 0.95, "delivery_speed": 0.7})

    result = service.pareto_filter([dominant, dominated, non_dominated])

    assert dominant in result
    assert non_dominated in result
    assert dominated not in result


def test_near_duplicate_candidate_deduplication():
    service = FrontierService()
    a = make_candidate("a", {"correctness_confidence": 0.8, "reversibility": 0.9, "locality": 0.8, "maintainability": 0.7, "delivery_speed": 0.8})
    b = make_candidate("b", {"correctness_confidence": 0.8, "reversibility": 0.9, "locality": 0.8, "maintainability": 0.7, "delivery_speed": 0.8}, files=["src/a.py"])
    c = make_candidate("c", {"correctness_confidence": 0.6, "reversibility": 0.5, "locality": 0.6, "maintainability": 0.6, "delivery_speed": 0.5})

    deduped = service.dedupe([a, b, c], similarity_threshold=0.98)

    assert len(deduped) == 2


def test_medoid_count_is_capped_to_three():
    service = FrontierService()
    candidates = [
        make_candidate(
            f"c{i}",
            {
                "correctness_confidence": 0.5 + i * 0.05,
                "reversibility": 0.6,
                "locality": 0.7,
                "maintainability": 0.6,
                "delivery_speed": 0.5,
            },
            files=[f"src/c{i}.py"],
        )
        for i in range(7)
    ]

    medoids = service.select_medoids(candidates, max_k=3)

    assert len(medoids) <= 3
