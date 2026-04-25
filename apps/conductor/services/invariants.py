"""Milestone 9 invariant checks for execution/package/memory/telemetry."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.conductor.services.reliability import stable_json_loads
from shared.schemas.models import InvariantCheck


class InvariantService:
    def validate_job(self, session: Session, job_id: str) -> list[InvariantCheck]:
        checks: list[InvariantCheck] = []
        checks.extend(self._execution_checks(session, job_id))
        checks.extend(self._package_checks(session, job_id))
        checks.extend(self._memory_checks(session, job_id))
        checks.extend(self._telemetry_checks(session, job_id))
        return checks

    def _execution_checks(self, session: Session, job_id: str) -> list[InvariantCheck]:
        row = session.execute(
            text("SELECT stage, status, transitions FROM execution_state WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        if not row:
            return [InvariantCheck(name="execution_exists", ok=False, cause_code="INVAR_EXECUTION_MISSING", details="execution_state row missing")]
        transitions = stable_json_loads(row[2], fallback=[])
        ok = isinstance(transitions, list) and len(transitions) > 0
        return [InvariantCheck(name="execution_transitions_present", ok=ok, cause_code=None if ok else "INVAR_EXECUTION_TRANSITIONS_EMPTY")]

    def _package_checks(self, session: Session, job_id: str) -> list[InvariantCheck]:
        row = session.execute(
            text("SELECT cause_code, response_payload FROM package_idempotency WHERE job_id = :job_id ORDER BY id DESC LIMIT 1"),
            {"job_id": job_id},
        ).fetchone()
        if not row:
            return [InvariantCheck(name="package_optional", ok=True, details="package not invoked")]
        payload = stable_json_loads(row[1], fallback={})
        ok = isinstance(payload, dict) and "job_id" in payload
        return [InvariantCheck(name="package_response_payload_valid", ok=ok, cause_code=None if ok else "INVAR_PACKAGE_PAYLOAD_INVALID")]

    def _memory_checks(self, session: Session, job_id: str) -> list[InvariantCheck]:
        row = session.execute(
            text("SELECT response_payload FROM package_idempotency WHERE job_id = :job_id ORDER BY id DESC LIMIT 1"),
            {"job_id": job_id},
        ).fetchone()
        if not row:
            return [InvariantCheck(name="memory_gating_optional", ok=True, details="no package payload")]
        payload = stable_json_loads(row[0], fallback={})
        memory_report = payload.get("memory_report", {}) if isinstance(payload, dict) else {}
        chosen_written = bool(memory_report.get("chosen_written"))
        cause = payload.get("cause_code", "")
        ok = not chosen_written or cause == "PACKAGE_OK_CANONICAL"
        return [InvariantCheck(name="memory_canonical_gating", ok=ok, cause_code=None if ok else "INVAR_MEMORY_GATING_VIOLATION")]

    def _telemetry_checks(self, session: Session, job_id: str) -> list[InvariantCheck]:
        rows = session.execute(
            text("SELECT route, phase, status, cause_code FROM telemetry_event WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchall()
        if not rows:
            return [InvariantCheck(name="telemetry_optional", ok=True, details="no telemetry rows")]
        ok = all(str(row[3]).strip() for row in rows)
        return [InvariantCheck(name="telemetry_cause_codes_present", ok=ok, cause_code=None if ok else "INVAR_TELEMETRY_CAUSE_CODE_MISSING")]
