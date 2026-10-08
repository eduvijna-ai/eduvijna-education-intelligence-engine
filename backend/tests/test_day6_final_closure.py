from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.education_intelligence.contracts import (
    DifficultyEvidence,
    InstitutionPolicyOverride,
    QuestionOptionInput,
)
from app.education_intelligence.enums import ValidationStatus
from app.education_intelligence.fixtures import positive_cbse_item, seed_cbse_fixture_curriculum
from app.education_intelligence.policy_registry import V1_POLICY_VERSION, load_policy_registry
from app.education_intelligence.quality_rule_pack import (
    DEFAULT_QUALITY_RULES,
    V1_QUALITY_PACK_VERSION,
    V2_QUALITY_PACK_VERSION,
    load_quality_rule_pack,
)
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.education_intelligence.taxonomy_registry import (
    V1_TAXONOMY_VERSION,
    load_taxonomy_registry,
)
from app.education_intelligence.validators.rubric_policy_safety import _safety_scan_text
from app.models.curriculum import LearningOutcome
from app.models.education_intelligence import EducationalQualityRulePack, TaxonomyRegistryEntry
from app.models.source import SourceRevision


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _revision_with_status(session: Session, lo_id: str, status: str) -> SourceRevision:
    lo = session.get(LearningOutcome, lo_id)
    assert lo and lo.source_revision_id
    base = session.get(SourceRevision, lo.source_revision_id)
    assert base
    rev = SourceRevision(
        source_id=base.source_id,
        revision_number=base.revision_number + 10,
        checksum="a" * 64,
        source_snapshot_checksum="b" * 64,
        ingestion_method="manual",
        content_type="text/plain",
        byte_size=1,
        retrieved_at=datetime.now(UTC),
        status=status,
        extraction_status="succeeded",
        extracted_checksum="a" * 64,
    )
    session.add(rev)
    session.flush()
    lo.source_revision_id = rev.id
    return rev


def test_lo_active_source_revision_passes() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        summary = service.validate_item(positive_cbse_item(ctx), board_code="cbse")
        lo = next(r for r in summary.results if r.validator_id == "learning_outcome_alignment")
        assert lo.status == ValidationStatus.PASS


def test_lo_staged_revision_fails() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        _revision_with_status(session, ctx["learning_outcome_id"], "staged")
        session.commit()
        service = EducationIntelligenceValidationService(session)
        lo = next(
            r
            for r in service.validate_item(positive_cbse_item(ctx), board_code="cbse").results
            if r.validator_id == "learning_outcome_alignment"
        )
        assert lo.status == ValidationStatus.FAIL


def test_lo_rejected_failed_superseded_revision_fail() -> None:
    for status in ("rejected", "failed", "superseded"):
        with _session() as session:
            ctx = seed_cbse_fixture_curriculum(session)
            _revision_with_status(session, ctx["learning_outcome_id"], status)
            session.commit()
            service = EducationIntelligenceValidationService(session)
            lo = next(
                r
                for r in service.validate_item(positive_cbse_item(ctx), board_code="cbse").results
                if r.validator_id == "learning_outcome_alignment"
            )
            assert lo.status == ValidationStatus.FAIL


def test_lo_missing_medium_fails() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        item = positive_cbse_item(ctx).model_copy(update={"medium_code": None})
        service = EducationIntelligenceValidationService(session)
        lo = next(
            r
            for r in service.validate_item(item, board_code="cbse").results
            if r.validator_id == "learning_outcome_alignment"
        )
        assert lo.status == ValidationStatus.FAIL


def test_lo_wrong_medium_fails() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        item = positive_cbse_item(ctx).model_copy(update={"medium_code": "telugu"})
        service = EducationIntelligenceValidationService(session)
        lo = next(
            r
            for r in service.validate_item(item, board_code="cbse").results
            if r.validator_id == "learning_outcome_alignment"
        )
        assert lo.status == ValidationStatus.FAIL


def test_official_competency_inactive_revision_fails() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        from sqlalchemy import select

        from app.models.curriculum import Competency

        comp = session.scalars(select(Competency)).first()
        assert comp
        base = session.get(SourceRevision, comp.source_revision_id)
        assert base
        rev = SourceRevision(
            source_id=base.source_id,
            revision_number=base.revision_number + 99,
            checksum="f" * 64,
            source_snapshot_checksum="e" * 64,
            ingestion_method="manual",
            content_type="text/plain",
            byte_size=1,
            retrieved_at=datetime.now(UTC),
            status="staged",
            extraction_status="succeeded",
            extracted_checksum="c" * 64,
        )
        session.add(rev)
        session.flush()
        comp.source_revision_id = rev.id
        session.commit()
        service = EducationIntelligenceValidationService(session)
        item = positive_cbse_item(ctx).model_copy(update={"competency_claim_official": True})
        comp_r = next(
            r
            for r in service.validate_item(item, board_code="cbse").results
            if r.validator_id == "source_backed_competency"
        )
        assert comp_r.status == ValidationStatus.FAIL


