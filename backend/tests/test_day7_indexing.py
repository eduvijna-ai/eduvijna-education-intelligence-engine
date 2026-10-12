from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.knowledge_intelligence.eligibility import IndexEligibilityError
from app.knowledge_intelligence.fixtures import seed_knowledge_fixtures, staged_revision_for_source
from app.knowledge_intelligence.indexing import index_source_revision
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION
from app.models.source import SourceRevision


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_active_revision_indexes_idempotently() -> None:
    adapter = FakeAnythingLLMAdapter()
    with _session() as session:
        fixtures = seed_knowledge_fixtures(session)
        session.commit()
        first = index_source_revision(
            session,
            adapter,
            fixtures.official_revision_id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        second = index_source_revision(
            session,
            adapter,
            fixtures.official_revision_id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        assert first.id == second.id
        assert first.index_status == "active"
        assert first.anythingllm_document_id


def test_inactive_revision_rejected() -> None:
    adapter = FakeAnythingLLMAdapter()
    with _session() as session:
        fixtures = seed_knowledge_fixtures(session)
        session.commit()
        revision = session.get(SourceRevision, fixtures.official_revision_id)
        assert revision
        staged = staged_revision_for_source(session, revision.source_id)
        with pytest.raises(IndexEligibilityError):
            index_source_revision(
                session,
                adapter,
                staged.id,
                retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
            )
