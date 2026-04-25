from sqlalchemy import text

from apps.conductor.db.models import create_session_factory
from apps.conductor.services.candidate_generation import CandidateGenerationService
from apps.conductor.services.overlay_state import OverlayResolution, OverlayStateService
from apps.conductor.services.package_semantics import classify_package_status
from apps.conductor.services.retrieval import MemoryRetrievalService
from shared.schemas.models import AliasOverlayUpsertRequest, DecisionState, PairOverlayUpsertRequest


class DummyOMLX:
    def chat(self, alias, messages, **kwargs):
        return {"choices": [{"message": {"content": {"role": "minimal_patch"}}}]}

    def embed(self, alias, inputs):
        return [[1.0, 0.0] for _ in inputs]

    def rerank(self, alias, query, documents):
        return [{"index": idx, "score": 1.0 / (idx + 1)} for idx, _ in enumerate(documents)]


def test_overlay_resolution_precedence_and_transcript_safety():
    SessionFactory = create_session_factory("sqlite+pysqlite:///:memory:")
    overlays = OverlayStateService()
    with SessionFactory() as session:
        overlays.upsert_alias_overlay(
            session,
            AliasOverlayUpsertRequest(
                repo="repo1",
                alias_name="builder-a",
                summary="prefer narrow files",
                guidance=["prefer tests first"],
                applies_to_tasks=["task-1"],
                tags=["api"],
            ),
        )
        overlays.upsert_pair_overlay(
            session,
            PairOverlayUpsertRequest(
                repo="repo1",
                pair_key="alice+bob",
                summary="pair prefers explicit rollback",
                guidance=["avoid broad refactor"],
                applies_to_tasks=["task-1"],
            ),
        )
        resolution = overlays.resolve(
            session=session,
            repo="repo1",
            task_id="task-1",
            macro_constraints=["global-constraint"],
            global_memory=["global-memory-line"],
            alias_name="builder-a",
            pair_key="alice+bob",
        )
        row = session.execute(
            text("SELECT payload FROM alias_memory_state WHERE repo='repo1' AND alias_name='builder-a'")
        ).fetchone()

    assert resolution.active_overlays == ["alias-local:builder-a", "pair-local:alice+bob"]
    assert resolution.as_prompt_lines() == [
        "global_constraints=['global-constraint']",
        "global_memory=['global-memory-line']",
        "alias_overlay=['prefer narrow files', 'prefer tests first']",
        "pair_overlay=['pair prefers explicit rollback', 'avoid broad refactor']",
    ]
    sanitized = overlays._sanitize_overlay_payload({"summary": "x", "prompt": "raw", "messages": ["a"], "transcript": "b"})
    assert "prompt" not in row[0]
    assert "prompt" not in sanitized
    assert "messages" not in sanitized
    assert "transcript" not in sanitized


def test_alias_local_retrieval_inclusion_exclusion():
    SessionFactory = create_session_factory("sqlite+pysqlite:///:memory:")
    retrieval = MemoryRetrievalService(omlx_client=DummyOMLX())
    overlays = OverlayStateService()
    with SessionFactory() as session:
        overlays.upsert_alias_overlay(
            session,
            AliasOverlayUpsertRequest(
                repo="repo1",
                alias_name="builder-a",
                summary="cache overlay guidance",
                guidance=["cache key naming"],
                applies_to_tasks=["task-1"],
            ),
        )
        retrieval.refresh_fts_from_memory_tables(session=session, repo="repo1")
        included = retrieval.query(
            session=session,
            query="cache",
            top_k=5,
            repo="repo1",
            task_id="task-1",
            alias_name="builder-a",
        )
        excluded = retrieval.query(
            session=session,
            query="cache",
            top_k=5,
            repo="repo1",
            task_id="task-1",
            alias_name="builder-b",
        )

    assert any(hit.source == "alias_overlay" for hit in included.reranked)
    assert all(hit.source != "alias_overlay" for hit in excluded.reranked)


def test_pair_local_retrieval_inclusion_exclusion():
    SessionFactory = create_session_factory("sqlite+pysqlite:///:memory:")
    retrieval = MemoryRetrievalService(omlx_client=DummyOMLX())
    overlays = OverlayStateService()
    with SessionFactory() as session:
        overlays.upsert_pair_overlay(
            session,
            PairOverlayUpsertRequest(
                repo="repo1",
                pair_key="alice+bob",
                summary="pair overlay testing policy",
                guidance=["pair-specific test emphasis"],
                applies_to_tasks=["task-1"],
            ),
        )
        retrieval.refresh_fts_from_memory_tables(session=session, repo="repo1")
        included = retrieval.query(
            session=session,
            query="pair overlay",
            top_k=5,
            repo="repo1",
            task_id="task-1",
            pair_key="alice+bob",
        )
        excluded = retrieval.query(
            session=session,
            query="pair overlay",
            top_k=5,
            repo="repo1",
            task_id="task-1",
            pair_key="carol+dave",
        )

    assert any(hit.source == "pair_overlay" for hit in included.reranked)
    assert all(hit.source != "pair_overlay" for hit in excluded.reranked)


def test_prompt_assembly_surfaces_active_overlays_compactly():
    service = CandidateGenerationService(omlx_client=DummyOMLX())
    decision = DecisionState(
        repo="repo1",
        task_id="task-1",
        issue_summary="fix cache behavior",
        macro_constraints=["global hard gate"],
    )
    overlay = OverlayResolution(
        active_overlays=["alias-local:builder-a", "pair-local:alice+bob"],
        global_constraints=["global hard gate"],
        global_memory=["chosen memory summary"],
        alias_guidance=["alias guidance"],
        pair_guidance=["pair guidance"],
    )

    messages = service._build_messages(decision_state=decision, role="minimal_patch", overlay_resolution=overlay)
    user_message = messages[1]["content"]

    assert "active_overlays=['alias-local:builder-a', 'pair-local:alice+bob']" in user_message
    assert "global_constraints=['global hard gate']" in user_message
    assert "global_memory=['chosen memory summary']" in user_message
    assert "alias_overlay=['alias guidance']" in user_message
    assert "pair_overlay=['pair guidance']" in user_message


def test_milestone6_package_semantics_regression_remains_intact():
    assert classify_package_status("completed").canonical_memory_allowed is True
    assert classify_package_status("blocked").mode == "draft_only"
    assert classify_package_status("failed").mode == "draft_only"
    assert classify_package_status("reviewing").rejected is True
