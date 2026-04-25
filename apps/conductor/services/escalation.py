"""Milestone 10 bounded escalation workflow."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session


class EscalationService:
    def observe_execution_outcome(
        self,
        *,
        session: Session,
        job_id: str,
        status: str,
        cause_code: str,
        threshold: int,
    ) -> None:
        row = session.execute(
            text("SELECT failure_streak, escalated, level FROM job_escalation WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        streak = int(row[0]) if row else 0
        escalated = bool(row[1]) if row else False
        level = int(row[2]) if row else 0

        if status in {"blocked", "failed"}:
            streak += 1
        else:
            streak = 0
            escalated = False
            level = 0

        reason_code = ""
        if streak >= threshold:
            escalated = True
            level = min(level + 1 if level > 0 else 1, 2)
            reason_code = "ESCALATION_FAILURE_STREAK"

        session.execute(
            text(
                """
                INSERT INTO job_escalation(job_id, failure_streak, escalated, level, reason_code, updated_at)
                VALUES (:job_id, :failure_streak, :escalated, :level, :reason_code, :updated_at)
                ON CONFLICT(job_id) DO UPDATE SET
                    failure_streak = excluded.failure_streak,
                    escalated = excluded.escalated,
                    level = excluded.level,
                    reason_code = excluded.reason_code,
                    updated_at = excluded.updated_at
                """
            ),
            {
                "job_id": job_id,
                "failure_streak": streak,
                "escalated": escalated,
                "level": level,
                "reason_code": reason_code or cause_code,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        session.commit()
