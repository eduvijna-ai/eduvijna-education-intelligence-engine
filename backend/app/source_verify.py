from __future__ import annotations

import json
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.models import SourceAuditEvent
from app.models.enums import (
    SourceIngestionMethod,
    SourceRevisionStatus,
    SourceTrustTier,
    SourceType,
)
from app.schemas.source_intelligence import SourceRegistrationInput
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage


def build_source_intelligence_verification() -> dict[str, object]:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)

    with tempfile.TemporaryDirectory(prefix="eduvijna-source-verify-") as directory:
        session = Session(engine)
        service = SourceIntelligenceService(
            session,
            storage=LocalSourceStorage(Path(directory) / "private"),
        )
        try:
            source = service.register_source(
                SourceRegistrationInput(
                    source_type=SourceType.OFFICIAL_SYLLABUS,
                    title="Synthetic verification syllabus",
                    authority="Synthetic Education Authority",
                    country="IN",
                    board_or_exam="SYNTH",
                    academic_year="2026-27",
                    copyright_classification="official-public-document",
                    trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
                ),
                actor_id="verification",
            )

            first = service.ingest_upload(
                source.id,
                method=SourceIngestionMethod.JSON,
                content=b'{"topics":["algebra"]}',
                filename="syllabus.json",
                actor_id="verification",
            )
            service.extract_revision(first.id, actor_id="verification")
            first_diff = service.create_diff(first.id, actor_id="verification")
            assert service.validate_revision(first.id, actor_id="verification").valid
            service.approve_revision(first.id, actor_id="verification")
            first = service.activate_revision(first.id, actor_id="verification")
            first_checksum = first.checksum

            second = service.ingest_upload(
                source.id,
                method=SourceIngestionMethod.JSON,
                content=b'{"topics":["algebra","geometry"]}',
                filename="syllabus.json",
                actor_id="verification",
            )
            service.extract_revision(second.id, actor_id="verification")
            second_diff = service.create_diff(second.id, actor_id="verification")

            session.refresh(first)
            session.refresh(source)
            before_activation = {
                "active_revision": first.revision_number,
                "active_status": first.status,
                "candidate_revision": second.revision_number,
                "candidate_status": second.status,
                "source_checksum_unchanged": source.checksum == first_checksum,
                "pattern_drift_candidate": second_diff.content_diff_json[
                    "pattern_drift_candidate"
                ],
            }

            assert service.validate_revision(second.id, actor_id="verification").valid
            service.approve_revision(second.id, actor_id="verification")
            second = service.activate_revision(second.id, actor_id="verification")

            session.refresh(first)
            session.refresh(source)
            event_count = session.scalar(
                select(func.count(SourceAuditEvent.id)).where(
                    SourceAuditEvent.source_id == source.id
                )
            )

            return {
                "source_id": source.id,
                "first_revision": {
                    "revision_number": first.revision_number,
                    "initial_diff": first_diff.summary,
                    "final_status": first.status,
                },
                "before_second_activation": before_activation,
                "second_revision": {
                    "revision_number": second.revision_number,
                    "status": second.status,
                    "source_checksum_matches": source.checksum == second.checksum,
                },
                "single_active_revision": (
                    second.status == SourceRevisionStatus.ACTIVE.value
                    and first.status == SourceRevisionStatus.SUPERSEDED.value
                ),
                "audit_event_count": int(event_count or 0),
            }
        finally:
            session.close()


def main() -> None:
    print(json.dumps(build_source_intelligence_verification(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
