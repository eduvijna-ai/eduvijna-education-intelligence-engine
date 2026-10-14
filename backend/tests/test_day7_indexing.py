from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.adapters.anythingllm.types import AdapterError, AdapterErrorCode
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.knowledge_intelligence.doc_source_identity import build_stable_doc_source_identity
from app.knowledge_intelligence.eligibility import IndexEligibilityError
from app.knowledge_intelligence.fixtures import seed_knowledge_fixtures, staged_revision_for_source
from app.knowledge_intelligence.indexing import (
    index_source_revision,
    list_active_bindings_for_source,
)
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION
from app.models.knowledge_intelligence import KnowledgeSourceBinding
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
        revision = session.get(SourceRevision, fixtures.official_revision_id)
        assert revision is not None
        expected_identity = build_stable_doc_source_identity(
            revision.id,
            DEFAULT_RETRIEVAL_PROFILE_VERSION,
            revision.checksum,
        )
        assert first.metadata_json.get("anythingllm_doc_source_identity") == expected_identity
        assert second.metadata_json.get("anythingllm_doc_source_identity") == expected_identity
        assert first.metadata_json.get("anythingllm_remote_location")
        assert (
            first.metadata_json.get("anythingllm_remote_location")
            == first.anythingllm_document_id
        )


class _FailOnceRetireAdapter(FakeAnythingLLMAdapter):
    def __init__(self) -> None:
        super().__init__()
        self._retire_calls = 0

    def remove_document(self, workspace_slug: str, document_id: str) -> None:
        self._retire_calls += 1
        if self._retire_calls == 1:
            raise AdapterError(
                AdapterErrorCode.UNAVAILABLE,
                "simulated retire failure",
                retryable=True,
            )
        super().remove_document(workspace_slug, document_id)


def _successor_active_revision(
    session: Session,
    revision: SourceRevision,
    text: str,
) -> SourceRevision:
    revision.status = "superseded"
    revision.active_slot = None
    successor = SourceRevision(
        source_id=revision.source_id,
        revision_number=revision.revision_number + 1,
        checksum="e" * 64,
        source_snapshot_checksum="f" * 64,
        ingestion_method="manual",
        content_type="text/plain",
        byte_size=len(text.encode("utf-8")),
        retrieved_at=revision.retrieved_at,
        status="active",
        active_slot=1,
        extraction_status="succeeded",
        extracted_text=text,
        extracted_checksum="e" * 64,
        metadata_json={"synthetic_fixture": True},
    )
    session.add(successor)
    session.flush()
    return successor


