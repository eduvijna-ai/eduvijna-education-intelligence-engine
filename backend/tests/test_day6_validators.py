from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.day6_verify import build_verification_report
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.education_intelligence.contracts import InstitutionPolicyOverride
from app.education_intelligence.enums import ValidationStatus
from app.education_intelligence.fixtures import (
    adversarial_broken_rubric,
    adversarial_cognitive_mismatch,
    adversarial_invalid_progression,
    adversarial_safety_trigger,
    adversarial_wrong_lo_version,
    positive_cbse_item,
    seed_cbse_fixture_curriculum,
)
from app.education_intelligence.policy_registry import load_policy_registry
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.education_intelligence.taxonomy_registry import (
    load_taxonomy_registry,
    seed_taxonomy_registry,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_positive_item_passes() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        summary = service.validate_item(positive_cbse_item(ctx), board_code="cbse")
        assert summary.aggregate_status == ValidationStatus.PASS
        assert summary.taxonomy_version
        assert summary.policy_version


def test_wrong_curriculum_version_fails() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        summary = service.validate_item(adversarial_wrong_lo_version(ctx), board_code="cbse")
        assert summary.aggregate_status == ValidationStatus.FAIL


def test_cognitive_mismatch_fails_or_warns() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        summary = service.validate_item(adversarial_cognitive_mismatch(ctx), board_code="cbse")
        assert summary.aggregate_status in {ValidationStatus.FAIL, ValidationStatus.WARN}


def test_deterministic_rerun() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        item = positive_cbse_item(ctx)
        first = service.validate_item(item, board_code="cbse")
        second = service.validate_item(item, board_code="cbse")
        assert first.input_hash == second.input_hash
        assert first.aggregate_status == second.aggregate_status
        assert [r.status for r in first.results] == [r.status for r in second.results]


def test_taxonomy_registry_idempotent() -> None:
    with _session() as session:
        first = seed_taxonomy_registry(session)
        second = seed_taxonomy_registry(session)
        assert first.version == second.version
        rows = load_taxonomy_registry(session)
        assert rows.version == first.version


def test_policy_precedence_blocks_institution_weakening() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        item = positive_cbse_item(ctx).model_copy(
            update={
                "institution_id": "inst-a",
                "explanation_required": True,
                "explanation_present": False,
            }
        )
        override = InstitutionPolicyOverride(
            institution_id="inst-a",
            policy_key="quality.explanation_when_required",
            value={"disable_blocking": True},
        )
        summary = service.validate_item(
            item, board_code="cbse", institution_overrides=[override]
        )
        assert summary.blocking_failure


def test_rubric_and_safety_adversarial() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        rubric = service.validate_item(adversarial_broken_rubric(ctx), board_code="cbse")
        safety = service.validate_item(adversarial_safety_trigger(ctx), board_code="cbse")
        assert rubric.aggregate_status == ValidationStatus.FAIL
        assert safety.blocking_failure


def test_cognitive_progression_no_paper_distribution() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        bad = service.validate_item(adversarial_invalid_progression(ctx), board_code="cbse")
        assert bad.aggregate_status == ValidationStatus.FAIL
        good = service.validate_cognitive_progression(["remember", "understand", "apply"])
        assert good.aggregate_status == ValidationStatus.PASS


def test_audit_persistence() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        summary = service.validate_item(positive_cbse_item(ctx), persist=True, board_code="cbse")
        stored = service.get_audit_run(summary.run_id)
        assert stored is not None
        assert stored.input_hash == summary.input_hash


def test_founder_verification_report() -> None:
    with _session() as session:
        report = build_verification_report(session)
        assert report["passed"] is True


def test_evidence_authority_types_distinct() -> None:
    from app.education_intelligence.enums import EvidenceAuthority

    values = {e.value for e in EvidenceAuthority}
    assert "official_curriculum_rule" in values
    assert "teacher_preference" in values
    assert "institution_preference" in values


def test_policy_registry_foreign_override_not_applied() -> None:
    with _session() as session:
        seed_taxonomy_registry(session)
        reg = load_policy_registry(
            session,
            institution_overrides=[
                InstitutionPolicyOverride(
                    institution_id="inst-b",
                    policy_key="quality.explanation_when_required",
                    value={"disable_blocking": True},
                )
            ],
        )
        rules = reg.rules_for_scope(board_code="cbse", institution_id="inst-a")
        assert all("disable_blocking" not in r.value for r in rules)
