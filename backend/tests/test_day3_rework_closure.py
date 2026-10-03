from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import configure_logging, redact_log_text
from app.db.base import Base
from app.db.session import create_database_engine
from app.models import (
    Institution,
    Organization,
    Question,
    Source,
    SourceRevision,
    Teacher,
)
from app.models.enums import (
    QuestionOrigin,
    QuestionType,
    SourceIngestionMethod,
    SourceRevisionStatus,
    SourceTrustTier,
    SourceType,
)
from app.schemas.source_intelligence import (
    ManualSourceRevisionInput,
    SourceAccessScope,
    SourceMetadataUpdateInput,
    SourceProvenanceLinkInput,
    SourceRegistrationInput,
)
from app.source_intelligence.extractors import (
    SourceExtractionError,
    extract_content,
)
from app.source_intelligence.security import (
    SourceUrlFetcher,
    UnsafeSourceUrl,
    validate_source_url,
)
from app.source_intelligence.service import (
    SourceGovernanceError,
    SourceIntelligenceService,
    SourceLifecycleError,
)
from app.source_intelligence.storage import LocalSourceStorage

PUBLIC_IP = "93.184.216.34"


class BarrierStorage(LocalSourceStorage):
    def __init__(self, root: Path, barrier: threading.Barrier) -> None:
        super().__init__(root)
        self.barrier = barrier

    def write_revision(
        self,
        *,
        source_id: str,
        revision_number: int,
        checksum: str,
        filename: str | None,
        content: bytes,
    ) -> str:
        path = super().write_revision(
            source_id=source_id,
            revision_number=revision_number,
            checksum=checksum,
            filename=filename,
            content=content,
        )
        self.barrier.wait(timeout=5)
        return path


class FakeResponse:
    status = 200

    def __init__(self) -> None:
        self._sent = False

    def getheader(self, name: str, default: str | None = None) -> str | None:
        if name.lower() == "content-type":
            return "application/json"
        return default

    def read(self, _: int) -> bytes:
        if self._sent:
            return b""
        self._sent = True
        return b'{"ok":true}'


class FakeConnection:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []

    def request(
        self,
        method: str,
        target: str,
        headers: dict[str, str],
    ) -> None:
        del headers
        self.requests.append((method, target))

    def getresponse(self) -> FakeResponse:
        return FakeResponse()

    def close(self) -> None:
        return


def _engine(tmp_path: Path, name: str = "day3-rework.db"):
    database_url = f"sqlite:///{tmp_path / name}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    return engine


def _service(
    session: Session,
    tmp_path: Path,
    *,
    scope: SourceAccessScope | None = None,
    storage: LocalSourceStorage | None = None,
) -> SourceIntelligenceService:
    return SourceIntelligenceService(
        session,
        storage=storage or LocalSourceStorage(tmp_path / "private"),
        access_scope=scope,
    )


def _official(
    service: SourceIntelligenceService,
    *,
    academic_year: str = "2026-27",
) -> Source:
    return service.register_source(
        SourceRegistrationInput(
            source_type=SourceType.OFFICIAL_SYLLABUS,
            title="Synthetic syllabus",
            authority="Synthetic Authority",
            country="IN",
            academic_year=academic_year,
            trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
        )
    )


def _activate_json(
    service: SourceIntelligenceService,
    source: Source,
    content: bytes = b'{"topic":"algebra"}',
) -> SourceRevision:
    revision = service.ingest_upload(
        source.id,
        method=SourceIngestionMethod.JSON,
        content=content,
        filename="source.json",
    )
    service.extract_revision(revision.id)
    service.create_diff(revision.id)
    assert service.validate_revision(revision.id).valid
    service.approve_revision(revision.id, actor_id="founder")
    return service.activate_revision(revision.id, actor_id="founder")


