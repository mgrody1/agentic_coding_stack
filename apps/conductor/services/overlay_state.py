"""Milestone 7A overlay state storage and precedence-aware resolution."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.schemas.models import (
    AliasOverlayUpsertRequest,
    OverlayRecord,
    PairOverlayUpsertRequest,
)


@dataclass
class OverlayResolution:
    active_overlays: list[str]
    global_constraints: list[str]
    global_memory: list[str]
    alias_guidance: list[str]
    pair_guidance: list[str]

    def as_prompt_lines(self) -> list[str]:
        return [
            f"global_constraints={self.global_constraints}",
            f"global_memory={self.global_memory}",
            f"alias_overlay={self.alias_guidance}",
            f"pair_overlay={self.pair_guidance}",
        ]


class OverlayStateService:
    @staticmethod
    def _sanitize_overlay_payload(payload: dict) -> dict:
        # Do not persist raw prompt transcripts in overlay state.
        blocked_keys = {"messages", "prompt", "transcript"}
        return {k: v for k, v in payload.items() if k not in blocked_keys}

    def upsert_alias_overlay(self, session: Session, request: AliasOverlayUpsertRequest) -> OverlayRecord:
        payload = self._sanitize_overlay_payload(
            {
                "summary": request.summary,
                "guidance": request.guidance,
                "applies_to_tasks": request.applies_to_tasks,
                "tags": request.tags,
            }
        )
        row = session.execute(
            text("SELECT id FROM alias_memory_state WHERE repo = :repo AND alias_name = :alias_name"),
            {"repo": request.repo, "alias_name": request.alias_name},
        ).fetchone()
        if row:
            session.execute(
                text("UPDATE alias_memory_state SET payload = :payload WHERE id = :id"),
                {"id": int(row[0]), "payload": json.dumps(payload)},
            )
        else:
            session.execute(
                text("INSERT INTO alias_memory_state(repo, alias_name, payload) VALUES (:repo, :alias_name, :payload)"),
                {"repo": request.repo, "alias_name": request.alias_name, "payload": json.dumps(payload)},
            )
        session.commit()
        return OverlayRecord(
            repo=request.repo,
            scope="alias_local",
            name=request.alias_name,
            summary=request.summary,
            guidance=request.guidance,
            applies_to_tasks=request.applies_to_tasks,
            tags=request.tags,
        )

    def upsert_pair_overlay(self, session: Session, request: PairOverlayUpsertRequest) -> OverlayRecord:
        payload = self._sanitize_overlay_payload(
            {
                "summary": request.summary,
                "guidance": request.guidance,
                "applies_to_tasks": request.applies_to_tasks,
                "tags": request.tags,
            }
        )
        row = session.execute(
            text("SELECT id FROM pair_memory_state WHERE repo = :repo AND pair_key = :pair_key"),
            {"repo": request.repo, "pair_key": request.pair_key},
        ).fetchone()
        if row:
            session.execute(
                text("UPDATE pair_memory_state SET payload = :payload WHERE id = :id"),
                {"id": int(row[0]), "payload": json.dumps(payload)},
            )
        else:
            session.execute(
                text("INSERT INTO pair_memory_state(repo, pair_key, payload) VALUES (:repo, :pair_key, :payload)"),
                {"repo": request.repo, "pair_key": request.pair_key, "payload": json.dumps(payload)},
            )
        session.commit()
        return OverlayRecord(
            repo=request.repo,
            scope="pair_local",
            name=request.pair_key,
            summary=request.summary,
            guidance=request.guidance,
            applies_to_tasks=request.applies_to_tasks,
            tags=request.tags,
        )

    def resolve(
        self,
        session: Session,
        repo: str,
        task_id: str,
        macro_constraints: list[str],
        global_memory: list[str],
        alias_name: str | None = None,
        pair_key: str | None = None,
    ) -> OverlayResolution:
        alias_guidance: list[str] = []
        pair_guidance: list[str] = []
        active: list[str] = []
        if alias_name:
            row = session.execute(
                text("SELECT payload FROM alias_memory_state WHERE repo = :repo AND alias_name = :alias_name"),
                {"repo": repo, "alias_name": alias_name},
            ).fetchone()
            payload = self._decode_payload(row[0]) if row else {}
            if payload and self._task_matches(task_id, payload.get("applies_to_tasks", [])):
                alias_guidance = self._flatten_guidance(payload)
                active.append(f"alias-local:{alias_name}")

        if pair_key:
            row = session.execute(
                text("SELECT payload FROM pair_memory_state WHERE repo = :repo AND pair_key = :pair_key"),
                {"repo": repo, "pair_key": pair_key},
            ).fetchone()
            payload = self._decode_payload(row[0]) if row else {}
            if payload and self._task_matches(task_id, payload.get("applies_to_tasks", [])):
                pair_guidance = self._flatten_guidance(payload)
                active.append(f"pair-local:{pair_key}")

        return OverlayResolution(
            active_overlays=active,
            # precedence order is explicit and stable for prompt assembly:
            # global constraints > global memory > alias-local > pair-local
            global_constraints=list(macro_constraints),
            global_memory=list(global_memory),
            alias_guidance=alias_guidance,
            pair_guidance=pair_guidance,
        )

    @staticmethod
    def _task_matches(task_id: str, applies_to_tasks: list[str]) -> bool:
        if not applies_to_tasks:
            return True
        return task_id in set(applies_to_tasks)

    @staticmethod
    def _flatten_guidance(payload: dict) -> list[str]:
        guidance = payload.get("guidance", [])
        summary = payload.get("summary")
        lines = []
        if isinstance(summary, str) and summary.strip():
            lines.append(summary.strip())
        if isinstance(guidance, list):
            lines.extend(str(item) for item in guidance if str(item).strip())
        return lines

    @staticmethod
    def _decode_payload(raw: object) -> dict:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}
        return {}
