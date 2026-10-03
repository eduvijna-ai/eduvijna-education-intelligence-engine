from __future__ import annotations

import difflib
import hashlib
import json
import logging
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import redact_log_text
from app.models import (
    Institution,
    Organization,
    PolicyRule,
    Source,
    SourceAuditEvent,
    SourceDiff,
    SourceRevision,
    Teacher,
)
from app.models.curriculum import CurriculumVersion
from app.models.enums import (
    SourceExtractionStatus,
    SourceIngestionMethod,
    SourceRevisionStatus,
    SourceStatus,
    SourceTrustTier,
    SourceType,
)
from app.models.examination import ExamVersion
from app.models.question import Question
from app.schemas.source_intelligence import (
    ManualSourceRevisionInput,
    SourceAccessScope,
    SourceMetadataUpdateInput,
    SourceProvenanceLinkInput,
    SourceRegistrationInput,
    SourceValidationResult,
)
from app.source_intelligence.extractors import (
    SourceExtractionError,
    extract_content,
)
from app.source_intelligence.security import SourceUrlFetcher
from app.source_intelligence.storage import LocalSourceStorage, SourceStorageError

logger = logging.getLogger("eduvijna.source")

_UPLOAD_MIME: dict[SourceIngestionMethod, tuple[str, str]] = {
    SourceIngestionMethod.PDF: ("application/pdf", "source.pdf"),
    SourceIngestionMethod.DOCX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "source.docx",
    ),
    SourceIngestionMethod.CSV: ("text/csv", "source.csv"),
    SourceIngestionMethod.JSON: ("application/json", "source.json"),
}

_UPLOAD_SUFFIX: dict[SourceIngestionMethod, str] = {
    SourceIngestionMethod.PDF: ".pdf",
    SourceIngestionMethod.DOCX: ".docx",
    SourceIngestionMethod.CSV: ".csv",
    SourceIngestionMethod.JSON: ".json",
}

_ALLOWED_TRUST: dict[SourceType, set[SourceTrustTier]] = {
    SourceType.OFFICIAL_AUTHORITY: {SourceTrustTier.OFFICIAL_PRIMARY},
    SourceType.OFFICIAL_SYLLABUS: {SourceTrustTier.OFFICIAL_PRIMARY},
    SourceType.OFFICIAL_EXAM_BULLETIN: {SourceTrustTier.OFFICIAL_PRIMARY},
    SourceType.OFFICIAL_PAPER: {
        SourceTrustTier.OFFICIAL_PRIMARY,
        SourceTrustTier.OFFICIAL_SUPPORTING,
    },
    SourceType.ANSWER_KEY: {
        SourceTrustTier.OFFICIAL_PRIMARY,
        SourceTrustTier.OFFICIAL_SUPPORTING,
    },
    SourceType.MARKING_SCHEME: {
        SourceTrustTier.OFFICIAL_PRIMARY,
        SourceTrustTier.OFFICIAL_SUPPORTING,
    },
    SourceType.SAMPLE_PAPER: {
        SourceTrustTier.OFFICIAL_PRIMARY,
        SourceTrustTier.OFFICIAL_SUPPORTING,
    },
    SourceType.COMPETITIVE_ANALYSIS: {SourceTrustTier.ANALYTICAL},
    SourceType.INSTITUTION_CONTENT: {SourceTrustTier.INSTITUTION},
    SourceType.TEACHER_CONTENT: {SourceTrustTier.TEACHER},
}


class SourceLifecycleError(ValueError):
    pass


class SourceGovernanceError(ValueError):
    pass


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _governance_errors(source_type: str, trust_tier: str, authority: str | None) -> list[str]:
    errors: list[str] = []
    typed_source = SourceType(source_type)
    typed_trust = SourceTrustTier(trust_tier)
    if typed_trust not in _ALLOWED_TRUST[typed_source]:
        errors.append(
            f"trust tier {typed_trust.value!r} is not valid for source type "
            f"{typed_source.value!r}"
        )
    if typed_source.value in Source.official_type_values() and not authority:
        errors.append("official sources require authority metadata")
    return errors