def test_url_fetch_pins_validated_global_address_before_request() -> None:
    captured: dict[str, Any] = {}

    def factory(
        scheme: str,
        hostname: str,
        port: int,
        timeout: float,
        pinned_ip: str,
    ) -> FakeConnection:
        captured.update(
            {
                "scheme": scheme,
                "hostname": hostname,
                "port": port,
                "timeout": timeout,
                "pinned_ip": pinned_ip,
            }
        )
        connection = FakeConnection()
        captured["connection"] = connection
        return connection

    fetcher = SourceUrlFetcher(
        timeout_seconds=1,
        max_bytes=1024,
        max_redirects=0,
        resolver=lambda _: [PUBLIC_IP],
        connection_factory=factory,
    )
    result = fetcher.fetch("https://authority.example/source.json")
    assert result.content == b'{"ok":true}'
    assert captured["pinned_ip"] == PUBLIC_IP
    assert captured["hostname"] == "authority.example"
    assert captured["connection"].requests == [("GET", "/source.json")]

    called = False

    def forbidden_factory(
        scheme: str,
        hostname: str,
        port: int,
        timeout: float,
        pinned_ip: str,
    ) -> FakeConnection:
        del scheme, hostname, port, timeout, pinned_ip
        nonlocal called
        called = True
        return FakeConnection()

    blocked = SourceUrlFetcher(
        timeout_seconds=1,
        max_bytes=1024,
        max_redirects=0,
        resolver=lambda _: ["127.0.0.1"],
        connection_factory=forbidden_factory,
    )
    with pytest.raises(UnsafeSourceUrl):
        blocked.fetch("http://rebind.example/source")
    assert called is False

    with pytest.raises(UnsafeSourceUrl):
        validate_source_url("http://100.64.0.1/source")


