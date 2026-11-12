from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.jee_main_exam_intelligence.blueprint_snapshot import (
    blueprint_fully_verified,
    load_production_blueprint_snapshot,
)
from app.jee_main_exam_intelligence.constants import (
    JEE_MAIN_VERSION_2027,
    NTA_2027_BULLETIN_CANDIDATE_URL,
    NTA_2027_BULLETIN_SOURCE_CODE,
    NTA_2027_SYLLABUS_CANDIDATE_URL,
    NTA_2027_SYLLABUS_SOURCE_CODE,
    NTA_DOCUMENTS_PORTAL,
)
from app.jee_main_exam_intelligence.contracts import OfficialSourceRegistrationRef
from app.jee_main_exam_intelligence.enums import OfficialPatternAuthorityStatus
from app.models.enums import (
    SourceExtractionStatus,
    SourceIngestionMethod,
    SourceRevisionStatus,
    SourceTrustTier,
    SourceType,
)
from app.models.examination import ExamVersion
from app.models.source import Source, SourceAuditEvent, SourceRevision
from app.schemas.source_intelligence import SourceRegistrationInput
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import SourceStorageError

_PDF_CONTENT_TYPES = {"application/pdf"}


def _find_source_by_logical_code(session: Session, logical_code: str) -> Source | None:
    sources = session.scalars(select(Source)).all()
    for source in sources:
        meta = source.metadata_json or {}
        if meta.get("eduvijna_source_code") == logical_code:
            return source
    title_hint = logical_code.replace("-", " ")
    return session.scalar(select(Source).where(Source.title.contains(title_hint)))


def _revision_row(
    session: Session, logical_code: str, *, production: bool
) -> OfficialSourceRegistrationRef:
    source = _find_source_by_logical_code(session, logical_code)
    if source is None:
        return OfficialSourceRegistrationRef(
            source_code=logical_code,
            revision_id=None,
            candidate_url=_candidate_url_for_code(logical_code),
            revision_status="missing",
            checksum_sha256=None,
            verified_for_official_pattern=False,
        )
    revision = session.scalar(
        select(SourceRevision)
        .where(
            SourceRevision.source_id == source.id,
            SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
        )
        .order_by(SourceRevision.revision_number.desc())
    )
    if revision is None:
        revision = session.scalar(
            select(SourceRevision)
            .where(SourceRevision.source_id == source.id)
            .order_by(SourceRevision.revision_number.desc())
        )
    if revision is None:
        return OfficialSourceRegistrationRef(
            source_code=logical_code,
            revision_id=None,
            candidate_url=_candidate_url_for_code(logical_code),
            revision_status="missing",
            checksum_sha256=None,
            verified_for_official_pattern=False,
        )
    meta = revision.metadata_json or {}
    checksum = revision.checksum
    verified = False
    if production:
        verified = _revision_is_production_nta_approved(session, revision, logical_code)
    else:
        verified = _revision_is_synthetic_demonstration(revision)
    return OfficialSourceRegistrationRef(
        source_code=logical_code,
        revision_id=revision.id,
        candidate_url=(
            meta.get("candidate_url") or source.url or _candidate_url_for_code(logical_code)
        ),
        revision_status=revision.status,
        checksum_sha256=checksum,
        verified_for_official_pattern=verified,
    )


def _revision_is_synthetic_demonstration(revision: SourceRevision) -> bool:
    if revision.status != SourceRevisionStatus.ACTIVE.value:
        return False
    meta = revision.metadata_json or {}
    manual = meta.get("manual_metadata") or {}
    if meta.get("synthetic_nta_harness") or manual.get("synthetic_nta_harness"):
        return True
    if revision.ingestion_method == SourceIngestionMethod.JSON.value:
        return True
    if revision.content_type == "application/json":
        return True
    return False