def test_authoritative_age_band_mismatch_fails() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        item = positive_cbse_item(ctx).model_copy(update={"age_min": 2, "age_max": 4})
        service = EducationIntelligenceValidationService(session)
        age = next(
            r
            for r in service.validate_item(item, board_code="cbse").results
            if r.validator_id == "age_grade_appropriateness"
        )
        assert age.status == ValidationStatus.FAIL


def test_caller_metadata_cannot_forge_age_authority() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        item = positive_cbse_item(ctx).model_copy(
            update={
                "grade_year_code": "grade-unknown",
                "metadata_json": {"authoritative_age_mapping": True},
            }
        )
        service = EducationIntelligenceValidationService(session)
        age = next(
            r
            for r in service.validate_item(item, board_code="cbse").results
            if r.validator_id == "age_grade_appropriateness"
        )
        assert age.status == ValidationStatus.REVIEW_REQUIRED


def test_foreign_tenant_same_policy_key_no_false_leakage() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        foreign = InstitutionPolicyOverride(
            institution_id="inst-b",
            policy_key="quality.explanation_when_required",
            value={"disable_blocking": True},
        )
        service = EducationIntelligenceValidationService(session)
        item = positive_cbse_item(ctx).model_copy(update={"institution_id": "inst-a"})
        summary = service.validate_item(item, board_code="cbse", institution_overrides=[foreign])
        inst = next(
            r for r in summary.results if r.validator_id == "institution_override_boundary"
        )
        assert inst.status == ValidationStatus.PASS
        assert summary.aggregate_status == ValidationStatus.PASS


def test_safety_scans_stem_and_supplemental() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        item = positive_cbse_item(ctx).model_copy(
            update={
                "stem_text": "please kill yourself",
                "content_text_for_safety": "benign supplemental",
            }
        )
        assert "kill yourself" in _safety_scan_text(item)


def test_structural_single_choice_defects() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        blank = positive_cbse_item(ctx).model_copy(
            update={
                "options": [
                    QuestionOptionInput(option_key="A", text="", is_correct=True),
                    QuestionOptionInput(option_key="B", text="2", is_correct=False),
                ]
            }
        )
        r_blank = next(
            r
            for r in service.validate_item(blank, board_code="cbse").results
            if r.validator_id == "structural_clarity"
        )
        assert r_blank.status == ValidationStatus.FAIL and "STRUCT-008" in r_blank.rule_codes


def test_difficulty_incomplete_evidence_review() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        item = positive_cbse_item(ctx).model_copy(
            update={"difficulty_evidence": DifficultyEvidence(cognitive_demand_band=2)}
        )
        service = EducationIntelligenceValidationService(session)
        diff = next(
            r
            for r in service.validate_item(item, board_code="cbse").results
            if r.validator_id == "difficulty_profile"
        )
        assert diff.status == ValidationStatus.REVIEW_REQUIRED


def test_historical_version_replay() -> None:
    with _session() as session:
        seed_cbse_fixture_curriculum(session)
        session.commit()
        session.add(
            TaxonomyRegistryEntry(
                registry_key="v1",
                version="cognitive-competency-v1.1-fixture",
                status="active",
                payload_json={
                    "cognitive": {"remember": {"label": "Remember", "order": 1, "aliases": []}},
                    "competencies": {},
                },
            )
        )
        session.add(
            EducationalQualityRulePack(
                pack_key="v1",
                version=V2_QUALITY_PACK_VERSION,
                status="active",
                rules_json=DEFAULT_QUALITY_RULES,
                description="fixture v2",
            )
        )
        session.commit()
        v1_tax = load_taxonomy_registry(session, version=V1_TAXONOMY_VERSION)
        v2_tax = load_taxonomy_registry(session, version="cognitive-competency-v1.1-fixture")
        assert v1_tax.version != v2_tax.version
        v1_pack = load_quality_rule_pack(session, version=V1_QUALITY_PACK_VERSION)
        v2_pack = load_quality_rule_pack(session, version=V2_QUALITY_PACK_VERSION)
        assert v1_pack.version != v2_pack.version
        policy_v1 = load_policy_registry(session, version=V1_POLICY_VERSION)
        assert policy_v1.version == V1_POLICY_VERSION


def test_day6_docs_exclude_paper_distribution() -> None:
    text = open("/workspace/docs/execution/D06-EDUCATION-INTELLIGENCE-VALIDATORS.md").read()
    assert "assessment-set cognitive distribution validator" not in text
    assert "Day 10" in text
