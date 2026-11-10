from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_main_exam_intelligence.constants import (
    NTA_2027_BULLETIN_CANDIDATE_URL,
    NTA_2027_BULLETIN_SOURCE_CODE,
    NTA_2027_SYLLABUS_CANDIDATE_URL,
    NTA_2027_SYLLABUS_SOURCE_CODE,
    NTA_DOCUMENTS_PORTAL,
)
from app.jee_main_exam_intelligence.contracts import OfficialSourceRegistrationRef
from app.jee_main_exam_intelligence.enums import OfficialPatternAuthorityStatus
from app.models.enums import (
    SourceRevisionStatus,
    SourceTrustTier,
    SourceType,
)
from app.models.examination import ExamVersion
from app.models.source import Source, SourceRevision
from app.schemas.source_intelligence import SourceRegistrationInput
from app.source_intelligence.service import SourceIntelligenceService

_ACTIVE_REVISION_STATUSES = {
    SourceRevisionStatus.APPROVED.value,
    SourceRevisionStatus.ACTIVE.value,
}


def _find_source_by_logical_code(session: Session, logical_code: str) -> Source | None:
    sources = session.scalars(select(Source)).all()
    for source in sources:
        meta = source.metadata_json or {}
        if meta.get("eduvijna_source_code") == logical_code:
            return source
    title_hint = logical_code.replace("-", " ")
    return session.scalar(select(Source).where(Source.title.contains(title_hint)))


def _source_revision_ref(session: Session, logical_code: str) -> OfficialSourceRegistrationRef:
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
    checksum = revision.checksum or meta.get("candidate_checksum_sha256")
    verified = revision.status in _ACTIVE_REVISION_STATUSES and bool(checksum)
    return OfficialSourceRegistrationRef(
        source_code=logical_code,
        revision_id=revision.id,
        candidate_url=(
            meta.get("candidate_url")
            or source.url
            or _candidate_url_for_code(logical_code)
        ),
        revision_status=revision.status,
        checksum_sha256=checksum,
        verified_for_official_pattern=verified,
    )


def _candidate_url_for_code(logical_code: str) -> str:
    if logical_code == NTA_2027_BULLETIN_SOURCE_CODE:
        return NTA_2027_BULLETIN_CANDIDATE_URL
    if logical_code == NTA_2027_SYLLABUS_SOURCE_CODE:
        return NTA_2027_SYLLABUS_CANDIDATE_URL
    return NTA_DOCUMENTS_PORTAL


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
    required_source_revision_ids: list[str] | None = None,
) -> tuple[OfficialPatternAuthorityStatus, list[OfficialSourceRegistrationRef], dict[str, object]]:
    refs = [
        _source_revision_ref(session, NTA_2027_BULLETIN_SOURCE_CODE),
        _source_revision_ref(session, NTA_2027_SYLLABUS_SOURCE_CODE),
    ]
    bulletin_ok = refs[0].verified_for_official_pattern
    syllabus_ok = refs[1].verified_for_official_pattern
    linked_ids: set[str] = set()
    linked_source_ids: set[str] = set()
    if exam_version is not None:
        linked_source_ids = {src.id for src in exam_version.sources}
        for ref in refs:
            if ref.revision_id:
                rev = session.get(SourceRevision, ref.revision_id)
                if rev is not None and rev.source_id in linked_source_ids:
                    linked_ids.add(ref.revision_id)
    extra_detail: dict[str, object] = {
        "bulletin_verified": bulletin_ok,
        "syllabus_verified": syllabus_ok,
        "exam_version_linked_revision_ids": sorted(linked_ids),
    }
    if not bulletin_ok or not syllabus_ok:
        return OfficialPatternAuthorityStatus.OFFICIAL_PATTERN_NOT_VERIFIED, refs, extra_detail
    if exam_version is not None and refs[0].revision_id and refs[1].revision_id:
        if refs[0].revision_id not in linked_ids or refs[1].revision_id not in linked_ids:
            return OfficialPatternAuthorityStatus.NOT_VERIFIED, refs, extra_detail
    required = set(required_source_revision_ids or [])
    if required:
        missing = required - {r.revision_id for r in refs if r.revision_id}
        if missing:
            return OfficialPatternAuthorityStatus.NOT_VERIFIED, refs, extra_detail
    return OfficialPatternAuthorityStatus.VERIFIED, refs, extra_detail


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
) -> None:
    revisions = [session.get(SourceRevision, rid) for rid in revision_ids]
    for revision in revisions:
        if revision is None:
            continue
        if exam_version not in revision.exam_versions:
            revision.exam_versions.append(exam_version)
        source = revision.source
        if source not in exam_version.sources:
            exam_version.sources.append(source)
    session.flush()
