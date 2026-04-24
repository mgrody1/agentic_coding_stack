"""Milestone 2 retrieval: lexical + embedding + rerank for memory query."""

from __future__ import annotations

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
                metadata={"fts_metadata": row[3]},
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
            # Placeholder deterministic similarity with oMLX-provided shape.
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

    def query(self, session: Session, query: str, top_k: int) -> RetrievalBundle:
        lexical = self.lexical_search(session, query=query, top_k=top_k * 2)
        embedding = self.embedding_search(query=query, lexical_hits=lexical, top_k=top_k * 2)
        reranked = self.rerank(query=query, hits=embedding, top_k=top_k)
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
    def ingest_memory_rows(session: Session, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            session.execute(
                text(
                    "INSERT INTO memory_fts(source, record_id, text, metadata) VALUES (:source, :record_id, :text, :metadata)"
                ),
                row,
            )
        session.commit()