class SourceIntelligenceService:
    def __init__(
        self,
        session: Session,
        *,
        storage: LocalSourceStorage | None = None,
        fetcher: SourceUrlFetcher | None = None,
        access_scope: SourceAccessScope | None = None,
    ) -> None:
        settings = get_settings()
        self.session = session
        self.storage = storage or LocalSourceStorage(settings.source_storage_dir)
        self.fetcher = fetcher or SourceUrlFetcher(
            timeout_seconds=settings.source_url_timeout_seconds,
            max_bytes=settings.source_max_bytes,
            max_redirects=settings.source_max_redirects,
        )
        self.access_scope = access_scope or SourceAccessScope(system=True)
        self.max_bytes = settings.source_max_bytes
        self._pending_log_events: list[dict[str, Any]] = []

    def _assert_source_access(self, source: Source) -> None:
        scope = self.access_scope
        if scope.system or source.organization_id is None:
            return
        if str(scope.organization_id) != source.organization_id:
            raise PermissionError("source is outside organization scope")
        if (
            scope.institution_id is not None
            and source.institution_id is not None
            and str(scope.institution_id) != source.institution_id
        ):
            raise PermissionError("source is outside institution scope")
        if (
            scope.teacher_id is not None
            and source.teacher_id is not None
            and str(scope.teacher_id) != source.teacher_id
        ):
            raise PermissionError("source is outside teacher scope")

    def _assert_registration_scope(self, payload: SourceRegistrationInput) -> None:
        scope = self.access_scope
        if scope.system or payload.organization_id is None:
            return
        if scope.organization_id != payload.organization_id:
            raise PermissionError("cannot register source outside organization scope")
        if (
            scope.institution_id is not None
            and payload.institution_id is not None
            and scope.institution_id != payload.institution_id
        ):
            raise PermissionError("cannot register source outside institution scope")
        if (
            scope.teacher_id is not None
            and payload.teacher_id is not None
            and scope.teacher_id != payload.teacher_id
        ):
            raise PermissionError("cannot register source outside teacher scope")

    def _validate_registration_ownership(
        self,
        payload: SourceRegistrationInput,
    ) -> None:
        self._assert_registration_scope(payload)
        if payload.organization_id is None:
            return

        organization = self.session.get(Organization, str(payload.organization_id))
        if organization is None:
            raise SourceGovernanceError("source organization does not exist")

        if payload.institution_id is not None:
            institution = self.session.get(Institution, str(payload.institution_id))
            if institution is None:
                raise SourceGovernanceError("source institution does not exist")
            if institution.organization_id != organization.id:
                raise SourceGovernanceError(
                    "source institution does not belong to organization"
                )

        if payload.teacher_id is not None:
            teacher = self.session.get(Teacher, str(payload.teacher_id))
            if teacher is None:
                raise SourceGovernanceError("source teacher does not exist")
            if payload.institution_id is None or teacher.institution_id != str(
                payload.institution_id
            ):
                raise SourceGovernanceError(
                    "source teacher does not belong to institution"
                )

    def _source(self, source_id: str) -> Source:
        source = self.session.scalar(
            select(Source)
            .where(Source.id == source_id)
            .execution_options(populate_existing=True)
        )
        if source is None:
            raise LookupError(f"source not found: {source_id}")
        self._assert_source_access(source)
        return source

    def _revision(
        self,
        revision_id: str,
        *,
        for_update: bool = False,
    ) -> SourceRevision:
        statement = (
            select(SourceRevision)
            .where(SourceRevision.id == revision_id)
            .execution_options(populate_existing=True)
        )
        if for_update:
            statement = statement.with_for_update()
        revision = self.session.scalar(statement)
        if revision is None:
            raise LookupError(f"source revision not found: {revision_id}")
        self._assert_source_access(revision.source)
        return revision

    @staticmethod
    def _source_snapshot(source: Source) -> dict[str, Any]:
        return {
            "organization_id": source.organization_id,
            "institution_id": source.institution_id,
            "teacher_id": source.teacher_id,
            "source_type": source.source_type,
            "title": source.title,
            "url": source.url,
            "authority": source.authority,
            "country": source.country,
            "board_or_exam": source.board_or_exam,
            "academic_year": source.academic_year,
            "effective_date": (
                source.effective_date.isoformat() if source.effective_date is not None else None
            ),
            "copyright_classification": source.copyright_classification,
            "trust_tier": source.trust_tier,
            "anythingllm_workspace": source.anythingllm_workspace,
            "metadata_json": source.metadata_json,
        }

    @staticmethod
    def _snapshot_checksum(snapshot: dict[str, Any]) -> str:
        return _sha256(_canonical_json_bytes(snapshot))

    @staticmethod
    def _apply_snapshot(source: Source, snapshot: dict[str, Any]) -> None:
        source.title = str(snapshot["title"])
        source.url = snapshot.get("url")
        source.authority = snapshot.get("authority")
        source.country = snapshot.get("country")
        source.board_or_exam = snapshot.get("board_or_exam")
        source.academic_year = snapshot.get("academic_year")
        effective_date = snapshot.get("effective_date")
        source.effective_date = (
            date.fromisoformat(str(effective_date)) if effective_date else None
        )
        source.copyright_classification = snapshot.get(
            "copyright_classification"
        )
        source.anythingllm_workspace = snapshot.get("anythingllm_workspace")
        source.metadata_json = dict(snapshot.get("metadata_json") or {})

    def _revision_content_bytes(self, revision: SourceRevision) -> bytes:
        if revision.ingestion_method == SourceIngestionMethod.MANUAL.value:
            manual_metadata = revision.metadata_json.get("manual_metadata")
            if not isinstance(manual_metadata, dict):
                raise SourceStorageError("manual revision metadata is unavailable")
            return _canonical_json_bytes(manual_metadata)
        if not revision.storage_path:
            raise SourceStorageError("revision does not have stored content")
        return self.storage.read(revision.storage_path)

    def _content_integrity(
        self,
        revision: SourceRevision,
    ) -> tuple[bytes, str, bool]:
        content = self._revision_content_bytes(revision)
        checksum = _sha256(content)
        valid = len(content) == revision.byte_size and checksum == revision.checksum
        return content, checksum, valid

    def _approval_fingerprint(self, revision: SourceRevision) -> str:
        source_diff = self.session.scalar(
            select(SourceDiff).where(SourceDiff.to_revision_id == revision.id)
        )
        payload = {
            "revision_id": revision.id,
            "checksum": revision.checksum,
            "source_snapshot_checksum": revision.source_snapshot_checksum,
            "extracted_checksum": revision.extracted_checksum,
            "validated_checksum": revision.validated_checksum,
            "extracted_text_checksum": _sha256(
                (revision.extracted_text or "").encode("utf-8")
            ),
            "content_type": revision.content_type,
            "byte_size": revision.byte_size,
            "diff_from_revision_id": (
                source_diff.from_revision_id if source_diff is not None else None
            ),
        }
        return _sha256(_canonical_json_bytes(payload))

    @staticmethod
    def _validate_upload_filename(
        method: SourceIngestionMethod,
        filename: str | None,
    ) -> None:
        if not filename:
            return
        suffix = Path(filename).suffix.lower()
        expected = _UPLOAD_SUFFIX[method]
        if suffix and suffix != expected:
            raise ValueError(
                f"upload filename extension {suffix!r} does not match "
                f"ingestion method {method.value!r}"
            )

    def _audit(
        self,
        *,
        source: Source,
        revision: SourceRevision | None,
        event_type: str,
        outcome: str,
        actor_id: str | None,
        request_id: str | None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = SourceAuditEvent(
            source_id=source.id,
            source_revision_id=revision.id if revision is not None else None,
            event_type=event_type,
            actor_id=actor_id,
            request_id=request_id,
            outcome=outcome,
            payload_json=payload or {},
        )
        self.session.add(event)
        self._pending_log_events.append(
            {
                "event": "source_intelligence",
                "source_event": event_type,
                "source_id": source.id,
                "source_revision_id": revision.id if revision is not None else None,
                "request_id": request_id,
                "outcome": outcome,
            }
        )

    def _commit(self) -> None:
        pending = list(self._pending_log_events)
        try:
            self.session.commit()
        except Exception:
            self._pending_log_events.clear()
            raise
        self._pending_log_events.clear()
        for entry in pending:
            logger.info(json.dumps(entry, separators=(",", ":")))

    def _rollback(self) -> None:
        self._pending_log_events.clear()
        self.session.rollback()

    def _record_ingestion_failure(
        self,
        *,
        source: Source,
        method: SourceIngestionMethod,
        error: Exception,
        actor_id: str | None,
        request_id: str | None,
    ) -> None:
        self._rollback()
        self._audit(
            source=source,
            revision=None,
            event_type="source_ingestion_failed",
            outcome="failed",
            actor_id=actor_id,
            request_id=request_id,
            payload={
                "ingestion_method": method.value,
                "error_type": type(error).__name__,
                "reason": redact_log_text(str(error))[:500],
            },
        )
        try:
            self._commit()
        except Exception:
            # Preserve the original ingestion error if audit persistence itself is unavailable.
            self._rollback()

    def register_source(
        self,
        payload: SourceRegistrationInput,
        *,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> Source:
        errors = _governance_errors(
            payload.source_type.value,
            payload.trust_tier.value,
            payload.authority,
        )
        if errors:
            raise SourceGovernanceError("; ".join(errors))
        self._validate_registration_ownership(payload)

        source = Source(
            organization_id=(
                str(payload.organization_id)
                if payload.organization_id is not None
                else None
            ),
            institution_id=(
                str(payload.institution_id)
                if payload.institution_id is not None
                else None
            ),
            teacher_id=(
                str(payload.teacher_id)
                if payload.teacher_id is not None
                else None
            ),
            source_type=payload.source_type.value,
            title=payload.title,
            url=payload.url,
            authority=payload.authority,
            country=payload.country,
            board_or_exam=payload.board_or_exam,
            academic_year=payload.academic_year,
            effective_date=payload.effective_date,
            copyright_classification=payload.copyright_classification,
            trust_tier=payload.trust_tier.value,
            anythingllm_workspace=payload.anythingllm_workspace,
            status=SourceStatus.STAGED.value,
            metadata_json=payload.metadata_json,
        )
        self.session.add(source)
        self.session.flush()
        self._audit(
            source=source,
            revision=None,
            event_type="source_registered",
            outcome="success",
            actor_id=actor_id,
            request_id=request_id,
        )
        self._commit()
        return source

    def _next_revision_number(self, source_id: str) -> int:
        maximum = self.session.scalar(
            select(func.max(SourceRevision.revision_number)).where(
                SourceRevision.source_id == source_id
            )
        )
        return int(maximum or 0) + 1

    def _find_identity_revision(
        self,
        *,
        source_id: str,
        checksum: str,
        source_snapshot_checksum: str,
    ) -> SourceRevision | None:
        return self.session.scalar(
            select(SourceRevision)
            .where(
                SourceRevision.source_id == source_id,
                SourceRevision.checksum == checksum,
                SourceRevision.source_snapshot_checksum == source_snapshot_checksum,
            )
            .execution_options(populate_existing=True)
        )

    def _audit_duplicate(
        self,
        *,
        source: Source,
        revision: SourceRevision,
        actor_id: str | None,
        request_id: str | None,
    ) -> None:
        self._audit(
            source=source,
            revision=revision,
            event_type="duplicate_content_detected",
            outcome="no_change",
            actor_id=actor_id,
            request_id=request_id,
            payload={
                "checksum": revision.checksum,
                "source_snapshot_checksum": revision.source_snapshot_checksum,
            },
        )
        self._commit()

    def _restore_missing_storage(
        self,
        *,
        source: Source,
        revision: SourceRevision,
        content: bytes,
        filename: str | None,
        actor_id: str | None,
        request_id: str | None,
    ) -> SourceRevision:
        restored_path = self.storage.write_revision(
            source_id=source.id,
            revision_number=revision.revision_number,
            checksum=revision.checksum,
            filename=filename or revision.original_filename,
            content=content,
        )
        revision.storage_path = restored_path
        if revision.status in {
            SourceRevisionStatus.FAILED.value,
            SourceRevisionStatus.REJECTED.value,
        }:
            revision.status = SourceRevisionStatus.STAGED.value
            revision.extraction_status = SourceExtractionStatus.PENDING.value
            revision.extracted_text = None
            revision.extracted_checksum = None
            revision.validated_checksum = None
            revision.approval_fingerprint = None
            revision.failure_reason = None
            revision.approved_by = None
            revision.approved_at = None
        self._audit(
            source=source,
            revision=revision,
            event_type="source_content_restored",
            outcome="success",
            actor_id=actor_id,
            request_id=request_id,
        )
        self._commit()
        return revision

    def _ingest_bytes(
        self,
        *,
        source: Source,
        method: SourceIngestionMethod,
        content: bytes,
        content_type: str,
        filename: str | None,
        actor_id: str | None,
        request_id: str | None,
        metadata: dict[str, Any] | None = None,
        source_snapshot: dict[str, Any] | None = None,
    ) -> SourceRevision:
        if not content:
            raise ValueError("source content cannot be empty")
        if len(content) > self.max_bytes:
            raise ValueError("source exceeds configured size limit")

        checksum = _sha256(content)
        snapshot = source_snapshot or self._source_snapshot(source)
        snapshot_checksum = self._snapshot_checksum(snapshot)
        duplicate = self._find_identity_revision(
            source_id=source.id,
            checksum=checksum,
            source_snapshot_checksum=snapshot_checksum,
        )
        if duplicate is not None:
            if (
                duplicate.ingestion_method != SourceIngestionMethod.MANUAL.value
                and (
                    not duplicate.storage_path
                    or not self.storage.exists(duplicate.storage_path)
                )
            ):
                return self._restore_missing_storage(
                    source=source,
                    revision=duplicate,
                    content=content,
                    filename=filename,
                    actor_id=actor_id,
                    request_id=request_id,
                )
            self._audit_duplicate(
                source=source,
                revision=duplicate,
                actor_id=actor_id,
                request_id=request_id,
            )
            return duplicate

        stored_path = self.storage.write_revision(
            source_id=source.id,
            revision_number=0,
            checksum=checksum,
            filename=filename,
            content=content,
        )
        revision_metadata = {
            "source_snapshot": snapshot,
            **(metadata or {}),
        }

        last_error: Exception | None = None
        for attempt in range(6):
            number = self._next_revision_number(source.id)
            revision = SourceRevision(
                source_id=source.id,
                revision_number=number,
                ingestion_method=method.value,
                checksum=checksum,
                source_snapshot_checksum=snapshot_checksum,
                content_type=content_type,
                byte_size=len(content),
                storage_path=stored_path,
                original_filename=LocalSourceStorage.sanitize_filename(filename),
                retrieved_at=_utc_now(),
                extraction_status=SourceExtractionStatus.PENDING.value,
                status=SourceRevisionStatus.STAGED.value,
                metadata_json=revision_metadata,
            )
            self.session.add(revision)
            try:
                self.session.flush()
                self._audit(
                    source=source,
                    revision=revision,
                    event_type="source_ingested",
                    outcome="staged",
                    actor_id=actor_id,
                    request_id=request_id,
                    payload={
                        "ingestion_method": method.value,
                        "checksum": checksum,
                        "byte_size": len(content),
                        "source_snapshot_checksum": snapshot_checksum,
                    },
                )
                self._commit()
                return revision
            except (IntegrityError, OperationalError) as exc:
                last_error = exc
                self._rollback()
                duplicate = self._find_identity_revision(
                    source_id=source.id,
                    checksum=checksum,
                    source_snapshot_checksum=snapshot_checksum,
                )
                if duplicate is not None:
                    self._audit_duplicate(
                        source=source,
                        revision=duplicate,
                        actor_id=actor_id,
                        request_id=request_id,
                    )
                    return duplicate
                if isinstance(exc, OperationalError) and "locked" not in str(exc).lower():
                    raise
                time.sleep(0.01 * (attempt + 1))

        raise SourceLifecycleError(
            "could not allocate source revision after concurrent writes"
        ) from last_error

    def ingest_upload(
        self,
        source_id: str,
        *,
        method: SourceIngestionMethod,
        content: bytes,
        filename: str | None = None,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> SourceRevision:
        source = self._source(source_id)
        try:
            if method not in _UPLOAD_MIME:
                raise ValueError("upload method must be pdf, docx, csv, or json")
            self._validate_upload_filename(method, filename)
            content_type, default_filename = _UPLOAD_MIME[method]
            return self._ingest_bytes(
                source=source,
                method=method,
                content=content,
                content_type=content_type,
                filename=filename or default_filename,
                actor_id=actor_id,
                request_id=request_id,
            )
        except Exception as exc:
            self._record_ingestion_failure(
                source=source,
                method=method,
                error=exc,
                actor_id=actor_id,
                request_id=request_id,
            )
            raise

    def ingest_url(
        self,
        source_id: str,
        *,
        url: str | None = None,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> SourceRevision:
        source = self._source(source_id)
        try:
            target_url = url or source.url
            if not target_url:
                raise ValueError("URL ingestion requires a source URL")

            fetched = self.fetcher.fetch(target_url)
            return self._ingest_bytes(
                source=source,
                method=SourceIngestionMethod.URL,
                content=fetched.content,
                content_type=fetched.content_type,
                filename=fetched.filename,
                actor_id=actor_id,
                request_id=request_id,
                metadata={
                    "requested_url": target_url,
                    "final_url": fetched.final_url,
                },
            )
        except Exception as exc:
            self._record_ingestion_failure(
                source=source,
                method=SourceIngestionMethod.URL,
                error=exc,
                actor_id=actor_id,
                request_id=request_id,
            )
            raise

    def _ingest_manual_snapshot(
        self,
        *,
        source: Source,
        payload: ManualSourceRevisionInput,
        snapshot: dict[str, Any],
        actor_id: str | None,
        request_id: str | None,
    ) -> SourceRevision:
        canonical_bytes = _canonical_json_bytes(payload.metadata)
        canonical = canonical_bytes.decode("utf-8")
        checksum = _sha256(canonical_bytes)
        snapshot_checksum = self._snapshot_checksum(snapshot)
        duplicate = self._find_identity_revision(
            source_id=source.id,
            checksum=checksum,
            source_snapshot_checksum=snapshot_checksum,
        )
        if duplicate is not None:
            self._audit_duplicate(
                source=source,
                revision=duplicate,
                actor_id=actor_id,
                request_id=request_id,
            )
            return duplicate

        last_error: Exception | None = None
        for attempt in range(6):
            revision = SourceRevision(
                source_id=source.id,
                revision_number=self._next_revision_number(source.id),
                ingestion_method=SourceIngestionMethod.MANUAL.value,
                checksum=checksum,
                source_snapshot_checksum=snapshot_checksum,
                content_type="application/vnd.eduvijna.metadata+json",
                byte_size=len(canonical_bytes),
                storage_path=None,
                original_filename=None,
                retrieved_at=_utc_now(),
                extraction_status=SourceExtractionStatus.SUCCEEDED.value,
                extracted_text=canonical,
                extracted_checksum=checksum,
                status=SourceRevisionStatus.EXTRACTED.value,
                metadata_json={
                    "source_snapshot": snapshot,
                    "manual_metadata": payload.metadata,
                    "note": payload.note,
                },
            )
            self.session.add(revision)
            try:
                self.session.flush()
                self._audit(
                    source=source,
                    revision=revision,
                    event_type="manual_source_ingested",
                    outcome="extracted",
                    actor_id=actor_id,
                    request_id=request_id,
                )
                self._commit()
                return revision
            except (IntegrityError, OperationalError) as exc:
                last_error = exc
                self._rollback()
                duplicate = self._find_identity_revision(
                    source_id=source.id,
                    checksum=checksum,
                    source_snapshot_checksum=snapshot_checksum,
                )
                if duplicate is not None:
                    self._audit_duplicate(
                        source=source,
                        revision=duplicate,
                        actor_id=actor_id,
                        request_id=request_id,
                    )
                    return duplicate
                if isinstance(exc, OperationalError) and "locked" not in str(exc).lower():
                    raise
                time.sleep(0.01 * (attempt + 1))

        raise SourceLifecycleError(
            "could not allocate manual source revision after concurrent writes"
        ) from last_error

    def ingest_manual(
        self,
        source_id: str,
        payload: ManualSourceRevisionInput,
        *,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> SourceRevision:
        source = self._source(source_id)
        return self._ingest_manual_snapshot(
            source=source,
            payload=payload,
            snapshot=self._source_snapshot(source),
            actor_id=actor_id,
            request_id=request_id,
        )

    def stage_metadata_update(
        self,
        source_id: str,
        payload: SourceMetadataUpdateInput,
        *,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> SourceRevision:
        source = self._source(source_id)
        active = self.session.scalar(
            select(SourceRevision)
            .where(
                SourceRevision.source_id == source.id,
                SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
            )
            .execution_options(populate_existing=True)
        )
        if active is None:
            raise SourceLifecycleError(
                "metadata updates require an existing active source revision"
            )

        snapshot = self._source_snapshot(source)
        for field_name in payload.model_fields_set:
            value = getattr(payload, field_name)
            if field_name == "effective_date":
                snapshot[field_name] = value.isoformat() if value is not None else None
            else:
                snapshot[field_name] = value

        errors = _governance_errors(
            str(snapshot["source_type"]),
            str(snapshot["trust_tier"]),
            snapshot.get("authority"),
        )
        if errors:
            raise SourceGovernanceError("; ".join(errors))

        new_snapshot_checksum = self._snapshot_checksum(snapshot)
        if new_snapshot_checksum == active.source_snapshot_checksum:
            raise SourceLifecycleError("source metadata update contains no material changes")

        if active.ingestion_method == SourceIngestionMethod.MANUAL.value:
            manual_metadata = active.metadata_json.get("manual_metadata")
            if not isinstance(manual_metadata, dict):
                raise SourceLifecycleError("active manual source metadata is unavailable")
            revision = self._ingest_manual_snapshot(
                source=source,
                payload=ManualSourceRevisionInput(
                    metadata=manual_metadata,
                    note="metadata-only source revision",
                ),
                snapshot=snapshot,
                actor_id=actor_id,
                request_id=request_id,
            )
        else:
            content, _, integrity_ok = self._content_integrity(active)
            if not integrity_ok:
                raise SourceLifecycleError(
                    "active source content failed integrity check"
                )
            revision = self._ingest_bytes(
                source=source,
                method=SourceIngestionMethod(active.ingestion_method),
                content=content,
                content_type=active.content_type,
                filename=active.original_filename,
                actor_id=actor_id,
                request_id=request_id,
                metadata={"metadata_only_change": True},
                source_snapshot=snapshot,
            )

        self._audit(
            source=source,
            revision=revision,
            event_type="source_metadata_change_staged",
            outcome="review_required",
            actor_id=actor_id,
            request_id=request_id,
        )
        self._commit()
        return revision

    def extract_revision(
        self,
        revision_id: str,
        *,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> SourceRevision:
        revision = self._revision(revision_id)
        source = revision.source
        if revision.status != SourceRevisionStatus.STAGED.value:
            raise SourceLifecycleError("only staged revisions can be extracted")

        try:
            content, actual_checksum, integrity_ok = self._content_integrity(revision)
            if not integrity_ok:
                raise SourceExtractionError(
                    "content_integrity_mismatch",
                    "stored source bytes do not match revision checksum/size",
                )
            result = extract_content(
                content=content,
                content_type=revision.content_type,
                filename=revision.original_filename,
            )
        except (SourceExtractionError, OSError, SourceStorageError) as exc:
            if isinstance(exc, SourceExtractionError):
                failure = exc
            else:
                failure = SourceExtractionError(
                    "storage_read_failed",
                    "stored source content could not be read",
                )
            revision.extraction_status = SourceExtractionStatus.FAILED.value
            revision.status = SourceRevisionStatus.FAILED.value
            revision.failure_reason = f"{failure.code}: {failure}"
            revision.extracted_checksum = None
            revision.validated_checksum = None
            revision.approval_fingerprint = None
            self._audit(
                source=source,
                revision=revision,
                event_type="source_extraction_failed",
                outcome="failed",
                actor_id=actor_id,
                request_id=request_id,
                payload={"error_code": failure.code},
            )
            self._commit()
            if failure is exc:
                raise
            raise failure from exc

        revision.extraction_status = SourceExtractionStatus.SUCCEEDED.value
        revision.extracted_text = result.text
        revision.extracted_checksum = actual_checksum
        revision.validated_checksum = None
        revision.approval_fingerprint = None
        revision.extraction_metadata_json = result.metadata
        revision.status = SourceRevisionStatus.EXTRACTED.value
        revision.failure_reason = None
        self._audit(
            source=source,
            revision=revision,
            event_type="source_extracted",
            outcome="success",
            actor_id=actor_id,
            request_id=request_id,
            payload={
                "text_length": len(result.text),
                "input_checksum": actual_checksum,
            },
        )
        self._commit()
        return revision

    def create_diff(
        self,
        revision_id: str,
        *,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> SourceDiff:
        revision = self._revision(revision_id)
        source = revision.source
        if revision.status in {
            SourceRevisionStatus.STAGED.value,
            SourceRevisionStatus.FAILED.value,
            SourceRevisionStatus.REJECTED.value,
        }:
            raise SourceLifecycleError("revision must be extracted before diffing")

        if revision.status in {
            SourceRevisionStatus.ACTIVE.value,
            SourceRevisionStatus.SUPERSEDED.value,
        }:
            raise SourceLifecycleError("active or superseded revisions cannot be re-diffed")

        previous = self.session.scalar(
            select(SourceRevision)
            .where(
                SourceRevision.source_id == source.id,
                SourceRevision.id != revision.id,
                SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
            )
            .order_by(SourceRevision.revision_number.desc())
        )
        previous_id = previous.id if previous else None

        existing = self.session.scalar(
            select(SourceDiff).where(SourceDiff.to_revision_id == revision.id)
        )
        refreshing = existing is not None and existing.from_revision_id != previous_id
        if existing is not None and not refreshing:
            return existing

        if refreshing:
            self.session.delete(existing)
            self.session.flush()
            if revision.status in {
                SourceRevisionStatus.VALIDATED.value,
                SourceRevisionStatus.APPROVED.value,
            }:
                revision.status = SourceRevisionStatus.EXTRACTED.value
                revision.validated_checksum = None
                revision.approval_fingerprint = None
                revision.approved_by = None
                revision.approved_at = None

        old_lines = (previous.extracted_text or "").splitlines() if previous else []
        new_lines = (revision.extracted_text or "").splitlines()
        matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
        additions = 0
        removals = 0
        hunks: list[dict[str, int | str]] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            if tag in {"replace", "delete"}:
                removals += i2 - i1
            if tag in {"replace", "insert"}:
                additions += j2 - j1
            if len(hunks) < 20:
                hunks.append(
                    {
                        "operation": tag,
                        "old_start": i1,
                        "old_end": i2,
                        "new_start": j1,
                        "new_end": j2,
                    }
                )

        old_snapshot = previous.metadata_json.get("source_snapshot", {}) if previous else {}
        new_snapshot = revision.metadata_json.get("source_snapshot", {})
        changed_keys = sorted(set(old_snapshot) | set(new_snapshot))
        metadata_changes = {
            key: {"from": old_snapshot.get(key), "to": new_snapshot.get(key)}
            for key in changed_keys
            if old_snapshot.get(key) != new_snapshot.get(key)
        }

        checksum_changed = previous is not None and previous.checksum != revision.checksum
        pattern_drift = (
            previous is not None
            and (checksum_changed or bool(metadata_changes))
            and source.source_type in Source.official_type_values()
        )
        diff = SourceDiff(
            source_id=source.id,
            from_revision_id=previous_id,
            to_revision_id=revision.id,
            checksum_changed=checksum_changed,
            metadata_changes_json=metadata_changes,
            content_diff_json={
                "additions": additions,
                "removals": removals,
                "similarity": matcher.ratio(),
                "changed_hunks": hunks,
                "pattern_drift_candidate": pattern_drift,
            },
            summary=(
                "initial source revision"
                if previous is None
                else (
                    f"checksum_changed={checksum_changed}; "
                    f"additions={additions}; removals={removals}; "
                    f"metadata_changes={len(metadata_changes)}"
                )
            ),
        )
        self.session.add(diff)
        self.session.flush()
        self._audit(
            source=source,
            revision=revision,
            event_type="source_diff_refreshed" if refreshing else "source_diff_created",
            outcome="review_required" if pattern_drift else "success",
            actor_id=actor_id,
            request_id=request_id,
            payload={
                "pattern_drift_candidate": pattern_drift,
                "based_on_active_revision_id": previous_id,
            },
        )
        self._commit()
        return diff

    def validate_revision(
        self,
        revision_id: str,
        *,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> SourceValidationResult:
        revision = self._revision(revision_id)
        source = revision.source
        if revision.status != SourceRevisionStatus.EXTRACTED.value:
            raise SourceLifecycleError("only extracted revisions can be validated")

        snapshot = revision.metadata_json.get("source_snapshot")
        snapshot_is_dict = isinstance(snapshot, dict)
        snapshot_checksum = (
            self._snapshot_checksum(snapshot) if snapshot_is_dict else ""
        )
        governance_errors = (
            _governance_errors(
                str(snapshot.get("source_type")),
                str(snapshot.get("trust_tier")),
                snapshot.get("authority"),
            )
            if snapshot_is_dict
            else ["source snapshot is unavailable"]
        )
        errors = list(governance_errors)

        actual_checksum: str | None = None
        storage_integrity = False
        try:
            _, actual_checksum, storage_integrity = self._content_integrity(revision)
        except (OSError, SourceStorageError):
            storage_integrity = False

        checks: dict[str, bool] = {
            "checksum_format": len(revision.checksum) == 64,
            "source_snapshot_integrity": (
                snapshot_is_dict
                and snapshot_checksum == revision.source_snapshot_checksum
            ),
            "extraction_succeeded": (
                revision.extraction_status == SourceExtractionStatus.SUCCEEDED.value
            ),
            "extracted_content_present": bool((revision.extracted_text or "").strip()),
            "extraction_binding": (
                actual_checksum is not None
                and revision.extracted_checksum == actual_checksum
                and actual_checksum == revision.checksum
            ),
            "storage_integrity": storage_integrity,
            "source_governance": not governance_errors,
        }

        source_diff = self.session.scalar(
            select(SourceDiff).where(SourceDiff.to_revision_id == revision.id)
        )
        current_active = self.session.scalar(
            select(SourceRevision)
            .where(
                SourceRevision.source_id == source.id,
                SourceRevision.id != revision.id,
                SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
            )
            .order_by(SourceRevision.revision_number.desc())
            .execution_options(populate_existing=True)
        )
        current_active_id = current_active.id if current_active else None
        checks["diff_created"] = source_diff is not None
        checks["diff_current"] = (
            source_diff is not None
            and source_diff.from_revision_id == current_active_id
        )

        for check_name, passed in checks.items():
            if not passed:
                errors.append(f"validation check failed: {check_name}")

        valid = not errors
        if valid and actual_checksum is not None:
            revision.status = SourceRevisionStatus.VALIDATED.value
            revision.validated_checksum = actual_checksum
            revision.approval_fingerprint = None
            revision.failure_reason = None
        else:
            revision.status = SourceRevisionStatus.REJECTED.value
            revision.validated_checksum = None
            revision.approval_fingerprint = None
            revision.failure_reason = "; ".join(errors)

        checksum_verified = (
            checks["checksum_format"]
            and checks["storage_integrity"]
            and checks["extraction_binding"]
            and checks["source_snapshot_integrity"]
        )
        self._audit(
            source=source,
            revision=revision,
            event_type="source_checksum_verified",
            outcome="success" if checksum_verified else "failed",
            actor_id=actor_id,
            request_id=request_id,
            payload={
                "checksum_format": checks["checksum_format"],
                "storage_integrity": checks["storage_integrity"],
                "extraction_binding": checks["extraction_binding"],
                "source_snapshot_integrity": checks[
                    "source_snapshot_integrity"
                ],
            },
        )
        self._audit(
            source=source,
            revision=revision,
            event_type="source_validated",
            outcome="success" if valid else "rejected",
            actor_id=actor_id,
            request_id=request_id,
            payload={"checks": checks, "errors": errors},
        )
        self._commit()
        return SourceValidationResult(valid=valid, checks=checks, errors=errors)

    def approve_revision(
        self,
        revision_id: str,
        *,
        actor_id: str,
        request_id: str | None = None,
    ) -> SourceRevision:
        revision = self._revision(revision_id, for_update=True)
        if revision.status != SourceRevisionStatus.VALIDATED.value:
            raise SourceLifecycleError("only validated revisions can be approved")

        try:
            _, actual_checksum, integrity_ok = self._content_integrity(revision)
        except (OSError, SourceStorageError) as exc:
            raise SourceLifecycleError(
                "validated source content is unavailable"
            ) from exc

        if (
            not integrity_ok
            or revision.validated_checksum != actual_checksum
            or revision.extracted_checksum != actual_checksum
        ):
            raise SourceLifecycleError(
                "validated source content changed before approval"
            )

        revision.status = SourceRevisionStatus.APPROVED.value
        revision.approved_by = actor_id
        revision.approved_at = _utc_now()
        revision.approval_fingerprint = self._approval_fingerprint(revision)
        self._audit(
            source=revision.source,
            revision=revision,
            event_type="source_approved",
            outcome="success",
            actor_id=actor_id,
            request_id=request_id,
            payload={"approval_fingerprint": revision.approval_fingerprint},
        )
        self._commit()
        return revision

    def activate_revision(
        self,
        revision_id: str,
        *,
        actor_id: str,
        request_id: str | None = None,
    ) -> SourceRevision:
        revision = self._revision(revision_id, for_update=True)
        if revision.status == SourceRevisionStatus.ACTIVE.value:
            return revision
        if revision.status != SourceRevisionStatus.APPROVED.value:
            raise SourceLifecycleError("only approved revisions can be activated")

        source = self._source(revision.source_id)
        try:
            _, actual_checksum, integrity_ok = self._content_integrity(revision)
        except (OSError, SourceStorageError) as exc:
            raise SourceLifecycleError(
                "approved source content is unavailable"
            ) from exc

        if (
            not integrity_ok
            or revision.validated_checksum != actual_checksum
            or revision.extracted_checksum != actual_checksum
        ):
            raise SourceLifecycleError(
                "approved source content changed before activation"
            )
        if not revision.approval_fingerprint:
            raise SourceLifecycleError("approved revision has no approval fingerprint")
        if revision.approval_fingerprint != self._approval_fingerprint(revision):
            raise SourceLifecycleError(
                "approved source evidence changed before activation"
            )

        snapshot = revision.metadata_json.get("source_snapshot")
        if not isinstance(snapshot, dict):
            raise SourceLifecycleError("approved revision source snapshot is unavailable")
        if self._snapshot_checksum(snapshot) != revision.source_snapshot_checksum:
            raise SourceLifecycleError("approved revision source snapshot changed")

        now = _utc_now()
        try:
            active_revisions = list(
                self.session.scalars(
                    select(SourceRevision)
                    .where(
                        SourceRevision.source_id == source.id,
                        SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
                    )
                    .execution_options(populate_existing=True)
                    .with_for_update()
                )
            )
            current_active_id = active_revisions[0].id if active_revisions else None
            source_diff = self.session.scalar(
                select(SourceDiff)
                .where(SourceDiff.to_revision_id == revision.id)
                .execution_options(populate_existing=True)
            )
            if source_diff is None:
                raise SourceLifecycleError(
                    "approved revision does not have a source diff"
                )
            if source_diff.from_revision_id != current_active_id:
                raise SourceLifecycleError(
                    "candidate diff is stale; refresh diff, validate, and approve again"
                )

            for active in active_revisions:
                active.status = SourceRevisionStatus.SUPERSEDED.value
                active.active_slot = None
                active.superseded_at = now
                self._audit(
                    source=source,
                    revision=active,
                    event_type="source_superseded",
                    outcome="success",
                    actor_id=actor_id,
                    request_id=request_id,
                    payload={"replacement_revision_id": revision.id},
                )

            if active_revisions:
                self.session.flush()

            revision.status = SourceRevisionStatus.ACTIVE.value
            revision.active_slot = 1
            revision.activated_at = now
            revision.superseded_at = None
            self._apply_snapshot(source, snapshot)
            source.status = SourceStatus.ACTIVE.value
            source.checksum = revision.checksum
            source.retrieved_at = revision.retrieved_at
            self._audit(
                source=source,
                revision=revision,
                event_type="source_activated",
                outcome="success",
                actor_id=actor_id,
                request_id=request_id,
            )
            self._commit()
            return revision
        except Exception:
            self._rollback()
            raise

    def reject_revision(
        self,
        revision_id: str,
        *,
        actor_id: str,
        reason: str,
        request_id: str | None = None,
    ) -> SourceRevision:
        revision = self._revision(revision_id)
        if revision.status in {
            SourceRevisionStatus.ACTIVE.value,
            SourceRevisionStatus.SUPERSEDED.value,
        }:
            raise SourceLifecycleError("active or superseded revisions cannot be rejected")
        revision.status = SourceRevisionStatus.REJECTED.value
        revision.active_slot = None
        revision.validated_checksum = None
        revision.approval_fingerprint = None
        revision.failure_reason = reason
        self._audit(
            source=revision.source,
            revision=revision,
            event_type="source_rejected",
            outcome="rejected",
            actor_id=actor_id,
            request_id=request_id,
            payload={"reason": reason[:500]},
        )
        self._commit()
        return revision

    def retry_revision(
        self,
        revision_id: str,
        *,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> SourceRevision:
        revision = self._revision(revision_id)
        if revision.status not in {
            SourceRevisionStatus.FAILED.value,
            SourceRevisionStatus.REJECTED.value,
        }:
            raise SourceLifecycleError("only failed or rejected revisions can be retried")
        if revision.ingestion_method == SourceIngestionMethod.MANUAL.value:
            revision.status = SourceRevisionStatus.EXTRACTED.value
            revision.extraction_status = SourceExtractionStatus.SUCCEEDED.value
        else:
            revision.status = SourceRevisionStatus.STAGED.value
            revision.extraction_status = SourceExtractionStatus.PENDING.value
            revision.extracted_text = None
            revision.extracted_checksum = None
            revision.extraction_metadata_json = {}
        revision.validated_checksum = None
        revision.approval_fingerprint = None
        revision.failure_reason = None
        revision.approved_by = None
        revision.approved_at = None
        self._audit(
            source=revision.source,
            revision=revision,
            event_type="source_retry_requested",
            outcome="success",
            actor_id=actor_id,
            request_id=request_id,
        )
        self._commit()
        return revision

    def link_provenance(
        self,
        payload: SourceProvenanceLinkInput,
        *,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> SourceRevision:
        revision = self._revision(str(payload.revision_id))
        if revision.status not in {
            SourceRevisionStatus.ACTIVE.value,
            SourceRevisionStatus.SUPERSEDED.value,
        }:
            raise SourceLifecycleError(
                "provenance links require an active or superseded source revision"
            )

        target: Any
        target_type: str
        collection: list[Any]
        if payload.curriculum_version_id is not None:
            target_type = "curriculum_version"
            target = self.session.get(CurriculumVersion, str(payload.curriculum_version_id))
            collection = revision.curriculum_versions
        elif payload.exam_version_id is not None:
            target_type = "exam_version"
            target = self.session.get(ExamVersion, str(payload.exam_version_id))
            collection = revision.exam_versions
        elif payload.question_id is not None:
            target_type = "question"
            target = self.session.get(Question, str(payload.question_id))
            collection = revision.questions
        else:
            target_type = "policy_rule"
            target = self.session.get(PolicyRule, str(payload.policy_rule_id))
            collection = revision.policy_rules

        if target is None:
            raise LookupError(f"provenance target not found: {target_type}")

        if (
            target_type == "policy_rule"
            and target.metadata_json.get("enforcement") == "hard"
            and revision.source.trust_tier != SourceTrustTier.OFFICIAL_PRIMARY.value
        ):
            raise SourceGovernanceError(
                "hard official policy rules require official_primary source provenance"
            )

        if target not in collection:
            collection.append(target)

        self._audit(
            source=revision.source,
            revision=revision,
            event_type="source_provenance_linked",
            outcome="success",
            actor_id=actor_id,
            request_id=request_id,
            payload={"target_type": target_type, "target_id": target.id},
        )
        self._commit()
        return revision