def _revision_is_production_nta_approved(
    session: Session, revision: SourceRevision, logical_code: str
) -> bool:
    """Prove real stored PDF bytes and an intact signed source lifecycle.

    Metadata claims, a PDF MIME string or a curator name alone never activate
    the production NTA exam blueprint.
    """
    if revision.status != SourceRevisionStatus.ACTIVE.value:
        return False
    meta = revision.metadata_json or {}
    manual = meta.get("manual_metadata") or {}
    if meta.get("synthetic_nta_harness") or manual.get("synthetic_nta_harness"):
        return False
    if revision.ingestion_method in (
        SourceIngestionMethod.JSON.value,
        SourceIngestionMethod.MANUAL.value,
    ):
        return False
    if revision.content_type not in _PDF_CONTENT_TYPES:
        return False
    if revision.extraction_status != SourceExtractionStatus.SUCCEEDED.value:
        return False
    if not revision.storage_path or revision.byte_size <= 0:
        return False
    source = revision.source
    source_meta = source.metadata_json or {}
    expected_type = (
        SourceType.OFFICIAL_EXAM_BULLETIN.value
        if logical_code == NTA_2027_BULLETIN_SOURCE_CODE
        else SourceType.OFFICIAL_SYLLABUS.value
    )
    if (
        source_meta.get("eduvijna_source_code") != logical_code
        or source.source_type != expected_type
        or source.trust_tier != SourceTrustTier.OFFICIAL_PRIMARY.value
        or source.authority != "National Testing Agency"
    ):
        return False
    locators = meta.get("page_locators") or manual.get("page_locators")
    if not locators or not revision.approved_by or not revision.approved_at:
        return False
    if not revision.activated_at or not revision.approval_fingerprint:
        return False
    if (
        not revision.checksum
        or revision.validated_checksum != revision.checksum
        or revision.extracted_checksum != revision.checksum
    ):
        return False

    # The original source lifecycle records an actual approval audit event.
    approval = session.scalar(
        select(SourceAuditEvent)
        .where(
            SourceAuditEvent.source_revision_id == revision.id,
            SourceAuditEvent.event_type == "source_approved",
            SourceAuditEvent.outcome == "success",
            SourceAuditEvent.actor_id == revision.approved_by,
        )
        .order_by(SourceAuditEvent.created_at.desc())
    )
    if approval is None:
        return False
    service = SourceIntelligenceService(session)
    try:
        payload, checksum, intact = service._content_integrity(revision)
        expected_fingerprint = service._approval_fingerprint(revision)
    except (OSError, SourceStorageError, ValueError):
        return False
    return (
        intact
        and payload.startswith(b"%PDF-")
        and checksum == revision.checksum
        and revision.approval_fingerprint == expected_fingerprint
    )


def _candidate_url_for_code(logical_code: str) -> str:
    if logical_code == NTA_2027_BULLETIN_SOURCE_CODE:
        return NTA_2027_BULLETIN_CANDIDATE_URL
    if logical_code == NTA_2027_SYLLABUS_SOURCE_CODE:
        return NTA_2027_SYLLABUS_CANDIDATE_URL
    return NTA_DOCUMENTS_PORTAL


def _revision_pinned_to_exam_version(session: Session, exam_version: ExamVersion, rid: str) -> bool:
    revision = session.get(SourceRevision, rid)
    if revision is None:
        return False
    if exam_version in revision.exam_versions:
        return True
    pinned = (exam_version.metadata_json or {}).get("pinned_source_revision_ids") or []
    return rid in pinned


def register_nta_2027_candidate_sources(session: Session) -> dict[str, str]:
    """Register NTA 2027 bulletin/syllabus sources in STAGED state; never auto-approve."""
    service = SourceIntelligenceService(session)
    ids: dict[str, str] = {}
    for logical_code, url, source_type, title in (
        (
            NTA_2027_BULLETIN_SOURCE_CODE,
            NTA_2027_BULLETIN_CANDIDATE_URL,
            SourceType.OFFICIAL_EXAM_BULLETIN,
            "JEE Main 2027 Information Bulletin (candidate)",
        ),
        (
            NTA_2027_SYLLABUS_SOURCE_CODE,
            NTA_2027_SYLLABUS_CANDIDATE_URL,
            SourceType.OFFICIAL_SYLLABUS,
            "JEE Main 2027 Syllabus (candidate)",
        ),
    ):
        source = _find_source_by_logical_code(session, logical_code)
        if source is None:
            source = service.register_source(
                SourceRegistrationInput(
                    source_type=source_type,
                    title=title,
                    url=url,
                    authority="National Testing Agency",
                    country="IN",
                    board_or_exam="JEE-Main",
                    academic_year="2026-27",
                    copyright_classification="official-public-document",
                    trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
                    metadata_json={
                        "eduvijna_source_code": logical_code,
                        "discovery_portal": NTA_DOCUMENTS_PORTAL,
                        "day11_candidate": True,
                        "official_pattern_activation": "pending_independent_nta_review",
                        "candidate_url": url,
                        "nta_exam_version_code": JEE_MAIN_VERSION_2027,
                    },
                ),
                actor_id="day11-curator",
                request_id="d11-register-candidate",
            )
        ids[logical_code] = source.id
    return ids


