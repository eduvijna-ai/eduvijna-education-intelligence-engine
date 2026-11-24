"""F04-A: read-only CLAT current affairs evidence preflight (no ingestion or issuance)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cuet_clat.clat_evidence_contracts import (
    CLAT_CA_SECTION_CODE,
    SYNTHETIC_CA_FIXTURE_METADATA_KEY,
    ClatCurrentAffairsEvidenceDecision,
    ClatCurrentAffairsPreflightRequest,
    ClatEvidenceIssueCode,
    ClatEvidenceOperatingMode,
    ClatEvidencePreflightVerdict,
    build_claim_evidence_binding_hash,
)
from app.cuet_clat.constants import CLAT_PACK_CODE
from app.cuet_clat.exam_profile import ensure_synthetic_demo_versions
from app.cuet_clat.source_registry import build_source_manifest, clat_official_evidence_ready
from app.knowledge_intelligence.contracts import KnowledgeContextPack, KnowledgeEvidenceItem
from app.models.enums import SourceRevisionStatus, SourceTrustTier, SourceType
from app.models.examination import ExamPack, ExamVersion
from app.models.knowledge_intelligence import KnowledgeSourceBinding
from app.models.source import (
    Source,
    SourceAuditEvent,
    SourceRevision,
    exam_version_source_revisions,
)

F04A_SYNTHETIC_CA_BYTES = b"eduvijna-d13-f04a-clat-ca-synthetic-fixture-v1\n"
F04A_SYNTHETIC_CA_CHECKSUM = hashlib.sha256(F04A_SYNTHETIC_CA_BYTES).hexdigest()
F04A_DEFAULT_RETRIEVAL_PROFILE = "d13-f04a-test-profile@v1"
F04A_SYNTHETIC_WORKSPACE = "d13-f04a-synthetic-ca-ws"
_MANIFEST_DISCOVERY_KEY = "d13_manifest_discovery_only"


def _issue_set(codes: list[ClatEvidenceIssueCode]) -> list[ClatEvidenceIssueCode]:
    seen: set[str] = set()
    ordered: list[ClatEvidenceIssueCode] = []
    for code in codes:
        if code.value not in seen:
            seen.add(code.value)
            ordered.append(code)
    return ordered


def _fail_decision(
    request: ClatCurrentAffairsPreflightRequest,
    *,
    verdict: ClatEvidencePreflightVerdict,
    issues: list[ClatEvidenceIssueCode],
    metadata: dict[str, object] | None = None,
) -> ClatCurrentAffairsEvidenceDecision:
    return ClatCurrentAffairsEvidenceDecision(
        verdict=verdict,
        operating_mode=request.operating_mode,
        issue_codes=_issue_set(issues),
        eligible_test_evidence_count=0,
        officially_verified_claim_count=0,
        mechanical_evidence_checks_ok=False,
        factual_claim_independently_verified=False,
        official_source_approved=False,
        metadata_json=metadata or {},
    )


def _normalize_exam_family(exam_family: str) -> str:
    return exam_family.strip().lower().replace("-", "_")


def _validate_request_scope(
    session: Session, request: ClatCurrentAffairsPreflightRequest
) -> tuple[list[ClatEvidenceIssueCode], str | None]:
    issues: list[ClatEvidenceIssueCode] = []
    exam_version_id = request.exam_version_id

    family = _normalize_exam_family(request.exam_family)
    if family != "clat_ug":
        issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
    if request.exam_pack_code != CLAT_PACK_CODE:
        issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
    if request.academic_year != "2027":
        issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
    if request.section_code != CLAT_CA_SECTION_CODE:
        issues.append(ClatEvidenceIssueCode.SECTION_UNSUPPORTED)

    if exam_version_id:
        version = session.get(ExamVersion, exam_version_id)
        if version is None:
            issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
        else:
            pack = session.get(ExamPack, version.exam_pack_id)
            if pack is None or pack.code != CLAT_PACK_CODE:
                issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
            if version.academic_year != "2027":
                issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
            if pack is not None:
                pack_meta = (pack.metadata_json or {}).get("examination_family")
                if str(pack_meta or "") not in {"clat_ug", ""}:
                    issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
    return issues, exam_version_id


def _revision_linked_to_exam(session: Session, revision_id: str, exam_version_id: str) -> bool:
    revision = session.get(SourceRevision, revision_id)
    if revision is None:
        return False
    if any(str(ev.id) == exam_version_id for ev in revision.exam_versions):
        return True
    row = session.execute(
        select(exam_version_source_revisions.c.exam_version_id).where(
            exam_version_source_revisions.c.source_revision_id == revision_id,
            exam_version_source_revisions.c.exam_version_id == exam_version_id,
        )
    ).first()
    return row is not None


def _rights_and_curator_ok_for_official(
    session: Session, source: Source, revision: SourceRevision
) -> list[ClatEvidenceIssueCode]:
    issues: list[ClatEvidenceIssueCode] = []
    meta = dict(source.metadata_json or {})
    rev_meta = dict(revision.metadata_json or {})

    synth_marker = SYNTHETIC_CA_FIXTURE_METADATA_KEY
    if meta.get(synth_marker) or rev_meta.get(synth_marker):
        issues.append(ClatEvidenceIssueCode.SYNTHETIC_FOR_OFFICIAL_MODE)
    if meta.get(_MANIFEST_DISCOVERY_KEY):
        issues.append(ClatEvidenceIssueCode.MANIFEST_ONLY)
    if source.trust_tier != SourceTrustTier.OFFICIAL_PRIMARY.value:
        issues.append(ClatEvidenceIssueCode.UNAPPROVED_TRUST_TIER)
    if source.source_type in {
        SourceType.SAMPLE_PAPER.value,
        SourceType.COMPETITIVE_ANALYSIS.value,
    }:
        issues.append(ClatEvidenceIssueCode.NON_OFFICIAL_FOR_OFFICIAL_MODE)

    rights_status = str(meta.get("rights_review_status") or "").upper()
    if rights_status in {"", "PENDING", "RIGHTS_REVIEW_PENDING"}:
        issues.append(ClatEvidenceIssueCode.RIGHTS_NOT_APPROVED)
    disposition = str(meta.get("human_rights_disposition") or "").strip()
    if not disposition:
        issues.append(ClatEvidenceIssueCode.RIGHTS_NOT_APPROVED)

    if not bool(meta.get("human_curator_approval")):
        issues.append(ClatEvidenceIssueCode.CURATOR_NOT_APPROVED)

    approve_event = session.scalar(
        select(SourceAuditEvent)
        .where(
            SourceAuditEvent.source_revision_id == revision.id,
            SourceAuditEvent.event_type == "source_approved",
            SourceAuditEvent.outcome == "success",
        )
        .order_by(SourceAuditEvent.created_at.desc())
    )
    if approve_event is None:
        issues.append(ClatEvidenceIssueCode.CURATOR_NOT_APPROVED)
    else:
        approver = (revision.approved_by or "").strip()
        if approver.lower() in {"founder", "founder-curator", ""}:
            issues.append(ClatEvidenceIssueCode.CURATOR_NOT_APPROVED)

    if revision.approval_fingerprint in {None, ""}:
        issues.append(ClatEvidenceIssueCode.RIGHTS_NOT_APPROVED)

    return issues


def _document_identity_matches(
    item: KnowledgeEvidenceItem,
    binding: KnowledgeSourceBinding,
) -> bool:
    binding_meta = dict(binding.metadata_json or {})
    stable = str(binding_meta.get("anythingllm_doc_source_identity") or "").strip()
    doc_id = (binding.anythingllm_document_id or "").strip()
    item_doc = (item.anythingllm_document_id or "").strip()
    if stable and item_doc == stable:
        return True
    if doc_id and item_doc == doc_id:
        return True
    if item_doc and item_doc == stable:
        return True
    return False


def _claim_snippet_linked(claim_text: str, snippet: str) -> bool:
    claim_tokens = [t for t in claim_text.lower().split() if len(t) > 4]
    if not claim_tokens:
        return True
    snippet_l = snippet.lower()
    hits = sum(1 for t in claim_tokens if t in snippet_l)
    return hits >= max(1, len(claim_tokens) // 2)


def _validate_fact_date(
    request: ClatCurrentAffairsPreflightRequest,
) -> list[ClatEvidenceIssueCode]:
    issues: list[ClatEvidenceIssueCode] = []
    if request.fact_date is None:
        issues.append(ClatEvidenceIssueCode.FACT_DATE_MISSING)
        return issues
    as_of_date = request.as_of.astimezone(UTC).date()
    if request.fact_date > as_of_date:
        issues.append(ClatEvidenceIssueCode.FACT_DATE_FUTURE)
    age_days = (as_of_date - request.fact_date).days
    if age_days > request.freshness_policy.max_age_days:
        issues.append(ClatEvidenceIssueCode.FACT_DATE_STALE)
    return issues


def _synthetic_fixture_source(source: Source) -> bool:
    meta = dict(source.metadata_json or {})
    return bool(meta.get(SYNTHETIC_CA_FIXTURE_METADATA_KEY))


def _evaluate_evidence_item(
    session: Session,
    request: ClatCurrentAffairsPreflightRequest,
    item: KnowledgeEvidenceItem,
    *,
    exam_version_id: str | None,
) -> tuple[list[ClatEvidenceIssueCode], str | None, bool]:
    """Returns issues, binding hash if mechanically linkable, mechanical_ok for this item."""

    issues: list[ClatEvidenceIssueCode] = []
    source = session.get(Source, item.source_id)
    if source is None:
        issues.append(ClatEvidenceIssueCode.MISSING_SOURCE)
        return issues, None, False

    revision = session.get(SourceRevision, item.source_revision_id)
    if revision is None:
        issues.append(ClatEvidenceIssueCode.MISSING_REVISION)
        return issues, None, False

    if revision.source_id != source.id:
        issues.append(ClatEvidenceIssueCode.FORGED_CITATION)

    if revision.status != SourceRevisionStatus.ACTIVE.value:
        issues.append(ClatEvidenceIssueCode.REVISION_NOT_ACTIVE)

    if revision.checksum != item.source_revision_checksum:
        issues.append(ClatEvidenceIssueCode.CHECKSUM_MISMATCH)

    binding = session.scalar(
        select(KnowledgeSourceBinding).where(KnowledgeSourceBinding.id == item.binding_id)
    )
    if binding is None:
        issues.append(ClatEvidenceIssueCode.BINDING_MISSING)
    else:
        if binding.index_status != "active":
            issues.append(ClatEvidenceIssueCode.BINDING_INACTIVE)
        if binding.source_revision_id != revision.id or binding.source_id != source.id:
            issues.append(ClatEvidenceIssueCode.BINDING_IDENTITY_MISMATCH)
        if binding.source_revision_checksum != revision.checksum:
            issues.append(ClatEvidenceIssueCode.CHECKSUM_MISMATCH)
        if binding.retrieval_profile_version != request.retrieval_profile_version:
            issues.append(ClatEvidenceIssueCode.BINDING_IDENTITY_MISMATCH)
        if item.anythingllm_workspace != binding.anythingllm_workspace:
            issues.append(ClatEvidenceIssueCode.FORGED_CITATION)
        if not _document_identity_matches(item, binding):
            issues.append(ClatEvidenceIssueCode.FORGED_CITATION)

    if request.organization_id and source.organization_id not in {None, request.organization_id}:
        issues.append(ClatEvidenceIssueCode.TENANT_MISMATCH)
    if request.institution_id and source.institution_id not in {None, request.institution_id}:
        issues.append(ClatEvidenceIssueCode.TENANT_MISMATCH)

    if (source.board_or_exam or "").lower() not in {"", "clat_ug", "clat"}:
        if request.operating_mode == ClatEvidenceOperatingMode.OFFICIAL_CLAT_2027:
            issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
    if source.academic_year not in {None, "2027"}:
        issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)

    if exam_version_id and not _revision_linked_to_exam(session, str(revision.id), exam_version_id):
        issues.append(ClatEvidenceIssueCode.EXAM_VERSION_UNASSOCIATED)

    issues.extend(_validate_fact_date(request))

    if not _claim_snippet_linked(request.claim_text, item.snippet):
        issues.append(ClatEvidenceIssueCode.UNTRUSTED_RETRIEVAL_ONLY)

    if request.operating_mode == ClatEvidenceOperatingMode.OFFICIAL_CLAT_2027:
        issues.extend(_rights_and_curator_ok_for_official(session, source, revision))
        if _synthetic_fixture_source(source):
            issues.append(ClatEvidenceIssueCode.SYNTHETIC_FOR_OFFICIAL_MODE)
    else:
        if not _synthetic_fixture_source(source):
            issues.append(ClatEvidenceIssueCode.NON_OFFICIAL_FOR_OFFICIAL_MODE)
        if source.source_type not in {
            SourceType.INSTITUTION_CONTENT.value,
            SourceType.TEACHER_CONTENT.value,
        }:
            issues.append(ClatEvidenceIssueCode.NON_OFFICIAL_FOR_OFFICIAL_MODE)
        if source.trust_tier == SourceTrustTier.OFFICIAL_PRIMARY.value:
            issues.append(ClatEvidenceIssueCode.UNAPPROVED_TRUST_TIER)

    binding_hash = build_claim_evidence_binding_hash(
        claim_text=request.claim_text,
        source_id=str(source.id),
        source_revision_id=str(revision.id),
        source_revision_checksum=revision.checksum,
        locator=item.locator,
        document_id=item.anythingllm_document_id,
        fact_date=request.fact_date,
        retrieval_profile_version=request.retrieval_profile_version,
        exam_pack_code=request.exam_pack_code,
        academic_year=request.academic_year,
        section_code=request.section_code,
    )

    if request.expected_claim_binding_hash and request.expected_claim_binding_hash != binding_hash:
        issues.append(ClatEvidenceIssueCode.CLAIM_BINDING_STALE)

    mechanical_ok = not issues
    return issues, binding_hash, mechanical_ok


def evaluate_clat_current_affairs_evidence(
    session: Session,
    request: ClatCurrentAffairsPreflightRequest,
    *,
    evidence_items: list[KnowledgeEvidenceItem] | None = None,
    context_pack: KnowledgeContextPack | None = None,
) -> ClatCurrentAffairsEvidenceDecision:
    """Read-only fail-closed preflight; never writes audits or activates sources."""

    items: list[KnowledgeEvidenceItem] = list(evidence_items or [])
    if context_pack is not None:
        items.extend(context_pack.evidence)

    scope_issues, exam_version_id = _validate_request_scope(session, request)
    if scope_issues:
        return _fail_decision(
            request,
            verdict=ClatEvidencePreflightVerdict.FAIL,
            issues=scope_issues,
            metadata={"scope_blocked": True},
        )

    global_issues: list[ClatEvidenceIssueCode] = []
    if not items:
        global_issues.append(ClatEvidenceIssueCode.NO_EVIDENCE)
        verdict = ClatEvidencePreflightVerdict.SOURCE_PENDING
        if request.operating_mode == ClatEvidenceOperatingMode.SYNTHETIC_TEST_ONLY:
            verdict = ClatEvidencePreflightVerdict.SOURCE_PENDING
        return _fail_decision(request, verdict=verdict, issues=global_issues)

    if request.operating_mode == ClatEvidenceOperatingMode.OFFICIAL_CLAT_2027:
        if not clat_official_evidence_ready(session):
            global_issues.append(ClatEvidenceIssueCode.RIGHTS_NOT_APPROVED)

    per_item_issues: list[ClatEvidenceIssueCode] = []
    mechanical_hashes: dict[str, str] = {}
    mechanical_count = 0
    for item in items:
        item_issues, binding_hash, mechanical_ok = _evaluate_evidence_item(
            session,
            request,
            item,
            exam_version_id=exam_version_id,
        )
        per_item_issues.extend(item_issues)
        if binding_hash:
            prior = mechanical_hashes.get(binding_hash)
            if prior is not None and prior != item.source_revision_id:
                per_item_issues.append(ClatEvidenceIssueCode.CONFLICTING_REVISION)
            mechanical_hashes.setdefault(binding_hash, item.source_revision_id)
        if (
            mechanical_ok
            and request.operating_mode == ClatEvidenceOperatingMode.SYNTHETIC_TEST_ONLY
        ):
            mechanical_count += 1

    all_issues = _issue_set(global_issues + per_item_issues)

    if request.operating_mode == ClatEvidenceOperatingMode.OFFICIAL_CLAT_2027:
        return ClatCurrentAffairsEvidenceDecision(
            verdict=ClatEvidencePreflightVerdict.SOURCE_PENDING,
            operating_mode=request.operating_mode,
            issue_codes=all_issues,
            eligible_test_evidence_count=0,
            officially_verified_claim_count=0,
            mechanical_evidence_checks_ok=False,
            factual_claim_independently_verified=False,
            official_source_approved=False,
            metadata_json={
                "mechanical_evidence_checks_ok": False,
                "factual_claim_independently_verified": False,
                "official_source_approved": False,
                "manifest_entry_count": len(build_source_manifest()),
            },
        )

    if all_issues or mechanical_count < 1:
        verdict = (
            ClatEvidencePreflightVerdict.SOURCE_PENDING
            if ClatEvidenceIssueCode.NO_EVIDENCE in all_issues
            else ClatEvidencePreflightVerdict.FAIL
        )
        return ClatCurrentAffairsEvidenceDecision(
            verdict=verdict,
            operating_mode=request.operating_mode,
            issue_codes=all_issues,
            eligible_test_evidence_count=0,
            officially_verified_claim_count=0,
            mechanical_evidence_checks_ok=False,
            factual_claim_independently_verified=False,
            official_source_approved=False,
            claim_binding_hash="",
            metadata_json={"synthetic_test_only": True},
        )

    _, binding_hash, _ = _evaluate_evidence_item(
        session,
        request,
        items[0],
        exam_version_id=exam_version_id,
    )

    return ClatCurrentAffairsEvidenceDecision(
        verdict=ClatEvidencePreflightVerdict.MECHANICAL_DEMO_OK,
        operating_mode=request.operating_mode,
        issue_codes=[],
        eligible_test_evidence_count=mechanical_count,
        officially_verified_claim_count=0,
        mechanical_evidence_checks_ok=True,
        factual_claim_independently_verified=False,
        official_source_approved=False,
        claim_binding_hash=binding_hash or "",
        metadata_json={
            "synthetic_test_only": True,
            "freshness_policy_label": request.freshness_policy.policy_label,
        },
    )


@dataclass(frozen=True, slots=True)
class F04aSyntheticCaFixture:
    organization_id: str
    institution_id: str
    exam_version_id: str
    source_id: str
    revision_id: str
    binding_id: str
    evidence_item: KnowledgeEvidenceItem
    claim_text: str
    fact_date_iso: str


def seed_f04a_synthetic_current_affairs_fixture(
    session: Session,
    *,
    organization_id: str = "d13-f04a-org",
    institution_id: str = "d13-f04a-inst",
) -> F04aSyntheticCaFixture:
    """Deterministic SQLite rows for offline F04-A mechanical demo tests only."""

    from app.models import Institution, Organization

    org = session.scalar(select(Organization).where(Organization.id == organization_id))
    if org is None:
        org = Organization(id=organization_id, code="d13-f04a-org", name="D13 F04A Org")
        session.add(org)
        session.flush()
    inst = session.scalar(
        select(Institution).where(
            Institution.id == institution_id,
            Institution.organization_id == organization_id,
        )
    )
    if inst is None:
        inst = Institution(
            id=institution_id,
            organization_id=organization_id,
            code="d13-f04a-inst",
            name="D13 F04A Inst",
        )
        session.add(inst)
        session.flush()

    _, clat_ver = ensure_synthetic_demo_versions(session)
    claim_text = "D13 F04A synthetic CLAT current affairs claim for mechanical linkage."
    locator = "synthetic-article/p1"
    doc_id = f"eduvijna://knowledge/f04a-ca/{F04A_SYNTHETIC_CA_CHECKSUM[:16]}"

    source = Source(
        organization_id=organization_id,
        institution_id=institution_id,
        source_type=SourceType.INSTITUTION_CONTENT.value,
        title="D13 F04A synthetic CLAT CA fixture (test-only)",
        board_or_exam="clat_ug",
        academic_year="2027",
        trust_tier=SourceTrustTier.ANALYTICAL.value,
        status="active",
        anythingllm_workspace=F04A_SYNTHETIC_WORKSPACE,
        metadata_json={
            SYNTHETIC_CA_FIXTURE_METADATA_KEY: True,
            "synthetic_test_only": True,
            "section_code": CLAT_CA_SECTION_CODE,
        },
    )
    session.add(source)
    session.flush()

    revision = SourceRevision(
        source_id=source.id,
        revision_number=1,
        checksum=F04A_SYNTHETIC_CA_CHECKSUM,
        source_snapshot_checksum=hashlib.sha256(F04A_SYNTHETIC_CA_BYTES).hexdigest(),
        content_type="text/plain",
        byte_size=len(F04A_SYNTHETIC_CA_BYTES),
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        extraction_status="validated",
        extracted_checksum=F04A_SYNTHETIC_CA_CHECKSUM,
        status=SourceRevisionStatus.ACTIVE.value,
        active_slot=1,
        anythingllm_document_id=doc_id,
        metadata_json={SYNTHETIC_CA_FIXTURE_METADATA_KEY: True},
    )
    session.add(revision)
    session.flush()

    session.execute(
        exam_version_source_revisions.insert().values(
            exam_version_id=str(clat_ver.id),
            source_revision_id=str(revision.id),
        )
    )

    binding = KnowledgeSourceBinding(
        source_id=str(source.id),
        source_revision_id=str(revision.id),
        source_revision_checksum=revision.checksum,
        anythingllm_workspace=F04A_SYNTHETIC_WORKSPACE,
        anythingllm_document_id=doc_id,
        ownership_scope="institution_scoped",
        organization_id=organization_id,
        institution_id=institution_id,
        index_status="active",
        retrieval_profile_version=F04A_DEFAULT_RETRIEVAL_PROFILE,
        metadata_json={
            "anythingllm_doc_source_identity": doc_id,
            SYNTHETIC_CA_FIXTURE_METADATA_KEY: True,
        },
    )
    session.add(binding)
    session.flush()

    snippet = f"{claim_text} Referenced in synthetic digest."
    item = KnowledgeEvidenceItem(
        source_id=str(source.id),
        source_revision_id=str(revision.id),
        source_revision_checksum=revision.checksum,
        binding_id=str(binding.id),
        trust_tier=source.trust_tier,
        authority_label="synthetic-fixture",
        title=source.title,
        locator=locator,
        snippet=snippet,
        retrieval_score=0.42,
        retrieval_rank=1,
        anythingllm_workspace=F04A_SYNTHETIC_WORKSPACE,
        anythingllm_document_id=doc_id,
        entity_refs={"exam_family": "clat_ug", "academic_year": "2027"},
        citation_label="[synthetic-fixture]",
    )

    return F04aSyntheticCaFixture(
        organization_id=organization_id,
        institution_id=institution_id,
        exam_version_id=str(clat_ver.id),
        source_id=str(source.id),
        revision_id=str(revision.id),
        binding_id=str(binding.id),
        evidence_item=item,
        claim_text=claim_text,
        fact_date_iso="2026-10-15",
    )