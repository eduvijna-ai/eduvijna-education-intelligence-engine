from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
from app.learner_intelligence.contracts import SnapshotItem, SnapshotOption, TrustedActorContext
from app.learner_intelligence.enums import MASTERY_POLICY_VERSION, EligibilityTrustMode
from app.learner_intelligence.snapshot import (
    compute_assessment_fingerprint,
    compute_item_fingerprint,
)
from app.models import Institution, Learner, Organization


def seed_synthetic_tenant(session: Session) -> TrustedActorContext:
    org = Organization(code="d15-org", name="D15 Synthetic Org", active=True)
    session.add(org)
    session.flush()
    inst = Institution(
        organization_id=str(org.id),
        code="d15-inst",
        name="D15 Synthetic Institution",
        active=True,
    )
    session.add(inst)
    session.flush()
    learner = Learner(
        institution_id=str(inst.id),
        external_code="d15-learner-1",
        display_name="Synthetic Learner",
        active=True,
    )
    session.add(learner)
    session.flush()
    return TrustedActorContext(
        organization_id=str(org.id),
        institution_id=str(inst.id),
        learner_id=str(learner.id),
    )


def build_two_item_synthetic_assessment() -> list[SnapshotItem]:
    item1 = SnapshotItem(
        item_sequence=1,
        question_id="q-d15-001",
        stem_text="What is 2 + 2?",
        question_type="single_choice",
        options=[
            SnapshotOption(option_key="A", display_text="3", is_correct=False),
            SnapshotOption(option_key="B", display_text="4", is_correct=True),
            SnapshotOption(option_key="C", display_text="5", is_correct=False),
        ],
        marks_if_correct=Decimal("4"),
        marks_if_incorrect=Decimal("-1"),
        marks_if_blank=Decimal("0"),
        concept_codes=["arithmetic.addition"],
        learning_outcome_ids=["lo-add-v1"],
        competency_codes=["comp-quant"],
        difficulty_band="easy",
        cognitive_level="remember",
        source_version="synthetic@v1",
        content_fingerprint="",
        diagnostic_tags_json=[
            {
                "item_id": "q-d15-001",
                "option_key": "A",
                "is_correct": False,
                "misconception_code": "OFF_BY_ONE_LOW",
                "taxonomy_version": "misconception-taxonomy@v1",
                "validation_status": DiagnosticValidationStatus.PASS.value,
                "evidence_refs": ["synthetic-fixture"],
            }
        ],
    )
    item1 = item1.model_copy(update={"content_fingerprint": compute_item_fingerprint(item1)})
    item2 = SnapshotItem(
        item_sequence=2,
        question_id="q-d15-002",
        stem_text="Solve: 3 + 4",
        question_type="numeric",
        options=[],
        marks_if_correct=Decimal("4"),
        marks_if_incorrect=Decimal("0"),
        numeric_answer="7",
        numeric_tolerance=Decimal("0"),
        concept_codes=["arithmetic.addition"],
        source_version="synthetic@v1",
        content_fingerprint="",
    )
    item2 = item2.model_copy(update={"content_fingerprint": compute_item_fingerprint(item2)})
    return [item1, item2]


SYNTHETIC_HARNESS_PROOF = "synthetic_fixture_v1"
VERIFY_HARNESS_PROOF = "day15_verify_harness"
TRUST_MODE = EligibilityTrustMode.SYNTHETIC_D15_HARNESS
MASTERY_POLICY = MASTERY_POLICY_VERSION


def assessment_content_fingerprint(items: list[SnapshotItem]) -> str:
    return compute_assessment_fingerprint(items)