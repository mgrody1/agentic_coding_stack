from sqlalchemy import text

from apps.conductor.db.models import create_session_factory
from apps.conductor.services.retrieval import MemoryRetrievalService


class DummyOMLX:
    def embed(self, alias, inputs):
        return [[1.0, 0.0] for _ in inputs]

    def rerank(self, alias, query, documents):
        return [{"index": idx, "score": 1.0 / (idx + 1)} for idx, _ in enumerate(documents)]


def test_retrieval_ingestion_from_structured_memory_tables():
    SessionFactory = create_session_factory("sqlite+pysqlite:///:memory:")
    service = MemoryRetrievalService(omlx_client=DummyOMLX())

    with SessionFactory() as session:
        session.execute(text("INSERT INTO frontier_memory(repo, payload, summary_text) VALUES ('repo1', '{}', 'frontier summary')"))
        session.execute(text("INSERT INTO residual_memory(repo, payload, summary_text) VALUES ('repo1', '{}', 'residual summary')"))
        session.execute(text("INSERT INTO outcome_memory(repo, decision_state_id, outcome, score, notes) VALUES ('repo1', 1, 'ok', 1.0, 'outcome notes')"))
        session.execute(text("INSERT INTO decision_state(repo, task_id, payload, created_at) VALUES ('repo1', 't1', :payload, CURRENT_TIMESTAMP)"), {"payload": '{"issue_summary": "issue context text"}'})
        session.commit()

        ingested = service.refresh_fts_from_memory_tables(session=session, repo="repo1")
        assert ingested >= 4

        hits = service.lexical_search(session=session, query="summary", top_k=10)
        assert len(hits) >= 2