def test_supersession_retire_failure_reconciled_on_retry() -> None:
    adapter = _FailOnceRetireAdapter()
    with _session() as session:
        fixtures = seed_knowledge_fixtures(session)
        session.commit()
        first = index_source_revision(
            session,
            adapter,
            fixtures.official_revision_id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        session.commit()
        revision = session.get(SourceRevision, fixtures.official_revision_id)
        assert revision is not None
        successor = _successor_active_revision(
            session,
            revision,
            "SYNTHETIC FIXTURE: successor quadratic content for supersession test.",
        )
        session.commit()
        replacement = index_source_revision(
            session,
            adapter,
            successor.id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        session.commit()
        active = list_active_bindings_for_source(
            session, first.source_id, DEFAULT_RETRIEVAL_PROFILE_VERSION
        )
        assert len(active) == 2

        again = index_source_revision(
            session,
            adapter,
            successor.id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        session.commit()
        assert again.id == replacement.id
        active_after = list_active_bindings_for_source(
            session, first.source_id, DEFAULT_RETRIEVAL_PROFILE_VERSION
        )
        assert len(active_after) == 1
        assert active_after[0].id == replacement.id
        retired = session.get(KnowledgeSourceBinding, first.id)
        assert retired is not None
        assert retired.index_status == "superseded"


class _CountingUploadAdapter(FakeAnythingLLMAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.upload_count = 0
        self.remove_calls: list[tuple[str, str]] = []

    def upload_document(self, workspace_slug, payload, *, idempotency_key):
        self.upload_count += 1
        return super().upload_document(workspace_slug, payload, idempotency_key=idempotency_key)

    def remove_document(self, workspace_slug: str, document_id: str) -> None:
        self.remove_calls.append((workspace_slug, document_id))
        return super().remove_document(workspace_slug, document_id)


class _FailOnceLegacyRetireAdapter(_CountingUploadAdapter):
    def remove_document(self, workspace_slug: str, document_id: str) -> None:
        self.remove_calls.append((workspace_slug, document_id))
        if (
            len(self.remove_calls) == 1
            and workspace_slug == "eduvijna-legacy-profile-agnostic"
        ):
            raise AdapterError(
                AdapterErrorCode.UNAVAILABLE,
                "simulated legacy retire failure",
                retryable=True,
            )
        super().remove_document(workspace_slug, document_id)


class _AlwaysFailLegacyRetireAdapter(_CountingUploadAdapter):
    def remove_document(self, workspace_slug: str, document_id: str) -> None:
        self.remove_calls.append((workspace_slug, document_id))
        if workspace_slug == "eduvijna-legacy-profile-agnostic":
            raise AdapterError(
                AdapterErrorCode.UNAVAILABLE,
                "simulated legacy retire failure",
                retryable=True,
            )
        super().remove_document(workspace_slug, document_id)


def test_legacy_workspace_retire_failure_persists_and_retries_on_idempotent_index() -> None:
    adapter = _FailOnceLegacyRetireAdapter()
    with _session() as session:
        fixtures = seed_knowledge_fixtures(session)
        session.commit()
        binding = index_source_revision(
            session,
            adapter,
            fixtures.official_revision_id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        session.commit()
        legacy_removal_key = binding.anythingllm_document_id
        assert legacy_removal_key
        binding.anythingllm_workspace = "eduvijna-legacy-profile-agnostic"
        session.commit()
        migrated = index_source_revision(
            session,
            adapter,
            fixtures.official_revision_id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        session.commit()
        assert migrated.index_status == "active"
        assert migrated.metadata_json.get("legacy_anythingllm_workspace") == (
            "eduvijna-legacy-profile-agnostic"
        )
        assert migrated.metadata_json.get("legacy_anythingllm_document_id") == legacy_removal_key
        assert migrated.metadata_json.get("legacy_workspace_retire_retryable") is True
        uploads_after_migration = adapter.upload_count

        again = index_source_revision(
            session,
            adapter,
            fixtures.official_revision_id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        session.commit()
        assert again.id == migrated.id
        assert again.index_status == "active"
        assert "legacy_anythingllm_workspace" not in again.metadata_json
        assert adapter.upload_count == uploads_after_migration
        legacy_removes = [
            call
            for call in adapter.remove_calls
            if call == ("eduvijna-legacy-profile-agnostic", legacy_removal_key)
        ]
        assert len(legacy_removes) >= 2


def test_legacy_workspace_retire_repeated_failure_keeps_retry_state() -> None:
    adapter = _AlwaysFailLegacyRetireAdapter()
    with _session() as session:
        fixtures = seed_knowledge_fixtures(session)
        session.commit()
        binding = index_source_revision(
            session,
            adapter,
            fixtures.official_revision_id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        session.commit()
        legacy_removal_key = binding.anythingllm_document_id
        binding.anythingllm_workspace = "eduvijna-legacy-profile-agnostic"
        session.commit()
        index_source_revision(
            session,
            adapter,
            fixtures.official_revision_id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        session.commit()
        uploads_after_migration = adapter.upload_count
        for _ in range(2):
            again = index_source_revision(
                session,
                adapter,
                fixtures.official_revision_id,
                retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
            )
            session.commit()
            assert again.index_status == "active"
            assert again.metadata_json.get("legacy_workspace_retire_retryable") is True
        assert adapter.upload_count == uploads_after_migration
        assert legacy_removal_key
        assert adapter.remove_calls.count(
            ("eduvijna-legacy-profile-agnostic", legacy_removal_key)
        ) >= 3


def test_legacy_workspace_is_migrated_on_reindex() -> None:
    adapter = FakeAnythingLLMAdapter()
    with _session() as session:
        fixtures = seed_knowledge_fixtures(session)
        session.commit()
        binding = index_source_revision(
            session,
            adapter,
            fixtures.official_revision_id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        session.commit()
        expected_workspace = binding.anythingllm_workspace
        binding.anythingllm_workspace = "eduvijna-legacy-profile-agnostic"
        session.commit()
        rebound = index_source_revision(
            session,
            adapter,
            fixtures.official_revision_id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        session.commit()
        assert rebound.id == binding.id
        assert rebound.anythingllm_workspace == expected_workspace
        assert rebound.index_status == "active"


def test_dual_retrieval_profiles_remain_active_independently() -> None:
    adapter = FakeAnythingLLMAdapter()
    with _session() as session:
        fixtures = seed_knowledge_fixtures(session)
        session.commit()
        v1 = index_source_revision(
            session,
            adapter,
            fixtures.official_revision_id,
            retrieval_profile_version="ki-retrieval-v1",
        )
        v0 = index_source_revision(
            session,
            adapter,
            fixtures.official_revision_id,
            retrieval_profile_version="ki-retrieval-v0",
        )
        session.commit()
        assert v1.index_status == "active"
        assert v0.index_status == "active"
        assert v1.id != v0.id
        active_v1 = list_active_bindings_for_source(
            session, v1.source_id, "ki-retrieval-v1"
        )
        active_v0 = list_active_bindings_for_source(
            session, v0.source_id, "ki-retrieval-v0"
        )
        assert len(active_v1) == 1
        assert len(active_v0) == 1
        assert v1.anythingllm_workspace != v0.anythingllm_workspace


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
