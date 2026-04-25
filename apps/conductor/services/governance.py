"""Milestone 10 governance: policy guards, approvals, and operator ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.conductor.services.reliability import stable_json_dumps


ALLOWED_ROLES: dict[str, set[str]] = {
    "cancel": {"operator", "admin"},
    "resume_execute": {"operator", "admin"},
    "retry_execute": {"operator", "admin"},
    "retry_package": {"admin"},
    "replay_execute": {"system", "operator", "admin"},
    "replay_package": {"system", "operator", "admin"},
}
APPROVAL_REASON_CODES = {"ops_override", "security_override", "incident_recovery"}


class GovernanceService:
    def enforce_role(self, *, action: str, actor_role: str) -> None:
        allowed = ALLOWED_ROLES.get(action, {"admin"})
        if actor_role not in allowed:
            raise HTTPException(
                status_code=403,
                detail={"cause_code": "POLICY_ROLE_FORBIDDEN", "action": action, "actor_role": actor_role},
            )

    def require_retry_package_approval(
        self,
        *,
        allow_duplicate_side_effects: bool,
        existing_completed_count: int,
        approval_token: str | None,
        configured_approval_token: str,
        approval_reason_code: str | None,
    ) -> None:
        if not existing_completed_count or not allow_duplicate_side_effects:
            return
        if not approval_token:
            raise HTTPException(status_code=409, detail={"cause_code": "APPROVAL_REQUIRED_FOR_DUPLICATE_PACKAGE_RETRY"})
        if approval_token != configured_approval_token:
            raise HTTPException(status_code=409, detail={"cause_code": "APPROVAL_TOKEN_INVALID"})
        if approval_reason_code not in APPROVAL_REASON_CODES:
            raise HTTPException(status_code=409, detail={"cause_code": "APPROVAL_REASON_CODE_INVALID"})

    def authorize_action(
        self,
        session: Session,
        *,
        job_id: str,
        actor_role: str,
        action: str,
        reason_code: str,
        cause_code: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.enforce_role(action=action, actor_role=actor_role)
        self.ledger(
            session=session,
            job_id=job_id,
            actor_role=actor_role,
            action=action,
            reason_code=reason_code,
            approved=True,
            cause_code=cause_code,
            details=details,
        )

    def ledger(
        self,
        session: Session,
        *,
        job_id: str,
        actor_role: str,
        action: str,
        reason_code: str,
        approved: bool,
        cause_code: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        session.execute(
            text(
                """
                INSERT INTO operator_action_ledger(job_id, actor_role, action, reason_code, approved, cause_code, details, created_at)
                VALUES (:job_id, :actor_role, :action, :reason_code, :approved, :cause_code, :details, :created_at)
                """
            ),
            {
                "job_id": job_id,
                "actor_role": actor_role,
                "action": action,
                "reason_code": reason_code,
                "approved": approved,
                "cause_code": cause_code,
                "details": stable_json_dumps(details or {}),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        session.commit()
