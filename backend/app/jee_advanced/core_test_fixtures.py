"""Test-only helpers for D12-CORE seed evidence (never production IIT/JAB claims)."""

from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy.orm import Session

from app.jee_advanced.constants import (
    EDUVIJNA_DERIVED_TOPIC_GROUP,
    MATHEMATICS_SUBJECT,
    SOURCE_SLOT_BROCHURE,
)
from app.jee_advanced.source_registry import JEE_ADVANCED_2026_SOURCE_SLOTS, _find_slot_source
from app.models import Question, QuestionOption
from app.models.enums import (
    QuestionOrigin,
    QuestionStatus,
    QuestionType,
    SourceIngestionMethod,
    SourceRevisionStatus,
    SourceTrustTier,
    SourceType,
)
from app.schemas.source_intelligence import SourceRegistrationInput
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage


def _simple_pdf_bytes(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    stream = DecodedStreamObject()
    safe_text = text.replace("(", "[").replace(")", "]")
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({safe_text}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def approve_slot_with_test_pdf(
    session: Session,
    slot_id: str,
    *,
    actor_id: str = "founder-curator",
) -> str:
    """Ingest + activate one slot with a labeled synthetic PDF for CORE adversarial tests."""

    storage = session.info.get("jee_core_storage")
    if storage is None:
        storage = LocalSourceStorage(Path("/tmp/eduvijna-d12-core-private"))
    service = SourceIntelligenceService(session, storage=storage)
    slot_meta = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if s.slot_id == slot_id)
    existing = _find_slot_source(session, slot_id)
    if existing is not None:
        source = existing
    else:
        source = service.register_source(
            SourceRegistrationInput(
                source_type=SourceType.OFFICIAL_EXAM_BULLETIN,
                title=slot_meta.title,
                url=slot_meta.discovery_url,
                authority="Synthetic Test Authority",
                country="IN",
                board_or_exam="jee_advanced",
                academic_year="2026",
                trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
                metadata_json={
                    "slot_id": slot_id,
                    "jee_advanced_slot": True,
                    "d12_core_test_fixture": True,
                },
            ),
            actor_id=actor_id,
            request_id=f"core-fixture-{slot_id}",
        )
        session.flush()
    content = _simple_pdf_bytes(f"CORE-TEST-{slot_id}")
    revision = service.ingest_upload(
        str(source.id),
        method=SourceIngestionMethod.PDF,
        content=content,
        filename=f"{slot_id}.pdf",
        actor_id=actor_id,
        request_id=f"core-stage-{slot_id}",
    )
    service.extract_revision(str(revision.id), actor_id=actor_id)
    service.create_diff(str(revision.id), actor_id=actor_id)
    validation = service.validate_revision(str(revision.id), actor_id=actor_id)
    if not validation.valid:
        raise RuntimeError(f"fixture validation failed for {slot_id}")
    service.approve_revision(str(revision.id), actor_id=actor_id)
    active = service.activate_revision(str(revision.id), actor_id=actor_id)
    if active.status != SourceRevisionStatus.ACTIVE.value:
        raise RuntimeError(f"fixture activation failed for {slot_id}")
    session.commit()
    return str(active.id)


def seed_all_core_source_slots(session: Session) -> list[str]:
    return [
        approve_slot_with_test_pdf(session, slot.slot_id)
        for slot in JEE_ADVANCED_2026_SOURCE_SLOTS
    ]


def seed_persisted_math_questions(
    session: Session,
    *,
    organization_id: str,
    institution_id: str,
    exam_version_id: str,
    math_count: int = 10,
    algebra_count: int = 10,
) -> list[str]:
    created: list[str] = []
    for i in range(math_count):
        q = Question(
            external_code=f"core-math-{i}",
            origin_type=QuestionOrigin.GENERATED.value,
            exam_version_id=exam_version_id,
            question_type=QuestionType.SINGLE_CHOICE.value,
            stem_text=f"CORE test math stem {i}",
            answer_json={"option_key": "A"},
            status=QuestionStatus.APPROVED.value,
            metadata_json={
                "d12_core_test_fixture": True,
                "organization_id": organization_id,
                "institution_id": institution_id,
                "subject_code": MATHEMATICS_SUBJECT,
                "topic_group": "calculus",
                "day6_validation_audit_id": f"audit-math-{i}",
                "day6_solver_evidence_id": f"solver-math-{i}",
            },
        )
        q.options.append(
            QuestionOption(option_key="A", text="A", is_correct=True, sequence=1)
        )
        session.add(q)
        session.flush()
        created.append(str(q.id))

    for i in range(algebra_count):
        q = Question(
            external_code=f"core-alg-{i}",
            origin_type=QuestionOrigin.GENERATED.value,
            exam_version_id=exam_version_id,
            question_type=QuestionType.SINGLE_CHOICE.value,
            stem_text=f"CORE test algebra stem {i}",
            answer_json={"option_key": "B"},
            status=QuestionStatus.APPROVED.value,
            metadata_json={
                "d12_core_test_fixture": True,
                "organization_id": organization_id,
                "institution_id": institution_id,
                "subject_code": MATHEMATICS_SUBJECT,
                "topic_group": EDUVIJNA_DERIVED_TOPIC_GROUP,
                "day6_validation_audit_id": f"audit-alg-{i}",
                "day6_solver_evidence_id": f"solver-alg-{i}",
            },
        )
        q.options.append(
            QuestionOption(option_key="B", text="B", is_correct=True, sequence=1)
        )
        session.add(q)
        session.flush()
        created.append(str(q.id))

    session.commit()
    return created


def seed_minimal_brochure_only(session: Session) -> str:
    return approve_slot_with_test_pdf(session, SOURCE_SLOT_BROCHURE)
