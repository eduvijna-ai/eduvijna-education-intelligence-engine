from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.knowledge_intelligence.contracts import KnowledgeRetrievalRequest
from app.knowledge_intelligence.fixtures import seed_knowledge_fixtures
from app.knowledge_intelligence.indexing import index_source_revision
from app.knowledge_intelligence.retrieval import retrieve_knowledge
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_tenant_isolation_drops_foreign_institution_evidence() -> None:
    adapter = FakeAnythingLLMAdapter()
    with _session() as session:
        fixtures = seed_knowledge_fixtures(session)
        session.commit()
        index_source_revision(
            session,
            adapter,
            fixtures.official_revision_id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        index_source_revision(
            session,
            adapter,
            fixtures.institution_revision_id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        session.commit()

        foreign = retrieve_knowledge(
            session,
            adapter,
            KnowledgeRetrievalRequest(
                query_text="quadratic worksheet practice",
                organization_id="foreign-org",
                institution_id="foreign-inst",
                top_k=5,
                retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
            ),
        )
        assert all("institution worksheet" not in item.title.lower() for item in foreign.items)

        scoped = retrieve_knowledge(
            session,
            adapter,
            KnowledgeRetrievalRequest(
                query_text="quadratic worksheet practice",
                organization_id=fixtures.organization_id,
                institution_id=fixtures.institution_id,
                top_k=5,
                retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
            ),
        )
        assert any("institution" in item.title.lower() for item in scoped.items)
        assert all(item.source_revision_checksum for item in scoped.items)


def test_authority_metadata_not_upgraded_by_score() -> None:
    adapter = FakeAnythingLLMAdapter()
    with _session() as session:
        fixtures = seed_knowledge_fixtures(session)
        session.commit()
        index_source_revision(
            session,
            adapter,
            fixtures.official_revision_id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        session.commit()
        result = retrieve_knowledge(
            session,
            adapter,
            KnowledgeRetrievalRequest(
                query_text="quadratic equations",
                top_k=3,
                retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
            ),
        )
        for item in result.items:
            assert item.authority_label != "official_source" or item.trust_tier in {
                "official_primary",
                "official_supporting",
            }
