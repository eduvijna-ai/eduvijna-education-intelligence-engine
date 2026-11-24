from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.ca_imat_eapcet.constants import CA_FOUNDATION_PACK_CODE
from app.ca_imat_eapcet.content_validation import (
    _independent_solve,
    derive_content_fingerprint,
    validate_and_bind_question_ref,
)
from app.ca_imat_eapcet.contracts import AllocateRequest, QuestionRef
from app.ca_imat_eapcet.eapcet_bilingual import evaluate_bilingual_pair
from app.ca_imat_eapcet.enums import Day14ProfileKind, Day14SourceTrustMode, PlanVerdict
from app.ca_imat_eapcet.exam_profile import ensure_synthetic_demo_versions
from app.ca_imat_eapcet.persistence_bridge import attempt_canonical_issuance
from app.ca_imat_eapcet.practice_service import Day14PracticeService
from app.ca_imat_eapcet.source_registry import ca_icai_evidence_ready
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys


def test_ca_qa_decimal_15_percent_of_201_diagnostic() -> None:
    stem = "CA_QA: What is 15% of 201?"
    target = str((Decimal(201) * Decimal(15) / Decimal(100)).quantize(Decimal("0.01")))
    options = {"A": "29", "B": target, "C": "31", "D": "32"}
    assert _independent_solve(stem, options) == "B"


def test_academic_validation_bind_contained() -> None:
    stem = "CA_QA: What is 15% of 40?"
    options = {"A": "4", "B": "6", "C": "7", "D": "8"}
    fp = derive_content_fingerprint(stem_text=stem, options=options, correct_key="B")
    q = QuestionRef(
        question_id="x",
        paper_or_section="paper3",
        fingerprint=fp,
        correct_key="B",
        marks_if_correct=1.0,
        marks_if_incorrect=0.0,
        stem_text=stem,
        options=options,
        independently_validated=True,
    )
    _, verdict, _ = validate_and_bind_question_ref(q, options_required=4)
    assert verdict is PlanVerdict.NOT_READY


def test_bilingual_arbitrary_evidence_still_review() -> None:
    v = evaluate_bilingual_pair(
        "english_telugu",
        english="What is force?",
        vernacular="బలం",
        equivalence_evidence_id="forged-id",
    )
    assert v.verdict == PlanVerdict.REVIEW_REQUIRED


def test_source_registry_fail_closed_without_curator_chain() -> None:
    assert ca_icai_evidence_ready(None) is False


def test_issuance_cross_tenant_contained() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ca_ver, _, _ = ensure_synthetic_demo_versions(session)
        alloc = Day14PracticeService().allocate(
            AllocateRequest(
                exam_pack_code=CA_FOUNDATION_PACK_CODE,
                profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
                trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
                paper_or_section="paper3_quantitative_aptitude",
                requested_count=2,
            )
        )
        assert alloc.delivered_count == 0
        replay = attempt_canonical_issuance(
            session=session,
            questions=[],
            organization_id="org-b",
            institution_id="inst-a",
            exam_version_id=str(ca_ver.id),
            source_version="synthetic_demo",
            idempotency_key="bound-key",
        )
        assert replay.verdict == PlanVerdict.NOT_READY
        assert replay.committed is False