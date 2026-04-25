"""Milestone 10 control-plane governance orchestration helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.conductor.services.governance import GovernanceService
from apps.conductor.services.reliability import TelemetryService, stable_json_loads

VALID_CHECKPOINTS = {"prepared", "validating", "reviewing", "repairing", "finalizing", "completed", "blocked", "failed"}


class ControlPlaneService:
    def __init__(self, governance_service: GovernanceService, telemetry_service: TelemetryService, approval_token: str):
        self.governance_service = governance_service
        self.telemetry_service = telemetry_service
        self.approval_token = approval_token

    def cancel(self, *, session: Session, job_id: str, reason: str, actor_role: str) -> datetime:
        now = datetime.now(timezone.utc)
        self.governance_service.authorize_action(
            session=session,
            job_id=job_id,
            actor_role=actor_role,
            action="cancel",
            reason_code="CONTROL_CANCEL_REQUESTED",
            cause_code="CONTROL_CANCELLED",
            details={"reason": reason},
        )
        session.execute(
            text(
                """
                INSERT INTO job_control(job_id, cancelled, reason, updated_at)
                VALUES (:job_id, 1, :reason, :updated_at)
                ON CONFLICT(job_id) DO UPDATE SET
                    cancelled = 1,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at
                """
            ),
            {"job_id": job_id, "reason": reason, "updated_at": now.isoformat()},
        )
        session.commit()
        self.telemetry_service.emit(
            session=session,
            job_id=job_id,
            route="control",
            phase="cancel",
            status="completed",
            cause_code="CONTROL_CANCELLED",
            replayed=False,
            idempotency_key=f"cancel:{job_id}",
            details={"reason": reason},
        )
        return now

    def resume_validate_and_record(
        self,
        *,
        session: Session,
        job_id: str,
        checkpoint_stage: str,
        idempotency_key: str,
        actor_role: str,
    ) -> None:
        row = session.execute(
            text("SELECT transitions FROM execution_state WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        transitions = stable_json_loads(row[0], fallback=[]) if row else []
        checkpoint_set = {item.get("stage") for item in transitions if isinstance(item, dict)}
        if checkpoint_stage not in VALID_CHECKPOINTS or checkpoint_stage not in checkpoint_set:
            raise HTTPException(status_code=409, detail={"cause_code": "RESUME_INVALID_CHECKPOINT"})

        self.governance_service.authorize_action(
            session=session,
            job_id=job_id,
            actor_role=actor_role,
            action="resume_execute",
            reason_code="CONTROL_RESUME_REQUESTED",
            cause_code="RESUME_ACCEPTED",
            details={"checkpoint_stage": checkpoint_stage},
        )
        self.telemetry_service.emit(
            session=session,
            job_id=job_id,
            route="control",
            phase="resume",
            status="accepted",
            cause_code="RESUME_ACCEPTED",
            replayed=False,
            idempotency_key=idempotency_key,
            details={"checkpoint_stage": checkpoint_stage},
        )

    def retry_execute_record(self, *, session: Session, job_id: str, idempotency_key: str, actor_role: str) -> None:
        self.governance_service.authorize_action(
            session=session,
            job_id=job_id,
            actor_role=actor_role,
            action="retry_execute",
            reason_code="CONTROL_RETRY_EXECUTE_REQUESTED",
            cause_code="RETRY_EXECUTE_ACCEPTED",
            details={"idempotency_key": idempotency_key},
        )
        self.telemetry_service.emit(
            session=session,
            job_id=job_id,
            route="control",
            phase="retry_execute",
            status="accepted",
            cause_code="RETRY_EXECUTE_ACCEPTED",
            replayed=False,
            idempotency_key=idempotency_key,
        )

    def retry_package_validate_and_record(
        self,
        *,
        session: Session,
        job_id: str,
        actor_role: str,
        idempotency_key: str,
        existing_completed_count: int,
        allow_duplicate_side_effects: bool,
        approval_token: str | None,
        approval_reason_code: str | None,
    ) -> None:
        self.governance_service.enforce_role(action="retry_package", actor_role=actor_role)
        if existing_completed_count and not allow_duplicate_side_effects:
            self.governance_service.ledger(
                session=session,
                job_id=job_id,
                actor_role=actor_role,
                action="retry_package",
                reason_code="CONTROL_RETRY_PACKAGE_REQUESTED",
                approved=False,
                cause_code="RETRY_PACKAGE_SIDE_EFFECT_BLOCKED",
                details={"allow_duplicate_side_effects": False},
            )
            self.telemetry_service.emit(
                session=session,
                job_id=job_id,
                route="control",
                phase="retry_package",
                status="blocked",
                cause_code="RETRY_PACKAGE_SIDE_EFFECT_BLOCKED",
                replayed=False,
                idempotency_key=idempotency_key,
            )
            raise HTTPException(status_code=409, detail={"cause_code": "RETRY_PACKAGE_SIDE_EFFECT_BLOCKED"})

        self.governance_service.require_retry_package_approval(
            allow_duplicate_side_effects=allow_duplicate_side_effects,
            existing_completed_count=existing_completed_count,
            approval_token=approval_token,
            configured_approval_token=self.approval_token,
            approval_reason_code=approval_reason_code,
        )

        self.governance_service.ledger(
            session=session,
            job_id=job_id,
            actor_role=actor_role,
            action="retry_package",
            reason_code=approval_reason_code or "CONTROL_RETRY_PACKAGE_REQUESTED",
            approved=True,
            cause_code="RETRY_PACKAGE_ACCEPTED",
            details={
                "allow_duplicate_side_effects": allow_duplicate_side_effects,
                "approval_required": bool(existing_completed_count and allow_duplicate_side_effects),
            },
        )
        self.telemetry_service.emit(
            session=session,
            job_id=job_id,
            route="control",
            phase="retry_package",
            status="accepted",
            cause_code="RETRY_PACKAGE_ACCEPTED",
            replayed=False,
            idempotency_key=idempotency_key,
            details={
                "allow_duplicate_side_effects": allow_duplicate_side_effects,
                "approval_reason_code": approval_reason_code or "",
            },
        )