def test_source_upload_race_does_not_delete_successful_file(tmp_path: Path) -> None:
    engine = _engine(tmp_path, "same-content-race.db")
    setup_session = Session(engine)
    source_id = _official(_service(setup_session, tmp_path)).id
    setup_session.close()

    barrier = threading.Barrier(2)
    storage = BarrierStorage(tmp_path / "race-private", barrier)
    results: list[str] = []
    errors: list[BaseException] = []

    def worker() -> None:
        session = Session(engine)
        try:
            revision = _service(session, tmp_path, storage=storage).ingest_upload(
                source_id,
                method=SourceIngestionMethod.JSON,
                content=b'{"same":true}',
                filename="source.json",
            )
            results.append(revision.id)
        except BaseException as exc:
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    assert len(results) == 2

    session = Session(engine)
    try:
        revisions = list(
            session.scalars(
                select(SourceRevision).where(SourceRevision.source_id == source_id)
            )
        )
        assert len(revisions) == 1
        assert revisions[0].storage_path
        assert storage.exists(revisions[0].storage_path)
        assert storage.read(revisions[0].storage_path) == b'{"same":true}'
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_different_content_race_retries_revision_number(tmp_path: Path) -> None:
    engine = _engine(tmp_path, "different-content-race.db")
    setup_session = Session(engine)
    source_id = _official(_service(setup_session, tmp_path)).id
    setup_session.close()

    barrier = threading.Barrier(2)
    storage = BarrierStorage(tmp_path / "different-private", barrier)
    errors: list[BaseException] = []

    def worker(content: bytes) -> None:
        session = Session(engine)
        try:
            _service(session, tmp_path, storage=storage).ingest_upload(
                source_id,
                method=SourceIngestionMethod.JSON,
                content=content,
                filename="source.json",
            )
        except BaseException as exc:
            errors.append(exc)
        finally:
            session.close()

    threads = [
        threading.Thread(target=worker, args=(b'{"value":1}',)),
        threading.Thread(target=worker, args=(b'{"value":2}',)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    session = Session(engine)
    try:
        revisions = list(
            session.scalars(
                select(SourceRevision)
                .where(SourceRevision.source_id == source_id)
                .order_by(SourceRevision.revision_number)
            )
        )
        assert [item.revision_number for item in revisions] == [1, 2]
        assert all(item.storage_path and storage.exists(item.storage_path) for item in revisions)
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_withdrawn_approval_cannot_activate_from_stale_session(tmp_path: Path) -> None:
    engine = _engine(tmp_path, "withdrawn-approval.db")
    session_one = Session(engine)
    service_one = _service(session_one, tmp_path)
    source = _official(service_one)
    revision = service_one.ingest_manual(
        source.id,
        ManualSourceRevisionInput(metadata={"version": 1}),
    )
    service_one.create_diff(revision.id)
    assert service_one.validate_revision(revision.id).valid
    service_one.approve_revision(revision.id, actor_id="founder")

    session_two = Session(engine)
    service_two = _service(session_two, tmp_path)
    service_two.reject_revision(
        revision.id,
        actor_id="founder",
        reason="approval withdrawn",
    )
    session_two.close()

    with pytest.raises(SourceLifecycleError, match="only approved"):
        service_one.activate_revision(revision.id, actor_id="founder")

    session_one.refresh(revision)
    assert revision.status == SourceRevisionStatus.REJECTED.value
    session_one.close()
    create_database_engine.cache_clear()


@pytest.mark.parametrize(
    ("status", "active_slot"),
    [
        (SourceRevisionStatus.ACTIVE.value, None),
        (SourceRevisionStatus.STAGED.value, 1),
    ],
)
def test_active_revision_constraint_is_bidirectional(
    tmp_path: Path,
    status: str,
    active_slot: int | None,
) -> None:
    engine = _engine(tmp_path, f"active-{status}-{active_slot}.db")
    session = Session(engine)
    try:
        source = _official(_service(session, tmp_path))
        session.add(
            SourceRevision(
                source_id=source.id,
                revision_number=1,
                ingestion_method=SourceIngestionMethod.MANUAL.value,
                checksum="a" * 64,
                source_snapshot_checksum="b" * 64,
                content_type="application/vnd.eduvijna.metadata+json",
                byte_size=2,
                retrieved_at=source.created_at,
                extraction_status="succeeded",
                extracted_text="{}",
                extracted_checksum="a" * 64,
                status=status,
                active_slot=active_slot,
                metadata_json={"manual_metadata": {}, "source_snapshot": {}},
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()
        create_database_engine.cache_clear()


def test_extraction_rejects_substituted_file_before_parsing(tmp_path: Path) -> None:
    engine = _engine(tmp_path, "substitution.db")
    session = Session(engine)
    try:
        service = _service(session, tmp_path)
        source = _official(service)
        revision = service.ingest_upload(
            source.id,
            method=SourceIngestionMethod.JSON,
            content=b'{"approved":"original"}',
            filename="source.json",
        )
        assert revision.storage_path
        (tmp_path / "private" / revision.storage_path).write_bytes(
            b'{"approved":"substitute"}'
        )
        with pytest.raises(SourceExtractionError, match="checksum"):
            service.extract_revision(revision.id)
        session.refresh(revision)
        assert revision.status == SourceRevisionStatus.FAILED.value
        assert "content_integrity_mismatch" in (revision.failure_reason or "")
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_file_tamper_after_approval_blocks_activation(tmp_path: Path) -> None:
    engine = _engine(tmp_path, "approval-tamper.db")
    session = Session(engine)
    try:
        service = _service(session, tmp_path)
        source = _official(service)
        revision = service.ingest_upload(
            source.id,
            method=SourceIngestionMethod.JSON,
            content=b'{"approved":true}',
            filename="source.json",
        )
        service.extract_revision(revision.id)
        service.create_diff(revision.id)
        assert service.validate_revision(revision.id).valid
        service.approve_revision(revision.id, actor_id="founder")
        assert revision.storage_path
        (tmp_path / "private" / revision.storage_path).write_bytes(
            b'{"approved":false}'
        )
        with pytest.raises(SourceLifecycleError, match="changed"):
            service.activate_revision(revision.id, actor_id="founder")
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_manual_revision_checksum_is_recomputed(tmp_path: Path) -> None:
    engine = _engine(tmp_path, "manual-checksum.db")
    session = Session(engine)
    try:
        service = _service(session, tmp_path)
        source = _official(service)
        revision = service.ingest_manual(
            source.id,
            ManualSourceRevisionInput(metadata={"version": 1}),
        )
        service.create_diff(revision.id)
        revision.checksum = "f" * 64
        revision.byte_size += 10
        session.commit()
        result = service.validate_revision(revision.id)
        assert result.valid is False
        assert result.checks["storage_integrity"] is False
        assert result.checks["extraction_binding"] is False
    finally:
        session.close()
        create_database_engine.cache_clear()


def _tenancy(
    session: Session,
) -> tuple[Organization, Institution, Teacher, Organization, Institution]:
    org_a = Organization(code="org-a", name="Org A")
    org_b = Organization(code="org-b", name="Org B")
    session.add_all([org_a, org_b])
    session.flush()
    inst_a = Institution(organization_id=org_a.id, code="a", name="A")
    inst_b = Institution(organization_id=org_b.id, code="b", name="B")
    session.add_all([inst_a, inst_b])
    session.flush()
    teacher_a = Teacher(
        institution_id=inst_a.id,
        external_code="teacher-a",
        display_name="Teacher A",
    )
    session.add(teacher_a)
    session.commit()
    return org_a, inst_a, teacher_a, org_b, inst_b


def test_owned_sources_enforce_relationships_and_access_scope(tmp_path: Path) -> None:
    engine = _engine(tmp_path, "source-scope.db")
    session = Session(engine)
    org_a, inst_a, teacher_a, org_b, inst_b = _tenancy(session)
    system = _service(session, tmp_path)

    source = system.register_source(
        SourceRegistrationInput(
            organization_id=UUID(org_a.id),
            institution_id=UUID(inst_a.id),
            teacher_id=UUID(teacher_a.id),
            source_type=SourceType.TEACHER_CONTENT,
            title="Teacher source",
            trust_tier=SourceTrustTier.TEACHER,
        )
    )

    with pytest.raises(SourceGovernanceError):
        system.register_source(
            SourceRegistrationInput(
                organization_id=UUID(org_b.id),
                institution_id=UUID(inst_b.id),
                teacher_id=UUID(teacher_a.id),
                source_type=SourceType.TEACHER_CONTENT,
                title="Invalid teacher source",
                trust_tier=SourceTrustTier.TEACHER,
            )
        )

    other_session = Session(engine)
    scoped = _service(
        other_session,
        tmp_path,
        scope=SourceAccessScope(
            organization_id=UUID(org_b.id),
            institution_id=UUID(inst_b.id),
        ),
    )
    with pytest.raises(PermissionError):
        scoped.ingest_manual(
            source.id,
            ManualSourceRevisionInput(metadata={"private": True}),
        )
    other_session.close()

    valid_session = Session(engine)
    valid_scope = _service(
        valid_session,
        tmp_path,
        scope=SourceAccessScope(
            organization_id=UUID(org_a.id),
            institution_id=UUID(inst_a.id),
            teacher_id=UUID(teacher_a.id),
        ),
    )
    revision = valid_scope.ingest_manual(
        source.id,
        ManualSourceRevisionInput(metadata={"private": True}),
    )
    assert revision.source_id == source.id
    valid_session.close()
    session.close()
    create_database_engine.cache_clear()


def test_scoped_provenance_link_cannot_cross_source_ownership(tmp_path: Path) -> None:
    engine = _engine(tmp_path, "provenance-scope.db")
    session = Session(engine)
    org_a, inst_a, teacher_a, org_b, inst_b = _tenancy(session)
    system = _service(session, tmp_path)
    source = system.register_source(
        SourceRegistrationInput(
            organization_id=UUID(org_a.id),
            institution_id=UUID(inst_a.id),
            teacher_id=UUID(teacher_a.id),
            source_type=SourceType.TEACHER_CONTENT,
            title="Teacher source",
            trust_tier=SourceTrustTier.TEACHER,
        )
    )
    revision = system.ingest_manual(
        source.id,
        ManualSourceRevisionInput(metadata={"private": True}),
    )
    system.create_diff(revision.id)
    assert system.validate_revision(revision.id).valid
    system.approve_revision(revision.id, actor_id="founder")
    revision = system.activate_revision(revision.id, actor_id="founder")

    question = Question(
        origin_type=QuestionOrigin.GENERATED.value,
        question_type=QuestionType.DESCRIPTIVE.value,
        stem_text="Synthetic",
    )
    session.add(question)
    session.commit()

    other_session = Session(engine)
    scoped = _service(
        other_session,
        tmp_path,
        scope=SourceAccessScope(
            organization_id=UUID(org_b.id),
            institution_id=UUID(inst_b.id),
        ),
    )
    with pytest.raises(PermissionError):
        scoped.link_provenance(
            SourceProvenanceLinkInput(
                revision_id=UUID(revision.id),
                question_id=UUID(question.id),
            )
        )
    other_session.close()
    session.close()
    create_database_engine.cache_clear()


def test_format_mismatch_strict_csv_and_nonstandard_json_are_rejected(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path, "format-validation.db")
    session = Session(engine)
    try:
        service = _service(session, tmp_path)
        source = _official(service)
        with pytest.raises(ValueError, match="does not match"):
            service.ingest_upload(
                source.id,
                method=SourceIngestionMethod.JSON,
                content=b'{"ok":true}',
                filename="wrong.csv",
            )

        with pytest.raises(SourceExtractionError, match="MIME type"):
            extract_content(
                content=b'{"ok":true}',
                content_type="application/json",
                filename="wrong.csv",
            )
        with pytest.raises(SourceExtractionError, match="CSV"):
            extract_content(
                content=b'a,b\n"unterminated,1\n',
                content_type="text/csv",
                filename="bad.csv",
            )
        with pytest.raises(SourceExtractionError, match="JSON"):
            extract_content(
                content=b'{"value":NaN}',
                content_type="application/json",
                filename="bad.json",
            )
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_missing_storage_becomes_failed_and_reingestion_restores_it(tmp_path: Path) -> None:
    engine = _engine(tmp_path, "missing-storage.db")
    session = Session(engine)
    try:
        service = _service(session, tmp_path)
        source = _official(service)
        content = b'{"recover":true}'
        revision = service.ingest_upload(
            source.id,
            method=SourceIngestionMethod.JSON,
            content=content,
            filename="source.json",
        )
        assert revision.storage_path
        storage_path = tmp_path / "private" / revision.storage_path
        storage_path.unlink()

        with pytest.raises(SourceExtractionError, match="could not be read"):
            service.extract_revision(revision.id)
        session.refresh(revision)
        assert revision.status == SourceRevisionStatus.FAILED.value
        assert "storage_read_failed" in (revision.failure_reason or "")

        service.retry_revision(revision.id)
        restored = service.ingest_upload(
            source.id,
            method=SourceIngestionMethod.JSON,
            content=content,
            filename="source.json",
        )
        assert restored.id == revision.id
        assert restored.storage_path
        assert service.storage.exists(restored.storage_path)
        assert service.storage.read(restored.storage_path) == content
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_logging_suppresses_dependency_urls_and_redacts_secrets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_logging("INFO")
    caplog.set_level(logging.INFO, logger="eduvijna.source")

    fetcher = SourceUrlFetcher(
        timeout_seconds=1,
        max_bytes=1024,
        max_redirects=0,
        resolver=lambda _: [PUBLIC_IP],
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                headers={"content-type": "application/json"},
                content=b'{"ok":true}',
            )
        ),
    )
    fetcher.fetch(
        "https://authority.example/source.json?access_token=synthetic-secret"
    )
    logging.getLogger("eduvijna.source").info("positive-control")

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "positive-control" in messages
    assert "synthetic-secret" not in messages
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert (
        "synthetic-secret"
        not in redact_log_text(
            "GET https://authority.example/x?access_token=synthetic-secret"
        )
    )


def test_metadata_only_change_stages_new_revision_until_activation(tmp_path: Path) -> None:
    engine = _engine(tmp_path, "metadata-change.db")
    session = Session(engine)
    try:
        service = _service(session, tmp_path)
        source = _official(service, academic_year="2026-27")
        first = _activate_json(service, source)
        original_path = first.storage_path

        candidate = service.stage_metadata_update(
            source.id,
            SourceMetadataUpdateInput(academic_year="2027-28"),
            actor_id="founder",
        )
        session.refresh(source)
        assert source.academic_year == "2026-27"
        assert candidate.id != first.id
        assert candidate.checksum == first.checksum
        assert candidate.source_snapshot_checksum != first.source_snapshot_checksum
        assert candidate.storage_path == original_path

        diff = service.create_diff(candidate.id)
        assert diff.checksum_changed is False
        assert diff.metadata_changes_json["academic_year"] == {
            "from": "2026-27",
            "to": "2027-28",
        }
        assert diff.content_diff_json["pattern_drift_candidate"] is True

        assert service.validate_revision(candidate.id).valid
        service.approve_revision(candidate.id, actor_id="founder")
        service.activate_revision(candidate.id, actor_id="founder")
        session.refresh(source)
        assert source.academic_year == "2027-28"
    finally:
        session.close()
        create_database_engine.cache_clear()


def test_source_identity_allows_same_bytes_for_different_metadata_snapshot(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path, "snapshot-identity.db")
    session = Session(engine)
    try:
        service = _service(session, tmp_path)
        source = _official(service)
        first = _activate_json(service, source)
        candidate = service.stage_metadata_update(
            source.id,
            SourceMetadataUpdateInput(title="Updated synthetic syllabus"),
        )
        count = session.scalar(
            select(func.count(SourceRevision.id)).where(
                SourceRevision.source_id == source.id
            )
        )
        assert count == 2
        assert candidate.checksum == first.checksum
        assert candidate.source_snapshot_checksum != first.source_snapshot_checksum
    finally:
        session.close()
        create_database_engine.cache_clear()