def evaluate_official_pattern_authority(
    session: Session,
    *,
    exam_version: ExamVersion | None,
    exam_version_code: str | None,
    execution_mode: TrustExecutionMode = TrustExecutionMode.PRODUCTION,
    required_source_revision_ids: list[str] | None = None,
) -> tuple[OfficialPatternAuthorityStatus, list[OfficialSourceRegistrationRef], dict[str, object]]:
    production = execution_mode == TrustExecutionMode.PRODUCTION
    refs = [
        _revision_row(session, NTA_2027_BULLETIN_SOURCE_CODE, production=production),
        _revision_row(session, NTA_2027_SYLLABUS_SOURCE_CODE, production=production),
    ]
    extra_detail: dict[str, object] = {
        "execution_mode": execution_mode.value,
        "exam_version_present": exam_version is not None,
    }

    if exam_version is None:
        extra_detail["reason"] = "missing_exam_version"
        return OfficialPatternAuthorityStatus.NOT_VERIFIED, refs, extra_detail

    if exam_version_code and exam_version.version_code != exam_version_code:
        extra_detail["reason"] = "exam_version_code_mismatch"
        return OfficialPatternAuthorityStatus.NOT_VERIFIED, refs, extra_detail

    version_meta = exam_version.metadata_json or {}
    nta_year = version_meta.get("nta_exam_version_code") or exam_version.version_code
    for ref in refs:
        source = _find_source_by_logical_code(session, ref.source_code)
        if source is not None:
            src_year = (source.metadata_json or {}).get("nta_exam_version_code")
            if src_year and src_year != nta_year:
                extra_detail["reason"] = "source_exam_year_mismatch"
                return OfficialPatternAuthorityStatus.NOT_VERIFIED, refs, extra_detail

    pinned_bulletin = refs[0].revision_id
    pinned_syllabus = refs[1].revision_id
    if not pinned_bulletin or not pinned_syllabus:
        return OfficialPatternAuthorityStatus.OFFICIAL_PATTERN_NOT_VERIFIED, refs, extra_detail

    if not _revision_pinned_to_exam_version(session, exam_version, pinned_bulletin):
        extra_detail["reason"] = "bulletin_not_pinned_to_exam_version"
        return OfficialPatternAuthorityStatus.NOT_VERIFIED, refs, extra_detail
    if not _revision_pinned_to_exam_version(session, exam_version, pinned_syllabus):
        extra_detail["reason"] = "syllabus_not_pinned_to_exam_version"
        return OfficialPatternAuthorityStatus.NOT_VERIFIED, refs, extra_detail

    required = set(required_source_revision_ids or [])
    if required:
        missing = required - {pinned_bulletin, pinned_syllabus}
        if missing:
            extra_detail["reason"] = "missing_required_source_revision"
            return OfficialPatternAuthorityStatus.NOT_VERIFIED, refs, extra_detail

    if production:
        if not version_meta.get("official_pattern_verified"):
            extra_detail["reason"] = "exam_version_not_official_pattern_verified"
            return OfficialPatternAuthorityStatus.OFFICIAL_PATTERN_NOT_VERIFIED, refs, extra_detail
        if not blueprint_fully_verified(session, exam_version):
            extra_detail["reason"] = "blueprint_rules_not_verified"
            return OfficialPatternAuthorityStatus.OFFICIAL_PATTERN_NOT_VERIFIED, refs, extra_detail
        if not (refs[0].verified_for_official_pattern and refs[1].verified_for_official_pattern):
            return OfficialPatternAuthorityStatus.OFFICIAL_PATTERN_NOT_VERIFIED, refs, extra_detail
        snapshot = load_production_blueprint_snapshot(session, exam_version)
        if snapshot is None:
            extra_detail["reason"] = "blueprint_snapshot_unavailable"
            return OfficialPatternAuthorityStatus.NOT_VERIFIED, refs, extra_detail
        extra_detail["production_blueprint"] = {
            "total_questions": snapshot.total_questions,
            "blueprint_rule_ids": list(snapshot.blueprint_rule_ids),
        }
        return OfficialPatternAuthorityStatus.VERIFIED, refs, extra_detail

    if refs[0].verified_for_official_pattern and refs[1].verified_for_official_pattern:
        extra_detail["synthetic_demonstration"] = True
        return OfficialPatternAuthorityStatus.SYNTHETIC_FIXTURE_DEMONSTRATION, refs, extra_detail

    return OfficialPatternAuthorityStatus.OFFICIAL_PATTERN_NOT_VERIFIED, refs, extra_detail


def detect_source_drift(
    session: Session,
    *,
    revision_id: str,
    expected_checksum: str,
) -> bool:
    revision = session.get(SourceRevision, revision_id)
    if revision is None:
        return True
    current = revision.checksum or ""
    return bool(expected_checksum) and current != expected_checksum


def link_approved_revisions_to_exam_version(
    session: Session,
    *,
    exam_version: ExamVersion,
    revision_ids: list[str],
    synthetic_demonstration_only: bool = False,
) -> None:
    revisions = [session.get(SourceRevision, rid) for rid in revision_ids]
    pinned: list[str] = []
    for revision in revisions:
        if revision is None:
            continue
        if exam_version not in revision.exam_versions:
            revision.exam_versions.append(exam_version)
        source = revision.source
        if source not in exam_version.sources:
            exam_version.sources.append(source)
        pinned.append(revision.id)
    exam_version.metadata_json = {
        **(exam_version.metadata_json or {}),
        "pinned_source_revision_ids": sorted(set(pinned)),
    }
    if synthetic_demonstration_only:
        exam_version.metadata_json["synthetic_demo_sources_linked"] = True
        exam_version.metadata_json.setdefault("official_pattern_verified", False)
    session.flush()
