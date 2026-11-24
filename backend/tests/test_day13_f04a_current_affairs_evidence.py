"""F04-A: CLAT current affairs evidence preflight (read-only, fail-closed)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.cuet_clat.clat_current_affairs_evidence import (
    F04A_DEFAULT_RETRIEVAL_PROFILE,
    evaluate_clat_current_affairs_evidence,
    seed_f04a_synthetic_current_affairs_fixture,
)
from app.cuet_clat.clat_evidence_contracts import (
    CLAT_CA_SECTION_CODE,
    ClatCurrentAffairsPreflightRequest,
    ClatEvidenceIssueCode,
    ClatEvidenceOperatingMode,
    ClatEvidencePreflightVerdict,
    build_claim_evidence_binding_hash,
)
from app.cuet_clat.constants import CLAT_PACK_CODE, CUET_PACK_CODE
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.knowledge_intelligence.contracts import KnowledgeEvidenceItem
from app.models.enums import SourceRevisionStatus, SourceTrustTier, SourceType
from app.models.knowledge_intelligence import KnowledgeSourceBinding
from app.models.source import (
    Source,
    SourceAuditEvent,
    SourceRevision,
    exam_version_source_revisions,
)


@contextmanager
def _session():
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        yield session


def _request(
    *,
    mode: ClatEvidenceOperatingMode,
    claim: str,
    fact_date: date | None,
    as_of: datetime,
    exam_version_id: str | None = None,
    organization_id: str | None = None,
    institution_id: str | None = None,
    exam_pack_code: str = CLAT_PACK_CODE,
    exam_family: str = "clat_ug",
    expected_binding: str | None = None,
) -> ClatCurrentAffairsPreflightRequest:
    return ClatCurrentAffairsPreflightRequest(
        exam_family=exam_family,
        exam_pack_code=exam_pack_code,
        academic_year="2027",
        section_code=CLAT_CA_SECTION_CODE,
        operating_mode=mode,
        claim_text=claim,
        fact_date=fact_date,
        as_of=as_of,
        organization_id=organization_id,
        institution_id=institution_id,
        exam_version_id=exam_version_id,
        retrieval_profile_version=F04A_DEFAULT_RETRIEVAL_PROFILE,
        expected_claim_binding_hash=expected_binding,
    )


def test_no_evidence_official_fail_closed() -> None:
    as_of = datetime(2026, 11, 1, tzinfo=UTC)
    with _session() as session:
        decision = evaluate_clat_current_affairs_evidence(
            session,
            _request(
                mode=ClatEvidenceOperatingMode.OFFICIAL_CLAT_2027,
                claim="Any claim",
                fact_date=date(2026, 10, 1),
                as_of=as_of,
            ),
            evidence_items=[],
        )
        assert decision.verdict == ClatEvidencePreflightVerdict.SOURCE_PENDING
        assert decision.officially_verified_claim_count == 0
        assert ClatEvidenceIssueCode.NO_EVIDENCE in decision.issue_codes


def test_synthetic_mechanical_demo_positive() -> None:
    as_of = datetime(2026, 11, 1, tzinfo=UTC)
    fact = date(2026, 10, 15)
    with _session() as session:
        fixture = seed_f04a_synthetic_current_affairs_fixture(session)
        session.commit()
        audits_before = session.scalar(select(func.count()).select_from(SourceAuditEvent))

        decision = evaluate_clat_current_affairs_evidence(
            session,
            _request(
                mode=ClatEvidenceOperatingMode.SYNTHETIC_TEST_ONLY,
                claim=fixture.claim_text,
                fact_date=fact,
                as_of=as_of,
                exam_version_id=fixture.exam_version_id,
                organization_id=fixture.organization_id,
                institution_id=fixture.institution_id,
            ),
            evidence_items=[fixture.evidence_item],
        )
        audits_after = session.scalar(select(func.count()).select_from(SourceAuditEvent))
        assert audits_before == audits_after

        assert decision.verdict == ClatEvidencePreflightVerdict.MECHANICAL_DEMO_OK
        assert decision.mechanical_evidence_checks_ok is True
        assert decision.official_source_approved is False
        assert decision.factual_claim_independently_verified is False
        assert decision.officially_verified_claim_count == 0
        assert decision.eligible_test_evidence_count == 1
        assert decision.claim_binding_hash


def test_official_mode_always_pending_even_with_rows() -> None:
    as_of = datetime(2026, 11, 1, tzinfo=UTC)
    with _session() as session:
        fixture = seed_f04a_synthetic_current_affairs_fixture(session)
        session.commit()
        decision = evaluate_clat_current_affairs_evidence(
            session,
            _request(
                mode=ClatEvidenceOperatingMode.OFFICIAL_CLAT_2027,
                claim=fixture.claim_text,
                fact_date=date(2026, 10, 15),
                as_of=as_of,
                exam_version_id=fixture.exam_version_id,
                organization_id=fixture.organization_id,
                institution_id=fixture.institution_id,
            ),
            evidence_items=[fixture.evidence_item],
        )
        assert decision.verdict == ClatEvidencePreflightVerdict.SOURCE_PENDING
        assert decision.officially_verified_claim_count == 0
        assert decision.mechanical_evidence_checks_ok is False


def test_manifest_url_without_approved_bytes() -> None:
    as_of = datetime(2026, 11, 1, tzinfo=UTC)
    with _session() as session:
        source = Source(
            source_type=SourceType.OFFICIAL_EXAM_BULLETIN.value,
            title="CLAT manifest discovery URL only",
            url="https://consortiumofnlus.ac.in/sample",
            trust_tier=SourceTrustTier.OFFICIAL_PRIMARY.value,
            status="staged",
            board_or_exam="clat_ug",
            academic_year="2027",
            metadata_json={"d13_manifest_discovery_only": True},
        )
        session.add(source)
        session.flush()
        item = KnowledgeEvidenceItem(
            source_id=str(source.id),
            source_revision_id="missing-revision",
            source_revision_checksum="a" * 64,
            binding_id="missing-binding",
            trust_tier=source.trust_tier,
            authority_label="manifest",
            title=source.title,
            locator="url",
            snippet="headline text",
            retrieval_score=0.5,
            retrieval_rank=1,
            anythingllm_workspace="ws",
            anythingllm_document_id="doc",
            citation_label="[manifest]",
        )
        session.commit()
        decision = evaluate_clat_current_affairs_evidence(
            session,
            _request(
                mode=ClatEvidenceOperatingMode.OFFICIAL_CLAT_2027,
                claim="headline text",
                fact_date=date(2026, 9, 1),
                as_of=as_of,
            ),
            evidence_items=[item],
        )
        assert decision.officially_verified_claim_count == 0
        assert decision.verdict == ClatEvidencePreflightVerdict.SOURCE_PENDING


def test_sample_paper_denied_for_official() -> None:
    as_of = datetime(2026, 11, 1, tzinfo=UTC)
    with _session() as session:
        source = Source(
            source_type=SourceType.SAMPLE_PAPER.value,
            title="Analytical sample",
            trust_tier=SourceTrustTier.ANALYTICAL.value,
            status="active",
            board_or_exam="clat_ug",
            academic_year="2027",
            metadata_json={"human_curator_approval": False},
        )
        session.add(source)
        session.flush()
        revision = SourceRevision(
            source_id=source.id,
            revision_number=1,
            checksum="b" * 64,
            source_snapshot_checksum="c" * 64,
            content_type="text/plain",
            byte_size=12,
            retrieved_at=as_of,
            status=SourceRevisionStatus.ACTIVE.value,
            active_slot=1,
        )
        session.add(revision)
        session.flush()
        binding = KnowledgeSourceBinding(
            source_id=str(source.id),
            source_revision_id=str(revision.id),
            source_revision_checksum=revision.checksum,
            anythingllm_workspace="ws",
            anythingllm_document_id="doc",
            ownership_scope="global_official",
            index_status="active",
            retrieval_profile_version=F04A_DEFAULT_RETRIEVAL_PROFILE,
        )
        session.add(binding)
        session.flush()
        item = KnowledgeEvidenceItem(
            source_id=str(source.id),
            source_revision_id=str(revision.id),
            source_revision_checksum=revision.checksum,
            binding_id=str(binding.id),
            trust_tier=source.trust_tier,
            authority_label="sample",
            title=source.title,
            locator="p1",
            snippet="sample paper headline content",
            retrieval_score=0.1,
            retrieval_rank=1,
            anythingllm_workspace="ws",
            anythingllm_document_id="doc",
            citation_label="[sample]",
        )
        session.commit()
        decision = evaluate_clat_current_affairs_evidence(
            session,
            _request(
                mode=ClatEvidenceOperatingMode.OFFICIAL_CLAT_2027,
                claim="sample paper headline",
                fact_date=date(2026, 8, 1),
                as_of=as_of,
            ),
            evidence_items=[item],
        )
        assert ClatEvidenceIssueCode.NON_OFFICIAL_FOR_OFFICIAL_MODE in decision.issue_codes
        assert decision.officially_verified_claim_count == 0


@pytest.mark.parametrize(
    "mutator,expected_issue",
    [
        ("checksum", ClatEvidenceIssueCode.CHECKSUM_MISMATCH),
        ("locator", ClatEvidenceIssueCode.FORGED_CITATION),
        ("stale_date", ClatEvidenceIssueCode.FACT_DATE_STALE),
        ("future_date", ClatEvidenceIssueCode.FACT_DATE_FUTURE),
        ("undated", ClatEvidenceIssueCode.FACT_DATE_MISSING),
        ("snippet", ClatEvidenceIssueCode.UNTRUSTED_RETRIEVAL_ONLY),
        ("tenant", ClatEvidenceIssueCode.TENANT_MISMATCH),
        ("cuet_pack", ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH),
    ],
)
def test_falsification_refuses(mutator: str, expected_issue: ClatEvidenceIssueCode) -> None:
    as_of = datetime(2026, 11, 1, tzinfo=UTC)
    fact = date(2026, 10, 15)
    with _session() as session:
        fixture = seed_f04a_synthetic_current_affairs_fixture(session)
        session.commit()
        item = fixture.evidence_item.model_copy(deep=True)
        req = _request(
            mode=ClatEvidenceOperatingMode.SYNTHETIC_TEST_ONLY,
            claim=fixture.claim_text,
            fact_date=fact,
            as_of=as_of,
            exam_version_id=fixture.exam_version_id,
            organization_id=fixture.organization_id,
            institution_id=fixture.institution_id,
        )
        if mutator == "checksum":
            item = item.model_copy(update={"source_revision_checksum": "z" * 64})
        elif mutator == "locator":
            item = item.model_copy(update={"anythingllm_document_id": "forged-doc"})
        elif mutator == "stale_date":
            req = req.model_copy(update={"fact_date": date(2020, 1, 1)})
        elif mutator == "future_date":
            req = req.model_copy(update={"fact_date": date(2027, 1, 1)})
        elif mutator == "undated":
            req = req.model_copy(update={"fact_date": None})
        elif mutator == "snippet":
            item = item.model_copy(update={"snippet": "unrelated market indices moved today"})
        elif mutator == "tenant":
            req = req.model_copy(update={"organization_id": "foreign-org"})
        elif mutator == "cuet_pack":
            req = req.model_copy(
                update={"exam_pack_code": CUET_PACK_CODE, "exam_family": "cuet_ug"}
            )

        decision = evaluate_clat_current_affairs_evidence(session, req, evidence_items=[item])
        assert expected_issue in decision.issue_codes
        assert decision.eligible_test_evidence_count == 0


def test_claim_binding_hash_stable_and_invalidates() -> None:
    as_of = datetime(2026, 11, 1, tzinfo=UTC)
    with _session() as session:
        fixture = seed_f04a_synthetic_current_affairs_fixture(session)
        session.commit()
        binding = build_claim_evidence_binding_hash(
            claim_text=fixture.claim_text,
            source_id=fixture.source_id,
            source_revision_id=fixture.revision_id,
            source_revision_checksum=fixture.evidence_item.source_revision_checksum,
            locator=fixture.evidence_item.locator,
            document_id=fixture.evidence_item.anythingllm_document_id,
            fact_date=date(2026, 10, 15),
            retrieval_profile_version=F04A_DEFAULT_RETRIEVAL_PROFILE,
            exam_pack_code=CLAT_PACK_CODE,
            academic_year="2027",
            section_code=CLAT_CA_SECTION_CODE,
        )
        ok = evaluate_clat_current_affairs_evidence(
            session,
            _request(
                mode=ClatEvidenceOperatingMode.SYNTHETIC_TEST_ONLY,
                claim=fixture.claim_text,
                fact_date=date(2026, 10, 15),
                as_of=as_of,
                exam_version_id=fixture.exam_version_id,
                organization_id=fixture.organization_id,
                institution_id=fixture.institution_id,
                expected_binding=binding,
            ),
            evidence_items=[fixture.evidence_item],
        )
        assert ok.verdict == ClatEvidencePreflightVerdict.MECHANICAL_DEMO_OK

        stale = evaluate_clat_current_affairs_evidence(
            session,
            _request(
                mode=ClatEvidenceOperatingMode.SYNTHETIC_TEST_ONLY,
                claim=fixture.claim_text,
                fact_date=date(2026, 10, 15),
                as_of=as_of,
                exam_version_id=fixture.exam_version_id,
                organization_id=fixture.organization_id,
                institution_id=fixture.institution_id,
                expected_binding="deadbeef" * 5,
            ),
            evidence_items=[fixture.evidence_item],
        )
        assert ClatEvidenceIssueCode.CLAIM_BINDING_STALE in stale.issue_codes


def test_exam_version_unassociated_foreign_revision() -> None:
    as_of = datetime(2026, 11, 1, tzinfo=UTC)
    with _session() as session:
        fixture = seed_f04a_synthetic_current_affairs_fixture(session)
        session.execute(
            exam_version_source_revisions.delete().where(
                exam_version_source_revisions.c.source_revision_id == fixture.revision_id
            )
        )
        session.commit()
        decision = evaluate_clat_current_affairs_evidence(
            session,
            _request(
                mode=ClatEvidenceOperatingMode.SYNTHETIC_TEST_ONLY,
                claim=fixture.claim_text,
                fact_date=date(2026, 10, 15),
                as_of=as_of,
                exam_version_id=fixture.exam_version_id,
                organization_id=fixture.organization_id,
                institution_id=fixture.institution_id,
            ),
            evidence_items=[fixture.evidence_item],
        )
        assert ClatEvidenceIssueCode.EXAM_VERSION_UNASSOCIATED in decision.issue_codes


def test_fake_curator_founder_string_not_official() -> None:
    as_of = datetime(2026, 11, 1, tzinfo=UTC)
    with _session() as session:
        source = Source(
            source_type=SourceType.OFFICIAL_EXAM_BULLETIN.value,
            title="Fake approved CLAT bulletin",
            trust_tier=SourceTrustTier.OFFICIAL_PRIMARY.value,
            status="active",
            board_or_exam="clat_ug",
            academic_year="2027",
            metadata_json={
                "human_curator_approval": True,
                "human_rights_disposition": "approved",
                "rights_review_status": "APPROVED",
            },
        )
        session.add(source)
        session.flush()
        revision = SourceRevision(
            source_id=source.id,
            revision_number=1,
            checksum="d" * 64,
            source_snapshot_checksum="e" * 64,
            content_type="application/pdf",
            byte_size=128,
            retrieved_at=as_of,
            status=SourceRevisionStatus.ACTIVE.value,
            active_slot=1,
            approved_by="founder",
            approval_fingerprint="f" * 64,
        )
        session.add(revision)
        session.flush()
        session.add(
            SourceAuditEvent(
                source_id=source.id,
                source_revision_id=revision.id,
                event_type="source_approved",
                outcome="success",
                actor_id="founder",
            )
        )
        binding = KnowledgeSourceBinding(
            source_id=str(source.id),
            source_revision_id=str(revision.id),
            source_revision_checksum=revision.checksum,
            anythingllm_workspace="ws-official",
            anythingllm_document_id="official-doc",
            ownership_scope="global_official",
            index_status="active",
            retrieval_profile_version=F04A_DEFAULT_RETRIEVAL_PROFILE,
            metadata_json={"anythingllm_doc_source_identity": "official-doc"},
        )
        session.add(binding)
        session.flush()
        item = KnowledgeEvidenceItem(
            source_id=str(source.id),
            source_revision_id=str(revision.id),
            source_revision_checksum=revision.checksum,
            binding_id=str(binding.id),
            trust_tier=source.trust_tier,
            authority_label="consortium",
            title=source.title,
            locator="bulletin/2027",
            snippet="consortium headline bulletin content",
            retrieval_score=0.9,
            retrieval_rank=1,
            anythingllm_workspace="ws-official",
            anythingllm_document_id="official-doc",
            citation_label="[official]",
        )
        session.commit()
        decision = evaluate_clat_current_affairs_evidence(
            session,
            _request(
                mode=ClatEvidenceOperatingMode.OFFICIAL_CLAT_2027,
                claim="consortium headline",
                fact_date=date(2026, 10, 1),
                as_of=as_of,
            ),
            evidence_items=[item],
        )
        assert ClatEvidenceIssueCode.CURATOR_NOT_APPROVED in decision.issue_codes
        assert decision.officially_verified_claim_count == 0