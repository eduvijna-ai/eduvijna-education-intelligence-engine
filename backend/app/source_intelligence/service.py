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
    ) -> None:
        settings = get_settings()
        self.session = session
        self.storage = storage or LocalSourceStorage(settings.source_storage_dir)
        self.fetcher = fetcher or SourceUrlFetcher(
            timeout_seconds=settings.source_url_timeout_seconds,
            max_bytes=settings.source_max_bytes,
            max_redirects=settings.source_max_redirects,
        )
        self.max_bytes = settings.source_max_bytes
        self._pending_log_events: list[dict[str, Any]] = []

    def _source(self, source_id: str) -> Source:
        source = self.session.get(Source, source_id)
        if source is None:
            raise LookupError(f"source not found: {source_id}")
        return source

    def _revision(self, revision_id: str) -> SourceRevision:
        revision = self.session.get(SourceRevision, revision_id)
        if revision is None:
            raise LookupError(f"source revision not found: {revision_id}")
        return revision

    @staticmethod
    def _source_snapshot(source: Source) -> dict[str, Any]:
        return {
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
        }

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
                "reason": str(error)[:500],
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

        source = Source(
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

    def _duplicate(
        self,
        *,
        source: Source,
        checksum: str,
        actor_id: str | None,
        request_id: str | None,
    ) -> SourceRevision | None:
        revision = self.session.scalar(
            select(SourceRevision).where(
                SourceRevision.source_id == source.id,
                SourceRevision.checksum == checksum,
            )
        )
        if revision is not None:
            self._audit(
                source=source,
                revision=revision,
                event_type="duplicate_content_detected",
                outcome="no_change",
                actor_id=actor_id,
                request_id=request_id,
                payload={"checksum": checksum},
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
    ) -> SourceRevision:
        if not content:
            raise ValueError("source content cannot be empty")
        if len(content) > self.max_bytes:
            raise ValueError("source exceeds configured size limit")

        checksum = _sha256(content)
        duplicate = self._duplicate(
            source=source,
            checksum=checksum,
            actor_id=actor_id,
            request_id=request_id,
        )
        if duplicate is not None:
            return duplicate

        number = self._next_revision_number(source.id)
        stored_path: str | None = None
        try:
            stored_path = self.storage.write_revision(
                source_id=source.id,
                revision_number=number,
                checksum=checksum,
                filename=filename,
                content=content,
            )
            revision_metadata = {
                "source_snapshot": self._source_snapshot(source),
                **(metadata or {}),
            }
            revision = SourceRevision(
                source_id=source.id,
                revision_number=number,
                ingestion_method=method.value,
                checksum=checksum,
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
                },
            )
            self._commit()
            return revision
        except Exception:
            self._rollback()
            if stored_path is not None:
                self.storage.delete(stored_path)
            raise

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

    def ingest_manual(
        self,
        source_id: str,
        payload: ManualSourceRevisionInput,
        *,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> SourceRevision:
        source = self._source(source_id)
        canonical = json.dumps(
            payload.metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        content = canonical.encode("utf-8")
        checksum = _sha256(content)
        duplicate = self._duplicate(
            source=source,
            checksum=checksum,
            actor_id=actor_id,
            request_id=request_id,
        )
        if duplicate is not None:
            return duplicate

        revision = SourceRevision(
            source_id=source.id,
            revision_number=self._next_revision_number(source.id),
            ingestion_method=SourceIngestionMethod.MANUAL.value,
            checksum=checksum,
            content_type="application/vnd.eduvijna.metadata+json",
            byte_size=len(content),
            storage_path=None,
            original_filename=None,
            retrieved_at=_utc_now(),
            extraction_status=SourceExtractionStatus.SUCCEEDED.value,
            extracted_text=canonical,
            extraction_metadata_json={"format": "manual_metadata"},
            status=SourceRevisionStatus.EXTRACTED.value,
            metadata_json={
                "source_snapshot": self._source_snapshot(source),
                "manual_metadata": payload.metadata,
                "note": payload.note,
            },
        )
        self.session.add(revision)
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
        if not revision.storage_path:
            raise SourceLifecycleError("revision does not have stored content")

        content = self.storage.read(revision.storage_path)
        try:
            result = extract_content(
                content=content,
                content_type=revision.content_type,
                filename=revision.original_filename,
            )
        except SourceExtractionError as exc:
            revision.extraction_status = SourceExtractionStatus.FAILED.value
            revision.status = SourceRevisionStatus.FAILED.value
            revision.failure_reason = f"{exc.code}: {exc}"
            self._audit(
                source=source,
                revision=revision,
                event_type="source_extraction_failed",
                outcome="failed",
                actor_id=actor_id,
                request_id=request_id,
                payload={"error_code": exc.code},
            )
            self._commit()
            raise

        revision.extraction_status = SourceExtractionStatus.SUCCEEDED.value
        revision.extracted_text = result.text
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
            payload={"text_length": len(result.text)},
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
            and checksum_changed
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

        errors = _governance_errors(source.source_type, source.trust_tier, source.authority)
        checks: dict[str, bool] = {
            "checksum_format": len(revision.checksum) == 64,
            "extraction_succeeded": (
                revision.extraction_status == SourceExtractionStatus.SUCCEEDED.value
            ),
            "extracted_content_present": bool((revision.extracted_text or "").strip()),
            "source_governance": not errors,
        }

        if revision.storage_path:
            try:
                stored = self.storage.read(revision.storage_path)
                checks["storage_integrity"] = (
                    len(stored) == revision.byte_size and _sha256(stored) == revision.checksum
                )
            except OSError:
                checks["storage_integrity"] = False
        else:
            checks["storage_integrity"] = (
                revision.ingestion_method == SourceIngestionMethod.MANUAL.value
            )

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
        if valid:
            revision.status = SourceRevisionStatus.VALIDATED.value
            revision.failure_reason = None
        else:
            revision.status = SourceRevisionStatus.REJECTED.value
            revision.failure_reason = "; ".join(errors)

        checksum_verified = checks["checksum_format"] and checks["storage_integrity"]
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
        revision = self._revision(revision_id)
        if revision.status != SourceRevisionStatus.VALIDATED.value:
            raise SourceLifecycleError("only validated revisions can be approved")
        revision.status = SourceRevisionStatus.APPROVED.value
        revision.approved_by = actor_id
        revision.approved_at = _utc_now()
        self._audit(
            source=revision.source,
            revision=revision,
            event_type="source_approved",
            outcome="success",
            actor_id=actor_id,
            request_id=request_id,
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
        revision = self._revision(revision_id)
        if revision.status == SourceRevisionStatus.ACTIVE.value:
            return revision
        if revision.status != SourceRevisionStatus.APPROVED.value:
            raise SourceLifecycleError("only approved revisions can be activated")

        source = revision.source
        now = _utc_now()
        try:
            active_revisions = list(
                self.session.scalars(
                    select(SourceRevision)
                    .where(
                        SourceRevision.source_id == source.id,
                        SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
                    )
                    .with_for_update()
                )
            )
            current_active_id = active_revisions[0].id if active_revisions else None
            source_diff = self.session.scalar(
                select(SourceDiff).where(SourceDiff.to_revision_id == revision.id)
            )
            if source_diff is None:
                raise SourceLifecycleError("approved revision does not have a source diff")
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

            # Preserve the one-active-revision invariant during the transaction:
            # release the previous active slot before assigning it to the candidate.
            if active_revisions:
                self.session.flush()

            revision.status = SourceRevisionStatus.ACTIVE.value
            revision.active_slot = 1
            revision.activated_at = now
            revision.superseded_at = None
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
            revision.extraction_metadata_json = {}
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
