"""Milestone 3 feasibility certification with explicit pass/fail reasons."""

from __future__ import annotations

from dataclasses import dataclass

from shared.schemas.models import CandidatePlan, FeasibilityCertificate


@dataclass
class FeasibilityResult:
    candidate: CandidatePlan
    certificate: FeasibilityCertificate
    feasible: bool


class FeasibilityService:
    def certify(self, candidate: CandidatePlan) -> FeasibilityResult:
        notes: list[str] = []

        macro_pass = bool(candidate.macro_vec) and len(candidate.macro_vec) == 6
        if not macro_pass:
            notes.append("macro_fail: macro_vec must have 6 axes")

        meso_pass = len(candidate.meso_tags) > 0
        if not meso_pass:
            notes.append("meso_fail: at least one meso tag is required")

        micro_pass = len(candidate.micro_targets.files) > 0
        if not micro_pass:
            notes.append("micro_fail: at least one file target is required")

        lint_plan_valid = True
        test_plan_valid = len(candidate.test_plan) > 0
        if not test_plan_valid:
            notes.append("test_plan_fail: test_plan cannot be empty")

        rollback_plan_valid = len(candidate.rollback_plan.strip()) > 4
        if not rollback_plan_valid:
            notes.append("rollback_fail: rollback_plan is missing or too short")

        migration_policy_pass = not candidate.micro_targets.migration or rollback_plan_valid
        if not migration_policy_pass:
            notes.append("migration_policy_fail: migration=true requires strong rollback plan")

        security_policy_pass = True
        scope_policy_pass = len(candidate.micro_targets.files) <= 12
        if not scope_policy_pass:
            notes.append("scope_policy_fail: candidate touches too many files for v1")

        if not notes:
            notes.append("all_feasibility_checks_passed")

        cert = FeasibilityCertificate(
            macro_pass=macro_pass,
            meso_pass=meso_pass,
            micro_pass=micro_pass,
            lint_plan_valid=lint_plan_valid,
            test_plan_valid=test_plan_valid,
            rollback_plan_valid=rollback_plan_valid,
            migration_policy_pass=migration_policy_pass,
            security_policy_pass=security_policy_pass,
            scope_policy_pass=scope_policy_pass,
            notes=notes,
        )

        feasible = all(
            [
                cert.macro_pass,
                cert.meso_pass,
                cert.micro_pass,
                cert.lint_plan_valid,
                cert.test_plan_valid,
                cert.rollback_plan_valid,
                cert.migration_policy_pass,
                cert.security_policy_pass,
                cert.scope_policy_pass,
            ]
        )

        return FeasibilityResult(candidate=candidate, certificate=cert, feasible=feasible)

    def gate(self, candidates: list[CandidatePlan]) -> tuple[list[FeasibilityResult], list[FeasibilityResult]]:
        feasible: list[FeasibilityResult] = []
        infeasible: list[FeasibilityResult] = []
        for candidate in candidates:
            result = self.certify(candidate)
            if result.feasible:
                feasible.append(result)
            else:
                infeasible.append(result)
        return feasible, infeasible
