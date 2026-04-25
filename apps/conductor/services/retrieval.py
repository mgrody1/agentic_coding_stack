"""Milestone 2 retrieval: lexical + embedding + rerank for memory query."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.schemas.models import MemoryHit


@dataclass
class RetrievalBundle:
    lexical: list[MemoryHit]
    embedding: list[MemoryHit]
    reranked: list[MemoryHit]


class MemoryRetrievalService:
    def __init__(self, omlx_client):
        self.omlx_client = omlx_client

    @staticmethod
    def ensure_fts(session: Session) -> None:
        session.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(source, record_id, text, metadata)"
            )
        )
        session.commit()

    def lexical_search(self, session: Session, query: str, top_k: int) -> list[MemoryHit]:
        self.ensure_fts(session)
        rows = session.execute(
            text(
                "SELECT source, record_id, text, metadata, rank FROM memory_fts WHERE memory_fts MATCH :q ORDER BY rank LIMIT :k"
            ),
            {"q": query, "k": top_k},
        ).fetchall()
        return [
            MemoryHit(
                source=row[0],
                record_id=int(row[1]),
                text=row[2],
                metadata=self._decode_metadata(row[3]),
                score=float(-row[4]),
            )
            for row in rows
        ]

    def embedding_search(self, query: str, lexical_hits: list[MemoryHit], top_k: int) -> list[MemoryHit]:
        if not lexical_hits:
            return []
        query_embedding = self.omlx_client.embed("mem-embed", [query])[0]
        rescored: list[MemoryHit] = []
        for hit in lexical_hits:
            reference = self.omlx_client.embed("mem-embed", [hit.text])[0]
            sim = self._cosine(query_embedding, reference)
            rescored.append(hit.model_copy(update={"score": sim}))
        rescored.sort(key=lambda h: h.score, reverse=True)
        return rescored[:top_k]

    def rerank(self, query: str, hits: list[MemoryHit], top_k: int) -> list[MemoryHit]:
        if not hits:
            return []
        docs = [hit.text for hit in hits]
        reranked = self.omlx_client.rerank("mem-rerank", query, docs)
        mapped: list[MemoryHit] = []
        for item in reranked[:top_k]:
            original = hits[item["index"]]
            mapped.append(original.model_copy(update={"score": float(item["score"])}))
        return mapped

    def query(
        self,
        session: Session,
        query: str,
        top_k: int,
        repo: str | None = None,
        task_id: str | None = None,
        alias_name: str | None = None,
        pair_key: str | None = None,
    ) -> RetrievalBundle:
        lexical = self.lexical_search(session, query=query, top_k=top_k * 2)
        lexical = [
            hit
            for hit in lexical
            if self._is_overlay_hit_relevant(hit, repo=repo, task_id=task_id, alias_name=alias_name, pair_key=pair_key)
        ]
        embedding = self.embedding_search(query=query, lexical_hits=lexical, top_k=top_k * 2)
        reranked = self.rerank(query=query, hits=embedding, top_k=top_k)
        reranked = self._apply_overlay_boosts(reranked, alias_name=alias_name, pair_key=pair_key)
        reranked.sort(key=lambda h: h.score, reverse=True)
        return RetrievalBundle(lexical=lexical, embedding=embedding, reranked=reranked)

    @staticmethod
    def _cosine(lhs: list[float], rhs: list[float]) -> float:
        dot = sum(a * b for a, b in zip(lhs, rhs, strict=False))
        l_norm = sum(a * a for a in lhs) ** 0.5
        r_norm = sum(b * b for b in rhs) ** 0.5
        if l_norm == 0 or r_norm == 0:
            return 0.0
        return dot / (l_norm * r_norm)

    @staticmethod
    def ingest_memory_rows(session: Session, rows: list[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            session.execute(
                text(
                    "INSERT INTO memory_fts(source, record_id, text, metadata) VALUES (:source, :record_id, :text, :metadata)"
                ),
                row,
            )
            count += 1
        session.commit()
        return count

    def refresh_fts_from_memory_tables(self, session: Session, repo: str) -> int:
        """Simple ingestion path from structured memory tables into FTS rows."""
        self.ensure_fts(session)
        session.execute(text("DELETE FROM memory_fts WHERE json_extract(metadata, '$.repo') = :repo"), {"repo": repo})

        rows: list[dict[str, Any]] = []
        table_specs = [
            ("chosen_memory", "summary_text"),
            ("frontier_memory", "summary_text"),
            ("residual_memory", "summary_text"),
            ("outcome_memory", "notes"),
        ]
        for table_name, text_col in table_specs:
            fetched = session.execute(
                text(f"SELECT id, repo, {text_col} FROM {table_name} WHERE repo = :repo"),
                {"repo": repo},
            ).fetchall()
            for row in fetched:
                summary = row[2] or ""
                if not summary.strip():
                    continue
                rows.append(
                    {
                        "source": table_name,
                        "record_id": int(row[0]),
                        "text": summary,
                        "metadata": json.dumps({"repo": row[1], "table": table_name}),
                    }
                )

        decision_rows = session.execute(
            text("SELECT id, repo, payload FROM decision_state WHERE repo = :repo"),
            {"repo": repo},
        ).fetchall()
        for row in decision_rows:
            payload = self._decode_metadata(row[2])
            issue_summary = payload.get("issue_summary")
            if issue_summary:
                rows.append(
                    {
                        "source": "decision_state",
                        "record_id": int(row[0]),
                        "text": issue_summary,
                        "metadata": json.dumps({"repo": row[1], "table": "decision_state"}),
                    }
                )

        alias_rows = session.execute(
            text("SELECT id, repo, alias_name, payload FROM alias_memory_state WHERE repo = :repo"),
            {"repo": repo},
        ).fetchall()
        for row in alias_rows:
            payload = self._decode_metadata(row[3])
            if not payload:
                continue
            summary = payload.get("summary") or ""
            guidance = payload.get("guidance") or []
            text_blob = "\n".join([summary, *[str(item) for item in guidance if str(item).strip()]]).strip()
            if not text_blob:
                continue
            rows.append(
                {
                    "source": "alias_overlay",
                    "record_id": int(row[0]),
                    "text": text_blob,
                    "metadata": json.dumps(
                        {
                            "repo": row[1],
                            "table": "alias_memory_state",
                            "alias_name": row[2],
                            "applies_to_tasks": payload.get("applies_to_tasks", []),
                        }
                    ),
                }
            )

        pair_rows = session.execute(
            text("SELECT id, repo, pair_key, payload FROM pair_memory_state WHERE repo = :repo"),
            {"repo": repo},
        ).fetchall()
        for row in pair_rows:
            payload = self._decode_metadata(row[3])
            if not payload:
                continue
            summary = payload.get("summary") or ""
            guidance = payload.get("guidance") or []
            text_blob = "\n".join([summary, *[str(item) for item in guidance if str(item).strip()]]).strip()
            if not text_blob:
                continue
            rows.append(
                {
                    "source": "pair_overlay",
                    "record_id": int(row[0]),
                    "text": text_blob,
                    "metadata": json.dumps(
                        {
                            "repo": row[1],
                            "table": "pair_memory_state",
                            "pair_key": row[2],
                            "applies_to_tasks": payload.get("applies_to_tasks", []),
                        }
                    ),
                }
            )

        if not rows:
            session.commit()
            return 0
        return self.ingest_memory_rows(session, rows)

    @staticmethod
    def _decode_metadata(raw: str | dict | None) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {"raw": raw}
        return {}

    def _is_overlay_hit_relevant(
        self,
        hit: MemoryHit,
        repo: str | None,
        task_id: str | None,
        alias_name: str | None,
        pair_key: str | None,
    ) -> bool:
        if hit.source not in {"alias_overlay", "pair_overlay"}:
            return True
        metadata = hit.metadata
        if repo and metadata.get("repo") and metadata.get("repo") != repo:
            return False
        tasks = metadata.get("applies_to_tasks", [])
        if tasks and task_id and task_id not in set(tasks):
            return False
        if hit.source == "alias_overlay":
            return bool(alias_name and metadata.get("alias_name") == alias_name)
        if hit.source == "pair_overlay":
            return bool(pair_key and metadata.get("pair_key") == pair_key)
        return True

    @staticmethod
    def _apply_overlay_boosts(hits: list[MemoryHit], alias_name: str | None, pair_key: str | None) -> list[MemoryHit]:
        boosted: list[MemoryHit] = []
        for hit in hits:
            score = hit.score
            if hit.source == "alias_overlay" and alias_name:
                score += 0.10
            if hit.source == "pair_overlay" and pair_key:
                score += 0.15
            boosted.append(hit.model_copy(update={"score": score}))
        return boosted
