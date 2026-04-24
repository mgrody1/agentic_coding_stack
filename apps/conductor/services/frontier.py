"""Milestone 4 frontier pruning: Pareto, dedupe, Gram, medoid selection."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

from shared.schemas.models import CandidatePlan

MESO_TAXONOMY: tuple[str, ...] = (
    "auth",
    "billing",
    "api",
    "schema_data",
    "frontend",
    "ci_build",
    "infra",
    "security",
    "observability",
    "docs_devex",
    "shared_lib",
    "tooling",
)


@dataclass
class FrontierResult:
    pareto_candidates: list[CandidatePlan]
    deduped_candidates: list[CandidatePlan]
    gram_matrix: list[list[float]]
    medoid_candidates: list[CandidatePlan]


class FrontierService:
    def pareto_filter(self, candidates: list[CandidatePlan]) -> list[CandidatePlan]:
        non_dominated: list[CandidatePlan] = []
        for idx, cand in enumerate(candidates):
            dominated = False
            for jdx, other in enumerate(candidates):
                if idx == jdx:
                    continue
                if self._dominates(other, cand):
                    dominated = True
                    break
            if not dominated:
                non_dominated.append(cand)
        return non_dominated

    def dedupe(self, candidates: list[CandidatePlan], similarity_threshold: float = 0.985) -> list[CandidatePlan]:
        kept: list[CandidatePlan] = []
        for candidate in candidates:
            if not kept:
                kept.append(candidate)
                continue
            if any(self._cosine(self._feature_vector(candidate), self._feature_vector(existing)) >= similarity_threshold for existing in kept):
                continue
            kept.append(candidate)
        return kept

    def gram_matrix(self, candidates: list[CandidatePlan]) -> list[list[float]]:
        vectors = [self._feature_vector(candidate) for candidate in candidates]
        return [[self._cosine(a, b) for b in vectors] for a in vectors]

    def select_medoids(self, candidates: list[CandidatePlan], max_k: int = 3) -> list[CandidatePlan]:
        if not candidates:
            return []
        if len(candidates) <= max_k:
            return list(candidates)

        gram = self.gram_matrix(candidates)
        n = len(candidates)
        k = min(max_k, n)
        best_combo: tuple[int, ...] | None = None
        best_score = -math.inf

        for combo in itertools.combinations(range(n), k):
            score = 0.0
            for i in range(n):
                score += max(gram[i][m] for m in combo)
            if score > best_score:
                best_score = score
                best_combo = combo

        assert best_combo is not None
        return [candidates[index] for index in best_combo]

    def build_frontier(self, candidates: list[CandidatePlan]) -> FrontierResult:
        pareto = self.pareto_filter(candidates)
        deduped = self.dedupe(pareto)
        gram = self.gram_matrix(deduped)
        medoids = self.select_medoids(deduped, max_k=3)
        return FrontierResult(
            pareto_candidates=pareto,
            deduped_candidates=deduped,
            gram_matrix=gram,
            medoid_candidates=medoids,
        )

    @staticmethod
    def _dominates(lhs: CandidatePlan, rhs: CandidatePlan) -> bool:
        l = lhs.objective_vec.model_dump()
        r = rhs.objective_vec.model_dump()
        lhs_ge_all = all(l[key] >= r[key] for key in l)
        lhs_gt_any = any(l[key] > r[key] for key in l)
        return lhs_ge_all and lhs_gt_any

    def _feature_vector(self, candidate: CandidatePlan) -> list[float]:
        macro = self._normalize([float(v) for v in candidate.macro_vec])

        meso_bits = [1.0 if tag in set(candidate.meso_tags) else 0.0 for tag in MESO_TAXONOMY]
        meso = self._normalize(meso_bits)

        micro_raw = [
            float(len(candidate.micro_targets.files)),
            float(len(candidate.micro_targets.tests)),
            1.0 if candidate.micro_targets.migration else 0.0,
            1.0 if candidate.micro_targets.config else 0.0,
            1.0 if candidate.micro_targets.endpoint else 0.0,
            1.0 if candidate.micro_targets.env_var else 0.0,
        ]
        micro = self._normalize(micro_raw)

        objective_raw = [
            candidate.objective_vec.correctness_confidence,
            candidate.objective_vec.reversibility,
            candidate.objective_vec.locality,
            candidate.objective_vec.maintainability,
            candidate.objective_vec.delivery_speed,
        ]
        objective = self._normalize(objective_raw)

        return macro + meso + micro + objective

    @staticmethod
    def _normalize(values: list[float]) -> list[float]:
        norm = math.sqrt(sum(v * v for v in values))
        if norm == 0:
            return values
        return [v / norm for v in values]

    @staticmethod
    def _cosine(lhs: list[float], rhs: list[float]) -> float:
        dot = sum(a * b for a, b in zip(lhs, rhs, strict=False))
        l_norm = math.sqrt(sum(a * a for a in lhs))
        r_norm = math.sqrt(sum(b * b for b in rhs))
        if l_norm == 0 or r_norm == 0:
            return 0.0
        return dot / (l_norm * r_norm)
