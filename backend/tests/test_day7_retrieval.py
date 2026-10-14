from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.adapters.anythingllm.types import AdapterRetrievalHit
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.knowledge_intelligence.binding_match import build_binding_lookup, match_binding_for_hit
from app.knowledge_intelligence.contracts import KnowledgeRetrievalRequest
from app.knowledge_intelligence.fixtures import seed_knowledge_fixtures
from app.knowledge_intelligence.indexing import index_source_revision
from app.knowledge_intelligence.retrieval import retrieve_knowledge
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION
from app.models.curriculum import CurriculumPack, CurriculumVersion
from app.models.knowledge_intelligence import KnowledgeSourceBinding
from app.models.source import Source, SourceRevision


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


def test_curriculum_filter_drops_unrelated_revision() -> None:
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
        pack = CurriculumPack(
            code="ki-pack",
            name="KI Pack",
            country="IN",
            metadata_json={"synthetic_fixture": True},
        )
        session.add(pack)
        session.flush()
        curriculum_version = CurriculumVersion(
            curriculum_pack_id=pack.id,
            version_code="v1",
            metadata_json={"synthetic_fixture": True},
        )
        session.add(curriculum_version)
        session.flush()
        forged_curriculum_id = "forged-curriculum-version"
        result = retrieve_knowledge(
            session,
            adapter,
            KnowledgeRetrievalRequest(
                query_text="quadratic equations",
                curriculum_version_id=forged_curriculum_id,
                top_k=5,
                retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
            ),
        )
        assert result.items == []
        assert any("dropped_unverified_curriculum" in w for w in result.warnings)

        revision = session.get(SourceRevision, fixtures.official_revision_id)
        assert revision is not None
        revision.curriculum_versions.append(curriculum_version)
        session.commit()
        linked = retrieve_knowledge(
            session,
            adapter,
            KnowledgeRetrievalRequest(
                query_text="quadratic equations",
                curriculum_version_id=curriculum_version.id,
                top_k=5,
                retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
            ),
        )
        assert linked.items
        assert linked.items[0].entity_refs.get("curriculum_version_id") == curriculum_version.id


def test_local_grade_filter_drops_metadata_mismatch() -> None:
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
        official_revision = session.get(SourceRevision, fixtures.official_revision_id)
        assert official_revision is not None
        source = session.get(Source, official_revision.source_id)
        assert source is not None
        source.metadata_json = {**source.metadata_json, "grade_year_code": "grade-10"}
        session.commit()
        mismatch = retrieve_knowledge(
            session,
            adapter,
            KnowledgeRetrievalRequest(
                query_text="quadratic equations",
                grade_year_code="grade-9",
                top_k=5,
                retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
            ),
        )
        assert mismatch.items == []
        match = retrieve_knowledge(
            session,
            adapter,
            KnowledgeRetrievalRequest(
                query_text="quadratic equations",
                grade_year_code="grade-10",
                top_k=5,
                retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
            ),
        )
        assert match.items


def test_binding_match_resolves_stable_doc_source_identity() -> None:
    stable_id = f"eduvijna://knowledge/rev-1/ki-v1/{'a' * 64}"
    binding = KnowledgeSourceBinding(
        source_id="source-1",
        source_revision_id="rev-1",
        source_revision_checksum="a" * 64,
        anythingllm_workspace="ws-global",
        anythingllm_document_id="custom-documents/doc-1.txt",
        ownership_scope="global_official",
        index_status="active",
        retrieval_profile_version="ki-v1",
        metadata_json={
            "anythingllm_doc_source_identity": stable_id,
            "anythingllm_remote_location": "custom-documents/doc-1.txt",
            "anythingllm_remote_doc_id": "doc-uuid-1",
        },
    )
    lookup = build_binding_lookup([binding])
    hit = AdapterRetrievalHit(
        workspace_slug="ws-global",
        document_id=stable_id,
        text="evidence",
        score=0.9,
        rank=1,
        metadata={
            "docSource": stable_id,
            "vector_chunk_id": "chunk-uuid",
        },
    )
    assert match_binding_for_hit(hit, lookup) is binding

    orphan_chunk = AdapterRetrievalHit(
        workspace_slug="ws-global",
        document_id="chunk-uuid",
        text="orphan",
        score=0.9,
        rank=1,
        metadata={"docSource": "chunk-uuid"},
    )
    assert match_binding_for_hit(orphan_chunk, lookup) is None

    unknown = AdapterRetrievalHit(
        workspace_slug="ws-global",
        document_id="eduvijna://knowledge/other/ki-v1/" + "b" * 64,
        text="unknown",
        score=0.9,
        rank=1,
        metadata={"docSource": "eduvijna://knowledge/other/ki-v1/" + "b" * 64},
    )
    assert match_binding_for_hit(unknown, lookup) is None


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
