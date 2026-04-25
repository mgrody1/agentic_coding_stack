"""Milestone 8 reliability helpers: idempotency keys, cause codes, telemetry."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def stable_json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def stable_json_loads(raw: str | dict | list | None, fallback: Any) -> Any:
    if raw is None:
        return fallback
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return fallback
    return fallback


def derive_idempotency_key(route: str, payload: dict[str, Any], explicit_key: str | None = None) -> str:
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    digest = hashlib.sha256(stable_json_dumps(payload).encode("utf-8")).hexdigest()
    return f"{route}:{digest[:24]}"


class TelemetryService:
    def emit(
        self,
        session: Session,
        *,
        job_id: str,
        route: str,
        phase: str,
        status: str,
        cause_code: str,
        replayed: bool,
        idempotency_key: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        session.execute(
            text(
                """
                INSERT INTO telemetry_event(job_id, route, phase, status, cause_code, replayed, idempotency_key, details, created_at)
                VALUES (:job_id, :route, :phase, :status, :cause_code, :replayed, :idempotency_key, :details, :created_at)
                """
            ),
            {
                "job_id": job_id,
                "route": route,
                "phase": phase,
                "status": status,
                "cause_code": cause_code,
                "replayed": replayed,
                "idempotency_key": idempotency_key,
                "details": stable_json_dumps(details or {}),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        session.commit()
