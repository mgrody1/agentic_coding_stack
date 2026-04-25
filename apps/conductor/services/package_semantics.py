"""Milestone 6 package-time semantics for draft payload and memory persistence.

This module centralizes package eligibility rules so the `/jobs/{id}/package`
endpoint and memory writers share one deterministic policy.
"""

from __future__ import annotations

from dataclasses import dataclass


CANONICAL_PERSIST_STATUSES = frozenset({"completed"})
DRAFT_ONLY_STATUSES = frozenset({"blocked", "failed"})
REJECTED_PACKAGE_STATUSES = frozenset(
    {
        "queued",
        "prepared",
        "implementing",
        "validating",
        "reviewing",
        "repairing",
        "finalizing",
    }
)


@dataclass(frozen=True)
class PackageSemantics:
    status: str
    draft_allowed: bool
    canonical_memory_allowed: bool
    rejected: bool

    @property
    def mode(self) -> str:
        if self.rejected:
            return "rejected"
        if self.canonical_memory_allowed:
            return "canonical"
        return "draft_only"


def classify_package_status(status: str) -> PackageSemantics:
    """Classify package behavior for an execution status.

    Rules:
    - `completed`: draft payload + canonical memory writes are allowed.
    - `blocked` or `failed`: draft payload is allowed, but canonical chosen
      memory persistence is disallowed.
    - In-progress statuses are rejected from package-time handling.
    """

    if status in CANONICAL_PERSIST_STATUSES:
        return PackageSemantics(
            status=status,
            draft_allowed=True,
            canonical_memory_allowed=True,
            rejected=False,
        )

    if status in DRAFT_ONLY_STATUSES:
        return PackageSemantics(
            status=status,
            draft_allowed=True,
            canonical_memory_allowed=False,
            rejected=False,
        )

    return PackageSemantics(
        status=status,
        draft_allowed=False,
        canonical_memory_allowed=False,
        rejected=True,
    )
