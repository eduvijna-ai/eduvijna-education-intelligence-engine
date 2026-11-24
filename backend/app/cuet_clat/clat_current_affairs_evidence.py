"""F04-A: read-only CLAT current affairs evidence preflight (no ingestion or issuance)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cuet_clat.clat_evidence_contracts import (
    CLAT_CA_SECTION_CODE,
    F04A_FIXTURE_BYTE_SHA_KEY,
    F04A_FIXTURE_BYTE_SIZE_KEY,
    F04A_FIXTURE_FACT_DATE_KEY,
    F04A_HARNESS_TOKEN,
    F04A_PERSISTED_LOCATOR_KEY,
    SYNTHETIC_CA_FIXTURE_METADATA_KEY,
    ClatCurrentAffairsEvidenceDecision,
    ClatCurrentAffairsPreflightRequest,
    ClatEvidenceIssueCode,
    ClatEvidenceOperatingMode,
    ClatEvidencePreflightVerdict,
    build_claim_evidence_binding_hash,
    build_claim_scope_grouping_key,
    snippet_content_digest,
)
from app.cuet_clat.constants import CLAT_PACK_CODE, VERSION_CLAT_2027
from app.cuet_clat.exam_profile import ensure_synthetic_demo_versions
from app.cuet_clat.source_registry import build_source_manifest, clat_official_evidence_ready
from app.knowledge_intelligence.contracts import KnowledgeContextPack, KnowledgeEvidenceItem
from app.models import Institution
from app.models.enums import SourceRevisionStatus, SourceStatus, SourceTrustTier, SourceType
from app.models.examination import ExamPack, ExamVersion
from app.models.knowledge_intelligence import KnowledgeSourceBinding
from app.models.source import (
    Source,
    SourceAuditEvent,
    SourceRevision,
    exam_version_source_revisions,
)

F04A_SYNTHETIC_CA_BYTES = b"eduvijna-d13-f04a-clat-ca-synthetic-fixture-v1\n"
F04A_SYNTHETIC_CA_BYTES_ALT = b"eduvijna-d13-f04a-clat-ca-synthetic-fixture-v2-alt\n"
F04A_SYNTHETIC_CA_CHECKSUM = hashlib.sha256(F04A_SYNTHETIC_CA_BYTES).hexdigest()
F04A_SYNTHETIC_CA_CHECKSUM_ALT = hashlib.sha256(F04A_SYNTHETIC_CA_BYTES_ALT).hexdigest()
F04A_SYNTHETIC_SNAPSHOT_CHECKSUM = hashlib.sha256(F04A_SYNTHETIC_CA_BYTES).hexdigest()
F04A_DEFAULT_RETRIEVAL_PROFILE = "d13-f04a-test-profile@v1"
F04A_SYNTHETIC_WORKSPACE = "d13-f04a-synthetic-ca-ws"
F04A_DEFAULT_LOCATOR = "synthetic-article/p1"
F04A_DEFAULT_FACT_DATE_ISO = "2026-10-15"
_MANIFEST_DISCOVERY_KEY = "d13_manifest_discovery_only"


@dataclass(frozen=True, slots=True)
class _ItemEvaluation:
    item: KnowledgeEvidenceItem
    issues: list[ClatEvidenceIssueCode]
    binding_hash: str | None
    mechanical_ok: bool
    snippet_sha256: str


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
        claim_binding_hash="",
        metadata_json=metadata or {},
    )


def _normalize_exam_family(exam_family: str) -> str:
    return exam_family.strip().lower().replace("-", "_")


def _as_of_utc(
    request: ClatCurrentAffairsPreflightRequest,
) -> tuple[list[ClatEvidenceIssueCode], datetime]:
    issues: list[ClatEvidenceIssueCode] = []
    as_of = request.as_of
    if as_of.tzinfo is None:
        issues.append(ClatEvidenceIssueCode.NAIVE_AS_OF)
        as_of = as_of.replace(tzinfo=UTC)
    return issues, as_of.astimezone(UTC)


def _trusted_persisted_locator(
    revision: SourceRevision,
    binding: KnowledgeSourceBinding | None,
) -> tuple[str, list[ClatEvidenceIssueCode]]:
    rev_meta = dict(revision.metadata_json or {})
    rev_loc = str(rev_meta.get(F04A_PERSISTED_LOCATOR_KEY) or "").strip()
    bind_loc = ""
    if binding is not None:
        bind_loc = str((binding.metadata_json or {}).get(F04A_PERSISTED_LOCATOR_KEY) or "").strip()
    issues: list[ClatEvidenceIssueCode] = []
    if rev_loc and bind_loc and rev_loc != bind_loc:
        issues.append(ClatEvidenceIssueCode.LOCATOR_MISMATCH)
        return "", issues
    locator = rev_loc or bind_loc
    if not locator:
        issues.append(ClatEvidenceIssueCode.LOCATOR_MISMATCH)
    return locator, issues


def _binding_document_consistent(binding: KnowledgeSourceBinding) -> bool:
    meta = dict(binding.metadata_json or {})
    stable = str(meta.get("anythingllm_doc_source_identity") or "").strip()
    remote = (binding.anythingllm_document_id or "").strip()
    if stable and remote and stable != remote:
        return False
    return bool(stable)


def _item_matches_binding_document(
    item: KnowledgeEvidenceItem,
    binding: KnowledgeSourceBinding,
) -> bool:
    if not _binding_document_consistent(binding):
        return False
    stable = str((binding.metadata_json or {}).get("anythingllm_doc_source_identity") or "").strip()
    item_doc = (item.anythingllm_document_id or "").strip()
    return bool(stable) and item_doc == stable


def _claim_snippet_weak_link(claim_text: str, snippet: str) -> bool:
    claim_tokens = [t for t in claim_text.lower().split() if len(t) > 4]
    if not claim_tokens:
        return False
    snippet_l = snippet.lower()
    hits = sum(1 for t in claim_tokens if t in snippet_l)
    return hits >= max(1, len(claim_tokens) // 2)


def _synthetic_fixture_source(source: Source) -> bool:
    return bool((source.metadata_json or {}).get(SYNTHETIC_CA_FIXTURE_METADATA_KEY))


def _validate_synthetic_trusted_scope(
    request: ClatCurrentAffairsPreflightRequest,
) -> list[ClatEvidenceIssueCode]:
    issues: list[ClatEvidenceIssueCode] = []
    if request.operating_mode != ClatEvidenceOperatingMode.SYNTHETIC_TEST_ONLY:
        return issues
    if not request.harness_authorized:
        issues.append(ClatEvidenceIssueCode.HARNESS_UNAUTHORIZED)
    elif (request.trusted_harness_token or "").strip() != F04A_HARNESS_TOKEN:
        issues.append(ClatEvidenceIssueCode.HARNESS_UNAUTHORIZED)
    for _label, value in (
        ("exam_version_id", request.exam_version_id),
        ("organization_id", request.organization_id),
        ("institution_id", request.institution_id),
    ):
        if not (value or "").strip():
            issues.append(ClatEvidenceIssueCode.MISSING_TRUSTED_SCOPE)
    return issues


def _validate_request_scope(
    session: Session,
    request: ClatCurrentAffairsPreflightRequest,
    *,
    as_of_utc: datetime,
) -> tuple[list[ClatEvidenceIssueCode], str | None]:
    issues: list[ClatEvidenceIssueCode] = []
    issues.extend(_validate_synthetic_trusted_scope(request))

    family = _normalize_exam_family(request.exam_family)
    if family != "clat_ug":
        issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
    if request.exam_pack_code != CLAT_PACK_CODE:
        issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
    if request.academic_year != "2027":
        issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
    if request.section_code != CLAT_CA_SECTION_CODE:
        issues.append(ClatEvidenceIssueCode.SECTION_UNSUPPORTED)

    exam_version_id = (request.exam_version_id or "").strip() or None
    require_version = request.operating_mode == ClatEvidenceOperatingMode.SYNTHETIC_TEST_ONLY
    if require_version and not exam_version_id:
        issues.append(ClatEvidenceIssueCode.MISSING_TRUSTED_SCOPE)
    elif exam_version_id:
        version = session.get(ExamVersion, exam_version_id)
        if version is None:
            issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
        else:
            pack = session.get(ExamPack, version.exam_pack_id)
            if pack is None or pack.code != CLAT_PACK_CODE:
                issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
            if version.academic_year != "2027":
                issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
            if version.version_code != VERSION_CLAT_2027:
                issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
            if pack is not None:
                pack_meta = (pack.metadata_json or {}).get("examination_family")
                if str(pack_meta or "") not in {"clat_ug", ""}:
                    issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
    _ = as_of_utc
    return issues, exam_version_id


def _revision_linked_to_exam(session: Session, revision_id: str, exam_version_id: str) -> bool:
    row = session.execute(
        select(exam_version_source_revisions.c.exam_version_id).where(
            exam_version_source_revisions.c.source_revision_id == revision_id,
            exam_version_source_revisions.c.exam_version_id == exam_version_id,
        )
    ).first()
    return row is not None


def _validate_fact_date(
    request: ClatCurrentAffairsPreflightRequest,
    as_of_utc: datetime,
) -> list[ClatEvidenceIssueCode]:
    issues: list[ClatEvidenceIssueCode] = []
    if request.fact_date is None:
        issues.append(ClatEvidenceIssueCode.FACT_DATE_MISSING)
        return issues
    as_of_date = as_of_utc.date()
    if request.fact_date > as_of_date:
        issues.append(ClatEvidenceIssueCode.FACT_DATE_FUTURE)
    age_days = (as_of_date - request.fact_date).days
    if age_days > request.freshness_policy.max_age_days:
        issues.append(ClatEvidenceIssueCode.FACT_DATE_STALE)
    return issues


def _expected_fixture_bytes_for_checksum(checksum: str) -> bytes | None:
    if checksum == F04A_SYNTHETIC_CA_CHECKSUM:
        return F04A_SYNTHETIC_CA_BYTES
    if checksum == F04A_SYNTHETIC_CA_CHECKSUM_ALT:
        return F04A_SYNTHETIC_CA_BYTES_ALT
    return None


def _validate_fixture_receipt(
    source: Source,
    revision: SourceRevision,
    request: ClatCurrentAffairsPreflightRequest,
) -> list[ClatEvidenceIssueCode]:
    issues: list[ClatEvidenceIssueCode] = []
    if not _synthetic_fixture_source(source):
        return issues

    if source.status != SourceStatus.ACTIVE.value:
        issues.append(ClatEvidenceIssueCode.SOURCE_NOT_ACTIVE)

    rev_meta = dict(revision.metadata_json or {})
    src_meta = dict(source.metadata_json or {})
    rev_date = str(rev_meta.get(F04A_FIXTURE_FACT_DATE_KEY) or "").strip()
    src_date = str(src_meta.get(F04A_FIXTURE_FACT_DATE_KEY) or "").strip()
    rev_sha = str(rev_meta.get(F04A_FIXTURE_BYTE_SHA_KEY) or "").strip()
    src_sha = str(src_meta.get(F04A_FIXTURE_BYTE_SHA_KEY) or "").strip()
    rev_size = rev_meta.get(F04A_FIXTURE_BYTE_SIZE_KEY)
    src_size = src_meta.get(F04A_FIXTURE_BYTE_SIZE_KEY)

    if not rev_date or not src_date or rev_date != src_date:
        issues.append(ClatEvidenceIssueCode.FIXTURE_RECEIPT_MISMATCH)
    if not rev_sha or not src_sha or rev_sha != src_sha:
        issues.append(ClatEvidenceIssueCode.FIXTURE_RECEIPT_MISMATCH)
    if rev_size is None or src_size is None or int(rev_size) != int(src_size):
        issues.append(ClatEvidenceIssueCode.FIXTURE_RECEIPT_MISMATCH)

    fixture_bytes = _expected_fixture_bytes_for_checksum(rev_sha)
    if fixture_bytes is None:
        issues.append(ClatEvidenceIssueCode.FIXTURE_RECEIPT_MISMATCH)
    else:
        expected_snap = hashlib.sha256(fixture_bytes).hexdigest()
        if revision.source_snapshot_checksum != expected_snap:
            issues.append(ClatEvidenceIssueCode.FIXTURE_RECEIPT_MISMATCH)
        if revision.byte_size != len(fixture_bytes):
            issues.append(ClatEvidenceIssueCode.FIXTURE_RECEIPT_MISMATCH)
        if revision.checksum != rev_sha:
            issues.append(ClatEvidenceIssueCode.FIXTURE_RECEIPT_MISMATCH)
        if revision.extracted_checksum != revision.checksum:
            issues.append(ClatEvidenceIssueCode.FIXTURE_RECEIPT_MISMATCH)
        if revision.extraction_status != "validated":
            issues.append(ClatEvidenceIssueCode.FIXTURE_RECEIPT_MISMATCH)

    if request.fact_date is None or request.fact_date.isoformat() != rev_date:
        issues.append(ClatEvidenceIssueCode.FIXTURE_RECEIPT_MISMATCH)
    return issues


def _validate_binding_tenant_ownership(
    session: Session,
    request: ClatCurrentAffairsPreflightRequest,
    source: Source,
    binding: KnowledgeSourceBinding | None,
) -> list[ClatEvidenceIssueCode]:
    issues: list[ClatEvidenceIssueCode] = []
    if binding is None:
        return issues
    if request.operating_mode != ClatEvidenceOperatingMode.SYNTHETIC_TEST_ONLY:
        return issues

    req_org = (request.organization_id or "").strip()
    req_inst = (request.institution_id or "").strip()
    src_org = (source.organization_id or "").strip()
    src_inst = (source.institution_id or "").strip()
    bind_org = (binding.organization_id or "").strip()
    bind_inst = (binding.institution_id or "").strip()

    if not req_org or not req_inst or not bind_org or not bind_inst or not src_org or not src_inst:
        issues.append(ClatEvidenceIssueCode.BINDING_TENANT_MISMATCH)
        return issues

    if bind_org != req_org or bind_org != src_org or src_org != req_org:
        issues.append(ClatEvidenceIssueCode.BINDING_TENANT_MISMATCH)
    if bind_inst != req_inst or bind_inst != src_inst or src_inst != req_inst:
        issues.append(ClatEvidenceIssueCode.BINDING_TENANT_MISMATCH)
    if binding.ownership_scope != "institution_scoped":
        issues.append(ClatEvidenceIssueCode.BINDING_TENANT_MISMATCH)

    inst_row = session.get(Institution, req_inst)
    if inst_row is None or str(inst_row.organization_id) != req_org:
        issues.append(ClatEvidenceIssueCode.TENANT_MISMATCH)
    return issues


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


def _evaluate_evidence_item(
    session: Session,
    request: ClatCurrentAffairsPreflightRequest,
    item: KnowledgeEvidenceItem,
    *,
    exam_version_id: str | None,
    as_of_utc: datetime,
) -> _ItemEvaluation:
    issues: list[ClatEvidenceIssueCode] = []
    snippet_sha, _snippet_len = snippet_content_digest(item.snippet)

    source = session.get(Source, item.source_id)
    if source is None:
        issues.append(ClatEvidenceIssueCode.MISSING_SOURCE)
        return _ItemEvaluation(item, issues, None, False, snippet_sha)

    revision = session.get(SourceRevision, item.source_revision_id)
    if revision is None:
        issues.append(ClatEvidenceIssueCode.MISSING_REVISION)
        return _ItemEvaluation(item, issues, None, False, snippet_sha)

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
        if not _item_matches_binding_document(item, binding):
            issues.append(ClatEvidenceIssueCode.FORGED_CITATION)
        issues.extend(_validate_binding_tenant_ownership(session, request, source, binding))

    board = (source.board_or_exam or "").strip().lower()
    if board not in {"clat_ug", "clat"}:
        issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)
    if source.academic_year not in {"2027"}:
        issues.append(ClatEvidenceIssueCode.EXAM_SCOPE_MISMATCH)

    persisted_locator, locator_issues = _trusted_persisted_locator(revision, binding)
    issues.extend(locator_issues)
    item_locator = (item.locator or "").strip()
    if not item_locator or not persisted_locator or item_locator != persisted_locator:
        issues.append(ClatEvidenceIssueCode.LOCATOR_MISMATCH)

    if exam_version_id is None:
        issues.append(ClatEvidenceIssueCode.MISSING_TRUSTED_SCOPE)
    elif not _revision_linked_to_exam(session, str(revision.id), exam_version_id):
        issues.append(ClatEvidenceIssueCode.EXAM_VERSION_UNASSOCIATED)

    issues.extend(_validate_fact_date(request, as_of_utc))
    issues.extend(_validate_fixture_receipt(source, revision, request))

    if not _claim_snippet_weak_link(request.claim_text, item.snippet):
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

    binding_hash: str | None = None
    if not issues and exam_version_id and request.organization_id and request.institution_id:
        sha, length = snippet_content_digest(item.snippet)
        stable_doc = ""
        if binding is not None:
            bmeta = binding.metadata_json or {}
            stable_doc = str(bmeta.get("anythingllm_doc_source_identity") or "")
        binding_hash = build_claim_evidence_binding_hash(
            claim_text=request.claim_text,
            source_id=str(source.id),
            source_revision_id=str(revision.id),
            source_revision_checksum=revision.checksum,
            source_snapshot_checksum=revision.source_snapshot_checksum,
            binding_id=str(binding.id) if binding else "",
            locator=persisted_locator,
            document_id=stable_doc,
            workspace=item.anythingllm_workspace,
            snippet_sha256=sha,
            snippet_byte_length=length,
            fact_date=request.fact_date,
            as_of_utc=as_of_utc,
            freshness_policy_label=request.freshness_policy.policy_label,
            freshness_max_age_days=request.freshness_policy.max_age_days,
            retrieval_profile_version=request.retrieval_profile_version,
            organization_id=request.organization_id,
            institution_id=request.institution_id,
            exam_version_id=exam_version_id,
            exam_pack_code=request.exam_pack_code,
            academic_year=request.academic_year,
            section_code=request.section_code,
        )
        expected = request.expected_claim_binding_hash
        if expected and expected != binding_hash:
            issues.append(ClatEvidenceIssueCode.CLAIM_BINDING_STALE)

    mechanical_ok = not issues and binding_hash is not None
    return _ItemEvaluation(item, issues, binding_hash, mechanical_ok, snippet_sha)


def _item_soft_key(item: KnowledgeEvidenceItem) -> tuple[str, str, str]:
    snippet_digest = hashlib.sha256(item.snippet.encode()).hexdigest()
    return item.binding_id, item.source_revision_id, snippet_digest


def _item_strict_fingerprint(item: KnowledgeEvidenceItem) -> tuple[str, ...]:
    return (
        item.binding_id,
        item.source_revision_id,
        item.source_id,
        item.source_revision_checksum,
        (item.locator or "").strip(),
        item.anythingllm_workspace,
        item.anythingllm_document_id,
        hashlib.sha256(item.snippet.encode()).hexdigest(),
    )


def _coalesce_evidence_items(
    items: list[KnowledgeEvidenceItem],
) -> tuple[list[KnowledgeEvidenceItem], list[ClatEvidenceIssueCode]]:
    grouped: dict[tuple[str, str, str], list[KnowledgeEvidenceItem]] = {}
    for item in items:
        key = _item_soft_key(item)
        grouped.setdefault(key, []).append(item)

    coalesced: list[KnowledgeEvidenceItem] = []
    issues: list[ClatEvidenceIssueCode] = []
    for group in grouped.values():
        fingerprints = {_item_strict_fingerprint(item) for item in group}
        if len(fingerprints) > 1:
            issues.append(ClatEvidenceIssueCode.FORGED_CITATION)
            coalesced.extend(group)
        else:
            coalesced.append(group[0])
    return coalesced, issues


def _validate_context_pack_scope(
    request: ClatCurrentAffairsPreflightRequest,
    context_pack: KnowledgeContextPack | None,
) -> list[ClatEvidenceIssueCode]:
    if context_pack is None:
        return []
    issues: list[ClatEvidenceIssueCode] = []
    scope = context_pack.scope
    req_org = (request.organization_id or "").strip()
    req_inst = (request.institution_id or "").strip()
    req_exam = (request.exam_version_id or "").strip()
    if not scope.organization_id or not scope.institution_id:
        issues.append(ClatEvidenceIssueCode.CONTEXT_PACK_SCOPE_MISMATCH)
    if scope.organization_id and scope.organization_id != req_org:
        issues.append(ClatEvidenceIssueCode.CONTEXT_PACK_SCOPE_MISMATCH)
    if scope.institution_id and scope.institution_id != req_inst:
        issues.append(ClatEvidenceIssueCode.CONTEXT_PACK_SCOPE_MISMATCH)
    if scope.exam_version_id and scope.exam_version_id != req_exam:
        issues.append(ClatEvidenceIssueCode.CONTEXT_PACK_SCOPE_MISMATCH)
    if context_pack.retrieval_profile_version != request.retrieval_profile_version:
        issues.append(ClatEvidenceIssueCode.CONTEXT_PACK_SCOPE_MISMATCH)
    return issues


def _detect_scope_conflicts(
    request: ClatCurrentAffairsPreflightRequest,
    evaluations: list[_ItemEvaluation],
    *,
    exam_version_id: str | None,
) -> list[ClatEvidenceIssueCode]:
    if not exam_version_id or not request.organization_id or not request.institution_id:
        return []

    scope_key = build_claim_scope_grouping_key(
        claim_text=request.claim_text,
        organization_id=request.organization_id,
        institution_id=request.institution_id,
        exam_version_id=exam_version_id,
        exam_pack_code=request.exam_pack_code,
        academic_year=request.academic_year,
        section_code=request.section_code,
    )
    _ = scope_key

    revision_snippets: dict[str, str] = {}
    revision_ids: set[str] = set()
    for ev in evaluations:
        identity_key = f"{ev.item.source_id}:{ev.item.source_revision_id}"
        revision_ids.add(identity_key)
        prior = revision_snippets.get(identity_key)
        if prior is not None and prior != ev.snippet_sha256:
            return [ClatEvidenceIssueCode.CONFLICTING_REVISION]
        revision_snippets.setdefault(identity_key, ev.snippet_sha256)

    if len(revision_ids) > 1:
        distinct_snippets = set(revision_snippets.values())
        if len(distinct_snippets) > 1:
            return [ClatEvidenceIssueCode.CONFLICTING_REVISION]
        return [ClatEvidenceIssueCode.UNTRUSTED_RETRIEVAL_ONLY]
    return []


def evaluate_clat_current_affairs_evidence(
    session: Session,
    request: ClatCurrentAffairsPreflightRequest,
    *,
    evidence_items: list[KnowledgeEvidenceItem] | None = None,
    context_pack: KnowledgeContextPack | None = None,
) -> ClatCurrentAffairsEvidenceDecision:
    """Read-only fail-closed preflight; never writes audits or activates sources."""

    as_of_issues, as_of_utc = _as_of_utc(request)
    pack_issues = _validate_context_pack_scope(request, context_pack)

    raw_items: list[KnowledgeEvidenceItem] = list(evidence_items or [])
    if context_pack is not None:
        raw_items.extend(context_pack.evidence)
    items, coalesce_issues = _coalesce_evidence_items(raw_items)

    scope_issues, exam_version_id = _validate_request_scope(
        session, request, as_of_utc=as_of_utc
    )
    preflight_blockers = scope_issues + as_of_issues + pack_issues + coalesce_issues
    if preflight_blockers:
        return _fail_decision(
            request,
            verdict=ClatEvidencePreflightVerdict.FAIL,
            issues=preflight_blockers,
            metadata={"scope_blocked": True},
        )

    if not items:
        return _fail_decision(
            request,
            verdict=ClatEvidencePreflightVerdict.SOURCE_PENDING,
            issues=[ClatEvidenceIssueCode.NO_EVIDENCE],
        )

    global_issues: list[ClatEvidenceIssueCode] = []
    if request.operating_mode == ClatEvidenceOperatingMode.OFFICIAL_CLAT_2027:
        if not clat_official_evidence_ready(session):
            global_issues.append(ClatEvidenceIssueCode.RIGHTS_NOT_APPROVED)

    evaluations = [
        _evaluate_evidence_item(
            session,
            request,
            item,
            exam_version_id=exam_version_id,
            as_of_utc=as_of_utc,
        )
        for item in items
    ]
    per_item_issues: list[ClatEvidenceIssueCode] = []
    for ev in evaluations:
        per_item_issues.extend(ev.issues)

    conflict_issues = _detect_scope_conflicts(request, evaluations, exam_version_id=exam_version_id)
    per_item_issues.extend(conflict_issues)

    accepted: list[_ItemEvaluation] = [
        ev for ev in evaluations if ev.mechanical_ok and not conflict_issues
    ]
    mechanical_count = (
        len(accepted)
        if request.operating_mode == ClatEvidenceOperatingMode.SYNTHETIC_TEST_ONLY
        else 0
    )

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
            claim_binding_hash="",
            metadata_json={
                "manifest_entry_count": len(build_source_manifest()),
            },
        )

    if all_issues or mechanical_count < 1:
        verdict = (
            ClatEvidencePreflightVerdict.REVIEW_REQUIRED
            if ClatEvidenceIssueCode.CONFLICTING_REVISION in all_issues
            else ClatEvidencePreflightVerdict.FAIL
        )
        if ClatEvidenceIssueCode.NO_EVIDENCE in all_issues:
            verdict = ClatEvidencePreflightVerdict.SOURCE_PENDING
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

    binding_hash = accepted[0].binding_hash or ""
    return ClatCurrentAffairsEvidenceDecision(
        verdict=ClatEvidencePreflightVerdict.MECHANICAL_DEMO_OK,
        operating_mode=request.operating_mode,
        issue_codes=[],
        eligible_test_evidence_count=mechanical_count,
        officially_verified_claim_count=0,
        mechanical_evidence_checks_ok=True,
        factual_claim_independently_verified=False,
        official_source_approved=False,
        claim_binding_hash=binding_hash,
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
    harness_token: str


def seed_f04a_synthetic_current_affairs_fixture(
    session: Session,
    *,
    organization_id: str = "d13-f04a-org",
    institution_id: str = "d13-f04a-inst",
) -> F04aSyntheticCaFixture:
    """Deterministic SQLite rows for offline F04-A mechanical demo tests only."""

    from app.models import Institution, Organization

    existing = session.scalar(
        select(Source).where(
            Source.organization_id == organization_id,
            Source.institution_id == institution_id,
            Source.title == "D13 F04A synthetic CLAT CA fixture (test-only)",
        )
    )
    marker = SYNTHETIC_CA_FIXTURE_METADATA_KEY
    if existing is not None and (existing.metadata_json or {}).get(marker):
        revision = session.scalar(
            select(SourceRevision).where(
                SourceRevision.source_id == existing.id,
                SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
            )
        )
        binding = session.scalar(
            select(KnowledgeSourceBinding).where(
                KnowledgeSourceBinding.source_id == str(existing.id),
                KnowledgeSourceBinding.index_status == "active",
            )
        )
        _, clat_ver = ensure_synthetic_demo_versions(session)
        if revision and binding:
            claim_text = "D13 F04A synthetic CLAT current affairs claim for mechanical linkage."
            snippet = f"{claim_text} Referenced in synthetic digest."
            doc_id = str((binding.metadata_json or {}).get("anythingllm_doc_source_identity") or "")
            item = KnowledgeEvidenceItem(
                source_id=str(existing.id),
                source_revision_id=str(revision.id),
                source_revision_checksum=revision.checksum,
                binding_id=str(binding.id),
                trust_tier=existing.trust_tier,
                authority_label="synthetic-fixture",
                title=existing.title,
                locator=F04A_DEFAULT_LOCATOR,
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
                source_id=str(existing.id),
                revision_id=str(revision.id),
                binding_id=str(binding.id),
                evidence_item=item,
                claim_text=claim_text,
                fact_date_iso=F04A_DEFAULT_FACT_DATE_ISO,
                harness_token=F04A_HARNESS_TOKEN,
            )

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
    locator = F04A_DEFAULT_LOCATOR
    doc_id = f"eduvijna://knowledge/f04a-ca/{F04A_SYNTHETIC_CA_CHECKSUM[:16]}"

    source = Source(
        organization_id=organization_id,
        institution_id=institution_id,
        source_type=SourceType.INSTITUTION_CONTENT.value,
        title="D13 F04A synthetic CLAT CA fixture (test-only)",
        board_or_exam="clat_ug",
        academic_year="2027",
        trust_tier=SourceTrustTier.ANALYTICAL.value,
        status=SourceStatus.ACTIVE.value,
        anythingllm_workspace=F04A_SYNTHETIC_WORKSPACE,
        metadata_json={
            SYNTHETIC_CA_FIXTURE_METADATA_KEY: True,
            "synthetic_test_only": True,
            "section_code": CLAT_CA_SECTION_CODE,
            F04A_FIXTURE_FACT_DATE_KEY: F04A_DEFAULT_FACT_DATE_ISO,
            F04A_FIXTURE_BYTE_SHA_KEY: F04A_SYNTHETIC_CA_CHECKSUM,
            F04A_FIXTURE_BYTE_SIZE_KEY: len(F04A_SYNTHETIC_CA_BYTES),
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
        metadata_json={
            SYNTHETIC_CA_FIXTURE_METADATA_KEY: True,
            F04A_PERSISTED_LOCATOR_KEY: locator,
            F04A_FIXTURE_FACT_DATE_KEY: F04A_DEFAULT_FACT_DATE_ISO,
            F04A_FIXTURE_BYTE_SHA_KEY: F04A_SYNTHETIC_CA_CHECKSUM,
            F04A_FIXTURE_BYTE_SIZE_KEY: len(F04A_SYNTHETIC_CA_BYTES),
        },
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
            F04A_PERSISTED_LOCATOR_KEY: locator,
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
        fact_date_iso=F04A_DEFAULT_FACT_DATE_ISO,
        harness_token=F04A_HARNESS_TOKEN,
    )


def seed_f04a_alt_synthetic_current_affairs_fixture(
    session: Session,
    *,
    organization_id: str,
    institution_id: str,
    exam_version_id: str,
) -> F04aSyntheticCaFixture:
    """Second valid active synthetic source for conflict tests (test harness only)."""

    claim_text = "D13 F04A synthetic CLAT current affairs claim for mechanical linkage."
    locator = "synthetic-article/p2"
    doc_id = f"eduvijna://knowledge/f04a-ca-alt/{F04A_SYNTHETIC_CA_CHECKSUM_ALT[:16]}"

    existing = session.scalar(
        select(Source).where(
            Source.organization_id == organization_id,
            Source.institution_id == institution_id,
            Source.title == "D13 F04A synthetic CLAT CA fixture alt (test-only)",
        )
    )
    if existing is not None:
        revision = session.scalar(
            select(SourceRevision).where(
                SourceRevision.source_id == existing.id,
                SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
            )
        )
        binding = session.scalar(
            select(KnowledgeSourceBinding).where(
                KnowledgeSourceBinding.source_id == str(existing.id),
                KnowledgeSourceBinding.index_status == "active",
            )
        )
        if revision and binding:
            snippet = (
                f"{claim_text} Contradictory alternate synthetic digest denies prior facts."
            )
            item = KnowledgeEvidenceItem(
                source_id=str(existing.id),
                source_revision_id=str(revision.id),
                source_revision_checksum=revision.checksum,
                binding_id=str(binding.id),
                trust_tier=existing.trust_tier,
                authority_label="synthetic-fixture-alt",
                title=existing.title,
                locator=locator,
                snippet=snippet,
                retrieval_score=0.41,
                retrieval_rank=2,
                anythingllm_workspace=F04A_SYNTHETIC_WORKSPACE,
                anythingllm_document_id=doc_id,
                entity_refs={"exam_family": "clat_ug", "academic_year": "2027"},
                citation_label="[synthetic-alt]",
            )
            return F04aSyntheticCaFixture(
                organization_id=organization_id,
                institution_id=institution_id,
                exam_version_id=exam_version_id,
                source_id=str(existing.id),
                revision_id=str(revision.id),
                binding_id=str(binding.id),
                evidence_item=item,
                claim_text=claim_text,
                fact_date_iso=F04A_DEFAULT_FACT_DATE_ISO,
                harness_token=F04A_HARNESS_TOKEN,
            )

    source = Source(
        organization_id=organization_id,
        institution_id=institution_id,
        source_type=SourceType.INSTITUTION_CONTENT.value,
        title="D13 F04A synthetic CLAT CA fixture alt (test-only)",
        board_or_exam="clat_ug",
        academic_year="2027",
        trust_tier=SourceTrustTier.ANALYTICAL.value,
        status=SourceStatus.ACTIVE.value,
        anythingllm_workspace=F04A_SYNTHETIC_WORKSPACE,
        metadata_json={
            SYNTHETIC_CA_FIXTURE_METADATA_KEY: True,
            "synthetic_test_only": True,
            "f04a_fixture_role": "alt",
            F04A_FIXTURE_FACT_DATE_KEY: F04A_DEFAULT_FACT_DATE_ISO,
            F04A_FIXTURE_BYTE_SHA_KEY: F04A_SYNTHETIC_CA_CHECKSUM_ALT,
            F04A_FIXTURE_BYTE_SIZE_KEY: len(F04A_SYNTHETIC_CA_BYTES_ALT),
        },
    )
    session.add(source)
    session.flush()

    revision = SourceRevision(
        source_id=source.id,
        revision_number=1,
        checksum=F04A_SYNTHETIC_CA_CHECKSUM_ALT,
        source_snapshot_checksum=hashlib.sha256(F04A_SYNTHETIC_CA_BYTES_ALT).hexdigest(),
        content_type="text/plain",
        byte_size=len(F04A_SYNTHETIC_CA_BYTES_ALT),
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        extraction_status="validated",
        extracted_checksum=F04A_SYNTHETIC_CA_CHECKSUM_ALT,
        status=SourceRevisionStatus.ACTIVE.value,
        active_slot=1,
        anythingllm_document_id=doc_id,
        metadata_json={
            SYNTHETIC_CA_FIXTURE_METADATA_KEY: True,
            F04A_PERSISTED_LOCATOR_KEY: locator,
            F04A_FIXTURE_FACT_DATE_KEY: F04A_DEFAULT_FACT_DATE_ISO,
            F04A_FIXTURE_BYTE_SHA_KEY: F04A_SYNTHETIC_CA_CHECKSUM_ALT,
            F04A_FIXTURE_BYTE_SIZE_KEY: len(F04A_SYNTHETIC_CA_BYTES_ALT),
        },
    )
    session.add(revision)
    session.flush()

    session.execute(
        exam_version_source_revisions.insert().values(
            exam_version_id=exam_version_id,
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
            F04A_PERSISTED_LOCATOR_KEY: locator,
        },
    )
    session.add(binding)
    session.flush()

    snippet = f"{claim_text} Contradictory alternate synthetic digest denies prior facts."
    item = KnowledgeEvidenceItem(
        source_id=str(source.id),
        source_revision_id=str(revision.id),
        source_revision_checksum=revision.checksum,
        binding_id=str(binding.id),
        trust_tier=source.trust_tier,
        authority_label="synthetic-fixture-alt",
        title=source.title,
        locator=locator,
        snippet=snippet,
        retrieval_score=0.41,
        retrieval_rank=2,
        anythingllm_workspace=F04A_SYNTHETIC_WORKSPACE,
        anythingllm_document_id=doc_id,
        entity_refs={"exam_family": "clat_ug", "academic_year": "2027"},
        citation_label="[synthetic-alt]",
    )

    return F04aSyntheticCaFixture(
        organization_id=organization_id,
        institution_id=institution_id,
        exam_version_id=exam_version_id,
        source_id=str(source.id),
        revision_id=str(revision.id),
        binding_id=str(binding.id),
        evidence_item=item,
        claim_text=claim_text,
        fact_date_iso=F04A_DEFAULT_FACT_DATE_ISO,
        harness_token=F04A_HARNESS_TOKEN,
    )