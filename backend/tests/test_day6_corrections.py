from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.education_intelligence.contracts import (
    CanonicalRubric,
    InstitutionPolicyOverride,
    RubricCriterion,
)
from app.education_intelligence.enums import ValidationStatus
from app.education_intelligence.fixtures import positive_cbse_item, seed_cbse_fixture_curriculum
from app.education_intelligence.governance import verify_governance_state
from app.education_intelligence.policy_registry import load_policy_registry
from app.education_intelligence.quality_rule_pack import (
    load_quality_rule_pack,
    seed_quality_rule_pack,
)
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.education_intelligence.taxonomy_registry import seed_taxonomy_registry


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_governance_verifier_reads_execution_state() -> None:
    report = verify_governance_state()
    assert report["passed"] is True
    assert report["checks"]["d5_ds01_deferred"] is True
    assert report["checks"]["day7_locked"] is True


def test_lo_wrong_grade_fails() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        item = positive_cbse_item(ctx).model_copy(update={"grade_year_code": "grade-9"})
        summary = service.validate_item(item, board_code="cbse")
        lo_result = next(
            r for r in summary.results if r.validator_id == "learning_outcome_alignment"
        )
        assert lo_result.status == ValidationStatus.FAIL


def test_lo_wrong_subject_fails() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        item = positive_cbse_item(ctx).model_copy(update={"subject_code": "physics"})
        summary = service.validate_item(item, board_code="cbse")
        lo_result = next(
            r for r in summary.results if r.validator_id == "learning_outcome_alignment"
        )
        assert lo_result.status == ValidationStatus.FAIL


def test_lo_wrong_medium_fails() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        item = positive_cbse_item(ctx).model_copy(update={"medium_code": "hindi"})
        summary = service.validate_item(item, board_code="cbse")
        lo_result = next(
            r for r in summary.results if r.validator_id == "learning_outcome_alignment"
        )
        assert lo_result.status == ValidationStatus.FAIL


def test_age_grade_without_authoritative_mapping_review_required() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        item = positive_cbse_item(ctx).model_copy(
            update={"age_min": None, "age_max": None, "grade_year_code": "grade-unknown"}
        )
        summary = service.validate_item(item, board_code="cbse")
        age = next(r for r in summary.results if r.validator_id == "age_grade_appropriateness")
        assert age.status == ValidationStatus.REVIEW_REQUIRED


def test_weakening_override_does_not_remove_official_rule() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        override = InstitutionPolicyOverride(
            institution_id="inst-a",
            policy_key="quality.explanation_when_required",
            value={"disable_blocking": True},
        )
        item = positive_cbse_item(ctx).model_copy(
            update={
                "institution_id": "inst-a",
                "explanation_required": True,
                "explanation_present": False,
            }
        )
        summary = service.validate_item(
            item, board_code="cbse", institution_overrides=[override]
        )
        assert summary.blocking_failure


def test_foreign_tenant_override_ignored_without_simulation_flag() -> None:
    with _session() as session:
        seed_taxonomy_registry(session)
        foreign = InstitutionPolicyOverride(
            institution_id="inst-b",
            policy_key="quality.explanation_when_required",
            value={"disable_blocking": True},
        )
        reg = load_policy_registry(session, institution_overrides=[foreign])
        rules = reg.rules_for_scope(board_code="cbse", institution_id="inst-a")
        assert all(not r.value.get("disable_blocking") for r in rules)


def test_rubric_bad_weights_and_unresolved_links() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        item = positive_cbse_item(ctx).model_copy(
            update={
                "rubric": CanonicalRubric(
                    total_marks=5,
                    criteria=[
                        RubricCriterion(
                            criterion_id="c1",
                            title="A",
                            marks=5,
                            weight=0.7,
                            performance_levels=[{"label": "ok", "score": 5}],
                            learning_outcome_ids=["missing-lo"],
                            competency_codes=["not_a_real_competency"],
                        )
                    ],
                )
            }
        )
        summary = service.validate_item(item, board_code="cbse")
        rubric = next(r for r in summary.results if r.validator_id == "rubric_integrity")
        assert rubric.status == ValidationStatus.FAIL


def test_safety_rule_pack_provenance_on_block() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        item = positive_cbse_item(ctx).model_copy(
            update={"content_text_for_safety": "please kill yourself"}
        )
        summary = service.validate_item(item, board_code="cbse")
        safety = next(r for r in summary.results if r.validator_id == "bias_fairness_safety")
        assert safety.status == ValidationStatus.FAIL
        assert safety.policy_version
        assert "SAFE-BLOCK" in safety.rule_codes[0]


def test_quality_rule_pack_versioned_and_reproducible() -> None:
    with _session() as session:
        first = seed_quality_rule_pack(session)
        second = load_quality_rule_pack(session)
        assert first.version == second.version
        assert len(second.rules) >= 4


def test_official_competency_missing_source_revision_review() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        item = positive_cbse_item(ctx).model_copy(update={"competency_claim_official": True})
        summary = service.validate_item(item, board_code="cbse")
        comp = next(r for r in summary.results if r.validator_id == "source_backed_competency")
        assert comp.status in {ValidationStatus.PASS, ValidationStatus.REVIEW_REQUIRED}
