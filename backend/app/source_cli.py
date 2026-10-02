from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.db.session import session_factory
from app.models import Source, SourceAuditEvent, SourceDiff, SourceRevision
from app.models.enums import SourceIngestionMethod, SourceTrustTier, SourceType
from app.schemas.source_intelligence import (
    ManualSourceRevisionInput,
    SourceRegistrationInput,
)
from app.source_intelligence.service import SourceIntelligenceService


def _json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("metadata JSON must be an object")
    return payload


def _print_source(source: Source, session: Any) -> None:
    revisions = list(
        session.scalars(
            select(SourceRevision)
            .where(SourceRevision.source_id == source.id)
            .order_by(SourceRevision.revision_number)
        )
    )
    diffs = list(
        session.scalars(
            select(SourceDiff)
            .where(SourceDiff.source_id == source.id)
            .order_by(SourceDiff.created_at)
        )
    )
    events = list(
        session.scalars(
            select(SourceAuditEvent)
            .where(SourceAuditEvent.source_id == source.id)
            .order_by(SourceAuditEvent.created_at)
        )
    )
    print(
        json.dumps(
            {
                "source": {
                    "id": source.id,
                    "title": source.title,
                    "source_type": source.source_type,
                    "trust_tier": source.trust_tier,
                    "status": source.status,
                    "checksum": source.checksum,
                },
                "revisions": [
                    {
                        "id": item.id,
                        "revision_number": item.revision_number,
                        "ingestion_method": item.ingestion_method,
                        "checksum": item.checksum,
                        "status": item.status,
                        "extraction_status": item.extraction_status,
                        "failure_reason": item.failure_reason,
                    }
                    for item in revisions
                ],
                "diffs": [
                    {
                        "id": item.id,
                        "from_revision_id": item.from_revision_id,
                        "to_revision_id": item.to_revision_id,
                        "checksum_changed": item.checksum_changed,
                        "summary": item.summary,
                        "content": item.content_diff_json,
                    }
                    for item in diffs
                ],
                "audit_events": [
                    {
                        "event_type": item.event_type,
                        "revision_id": item.source_revision_id,
                        "outcome": item.outcome,
                        "actor_id": item.actor_id,
                    }
                    for item in events
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Eduvijna Source Intelligence engineering CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    register = subparsers.add_parser("register")
    register.add_argument(
        "--source-type",
        required=True,
        choices=[item.value for item in SourceType],
    )
    register.add_argument("--title", required=True)
    register.add_argument(
        "--trust-tier",
        required=True,
        choices=[item.value for item in SourceTrustTier],
    )
    register.add_argument("--authority")
    register.add_argument("--url")
    register.add_argument("--country")
    register.add_argument("--board-or-exam")
    register.add_argument("--academic-year")
    register.add_argument("--copyright-classification")
    register.add_argument("--metadata-json")
    register.add_argument("--actor", default="engineering-cli")

    upload = subparsers.add_parser("ingest-file")
    upload.add_argument("source_id")
    upload.add_argument("path")
    upload.add_argument(
        "--method",
        required=True,
        choices=[
            SourceIngestionMethod.PDF.value,
            SourceIngestionMethod.DOCX.value,
            SourceIngestionMethod.CSV.value,
            SourceIngestionMethod.JSON.value,
        ],
    )
    upload.add_argument("--actor", default="engineering-cli")

    url = subparsers.add_parser("ingest-url")
    url.add_argument("source_id")
    url.add_argument("--url")
    url.add_argument("--actor", default="engineering-cli")

    manual = subparsers.add_parser("ingest-manual")
    manual.add_argument("source_id")
    manual.add_argument("--metadata-json", required=True)
    manual.add_argument("--note")
    manual.add_argument("--actor", default="engineering-cli")

    for name in ("extract", "diff", "validate", "approve", "activate", "inspect"):
        command = subparsers.add_parser(name)
        command.add_argument("id")
        if name in {"extract", "diff", "validate", "approve", "activate"}:
            command.add_argument("--actor", default="engineering-cli")

    reject = subparsers.add_parser("reject")
    reject.add_argument("id")
    reject.add_argument("--reason", required=True)
    reject.add_argument("--actor", default="engineering-cli")

    retry = subparsers.add_parser("retry")
    retry.add_argument("id")
    retry.add_argument("--actor", default="engineering-cli")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    session = session_factory()()
    service = SourceIntelligenceService(session)
    try:
        if args.command == "register":
            source = service.register_source(
                SourceRegistrationInput(
                    source_type=SourceType(args.source_type),
                    title=args.title,
                    url=args.url,
                    authority=args.authority,
                    country=args.country,
                    board_or_exam=args.board_or_exam,
                    academic_year=args.academic_year,
                    copyright_classification=args.copyright_classification,
                    trust_tier=SourceTrustTier(args.trust_tier),
                    metadata_json=_json(args.metadata_json),
                ),
                actor_id=args.actor,
            )
            print(source.id)
            return

        if args.command == "ingest-file":
            path = Path(args.path)
            revision = service.ingest_upload(
                args.source_id,
                method=SourceIngestionMethod(args.method),
                content=path.read_bytes(),
                filename=path.name,
                actor_id=args.actor,
            )
            print(revision.id)
            return

        if args.command == "ingest-url":
            revision = service.ingest_url(
                args.source_id,
                url=args.url,
                actor_id=args.actor,
            )
            print(revision.id)
            return

        if args.command == "ingest-manual":
            revision = service.ingest_manual(
                args.source_id,
                ManualSourceRevisionInput(
                    metadata=_json(args.metadata_json),
                    note=args.note,
                ),
                actor_id=args.actor,
            )
            print(revision.id)
            return

        if args.command == "extract":
            print(service.extract_revision(args.id, actor_id=args.actor).id)
        elif args.command == "diff":
            print(service.create_diff(args.id, actor_id=args.actor).id)
        elif args.command == "validate":
            print(service.validate_revision(args.id, actor_id=args.actor).model_dump_json())
        elif args.command == "approve":
            print(service.approve_revision(args.id, actor_id=args.actor).id)
        elif args.command == "activate":
            print(service.activate_revision(args.id, actor_id=args.actor).id)
        elif args.command == "reject":
            print(
                service.reject_revision(
                    args.id,
                    actor_id=args.actor,
                    reason=args.reason,
                ).id
            )
        elif args.command == "retry":
            print(service.retry_revision(args.id, actor_id=args.actor).id)
        elif args.command == "inspect":
            source = session.get(Source, args.id)
            if source is None:
                revision = session.get(SourceRevision, args.id)
                if revision is None:
                    raise SystemExit("source or revision not found")
                source = revision.source
            _print_source(source, session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
