"""Day 6 acceptance-closure adversarial tests (D6-A06)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.education_intelligence.contracts import QuestionOptionInput
from app.education_intelligence.enums import ValidationStatus
from app.education_intelligence.fixtures import positive_cbse_item, seed_cbse_fixture_curriculum
from app.education_intelligence.policy_registry import (
    V1_POLICY_VERSION,
    load_policy_registry,
    seed_policy_registry,
)
from app.education_intelligence.quality_rule_pack import (
    load_quality_rule_pack,
    seed_quality_rule_pack,
)
from app.education_intelligence.registry_versions import RegistryVersionNotFound
from app.education_intelligence.safety_rules import (
    V1_SAFETY_RULES_VERSION,
    load_safety_rule_pack,
)
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.education_intelligence.taxonomy_registry import (
    load_taxonomy_registry,
    seed_taxonomy_registry,
)
from app.models.curriculum import LearningOutcome
from app.models.education_intelligence import PolicyRegistryEntry
from app.models.source import SourceRevision


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _set_lo_revision_status(session: Session, lo_id: str, status: str) -> None:
    lo = session.get(LearningOutcome, lo_id)
    assert lo and lo.source_revision_id
    base = session.get(SourceRevision, lo.source_revision_id)
    assert base
    rev = SourceRevision(
        source_id=base.source_id,
        revision_number=base.revision_number + 1,
        checksum=("a" * 63) + str(len(status)),
        source_snapshot_checksum=("b" * 63) + str(len(status)),
        ingestion_method="manual",
        content_type="text/plain",
        byte_size=1,
        retrieved_at=datetime.now(UTC),
        status=status,
        extraction_status="succeeded",
        extracted_checksum=("a" * 63) + str(len(status)),
    )
    session.add(rev)
    session.flush()
    lo.source_revision_id = rev.id


def test_official_competency_wrong_grade_medium_subject() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        base = positive_cbse_item(ctx).model_copy(update={"competency_claim_official": True})
        for field, value in (
            ("grade_year_code", "grade-9"),
            ("medium_code", "telugu"),
            ("subject_code", "physics"),
        ):
            summary = service.validate_item(
                base.model_copy(update={field: value}), board_code="cbse"
            )
            comp = next(
                r for r in summary.results if r.validator_id == "source_backed_competency"
            )
            assert comp.status == ValidationStatus.FAIL


def test_unsafe_option_text_triggers_safety_validator() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        item = positive_cbse_item(ctx).model_copy(
            update={
                "options": [
                    QuestionOptionInput(
                        option_key="A", text="please kill yourself", is_correct=False
                    ),
                    QuestionOptionInput(option_key="B", text="12", is_correct=True),
                ]
            }
        )
        safety = next(
            r
            for r in service.validate_item(item, board_code="cbse").results
            if r.validator_id == "bias_fairness_safety"
        )
        assert safety.status == ValidationStatus.FAIL


def test_structural_duplicate_key_multiple_zero_correct() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        dup_key = positive_cbse_item(ctx).model_copy(
            update={
                "options": [
                    QuestionOptionInput(option_key="A", text="1", is_correct=False),
                    QuestionOptionInput(option_key="A", text="2", is_correct=True),
                ]
            }
        )
        multi = positive_cbse_item(ctx).model_copy(
            update={
                "options": [
                    QuestionOptionInput(option_key="A", text="1", is_correct=True),
                    QuestionOptionInput(option_key="B", text="2", is_correct=True),
                ]
            }
        )
        zero = positive_cbse_item(ctx).model_copy(
            update={
                "options": [
                    QuestionOptionInput(option_key="A", text="1", is_correct=False),
                    QuestionOptionInput(option_key="B", text="2", is_correct=False),
                ]
            }
        )
        for item, code in (
            (dup_key, "STRUCT-010"),
            (multi, "STRUCT-009"),
            (zero, "STRUCT-004"),
        ):
            struct = next(
                r
                for r in service.validate_item(item, board_code="cbse").results
                if r.validator_id == "structural_clarity"
            )
            assert struct.status == ValidationStatus.FAIL
            assert code in struct.rule_codes


def test_safety_rule_metadata_drives_blocking() -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        seed_policy_registry(session)
        row = session.scalar(select(PolicyRegistryEntry))
        assert row
        payload = dict(row.payload_json)
        payload["safety_rules"] = [
            {
                "rule_code": "SAFE-ADVISORY-TEST",
                "pattern": "fixture advisory phrase",
                "severity": "advisory",
                "blocking": False,
            }
        ]
        payload["safety_rules_version"] = "safety-rules-test-v1"
        row.payload_json = payload
        session.commit()
        service = EducationIntelligenceValidationService(session)
        item = positive_cbse_item(ctx).model_copy(
            update={"stem_text": "fixture advisory phrase in stem"}
        )
        safety = next(
            r
            for r in service.validate_item(item, board_code="cbse").results
            if r.validator_id == "bias_fairness_safety"
        )
        assert safety.status == ValidationStatus.WARN
        assert safety.blocking is False
        assert "SAFE-ADVISORY-TEST" in safety.rule_codes


def test_missing_exact_registry_versions_fail_closed() -> None:
    with _session() as session:
        seed_taxonomy_registry(session)
        seed_quality_rule_pack(session)
        seed_policy_registry(session)
        session.commit()
        with pytest.raises(RegistryVersionNotFound):
            load_taxonomy_registry(session, version="missing-taxonomy-version")
        with pytest.raises(RegistryVersionNotFound):
            load_policy_registry(session, version="missing-policy-version")
        with pytest.raises(RegistryVersionNotFound):
            load_quality_rule_pack(session, version="missing-quality-pack")


def test_historical_safety_version_replay() -> None:
    with _session() as session:
        seed_policy_registry(session)
        v1 = load_safety_rule_pack(
            session, V1_POLICY_VERSION, safety_rules_version=V1_SAFETY_RULES_VERSION
        )
        session.add(
            PolicyRegistryEntry(
                registry_key="v1",
                version="education-policy-v1.1-fixture",
                status="active",
                payload_json={
                    "rules": [],
                    "institution_overrides": [],
                    "safety_rules_version": "safety-rules-v2-fixture",
                    "safety_rules": [
                        {
                            "rule_code": "SAFE-V2",
                            "pattern": "v2-only-pattern",
                            "severity": "safety",
                            "blocking": True,
                        }
                    ],
                },
            )
        )
        session.commit()
        replay = load_safety_rule_pack(
            session, V1_POLICY_VERSION, safety_rules_version=V1_SAFETY_RULES_VERSION
        )
        assert replay.version == v1.version
        assert replay.policy_version == V1_POLICY_VERSION
        with pytest.raises(RegistryVersionNotFound):
            load_safety_rule_pack(
                session, V1_POLICY_VERSION, safety_rules_version="missing-safety-version"
            )


@pytest.mark.parametrize("status", ["validated", "approved", "superseded"])
def test_non_active_source_revision_cannot_authorize_lo(status: str) -> None:
    with _session() as session:
        ctx = seed_cbse_fixture_curriculum(session)
        _set_lo_revision_status(session, ctx["learning_outcome_id"], status)
        session.commit()
        service = EducationIntelligenceValidationService(session)
        lo = next(
            r
            for r in service.validate_item(positive_cbse_item(ctx), board_code="cbse").results
            if r.validator_id == "learning_outcome_alignment"
        )
        assert lo.status == ValidationStatus.FAIL


def test_day6_docs_exclude_paper_distribution_portable() -> None:
    relative = Path("docs/execution/D06-EDUCATION-INTELLIGENCE-VALIDATORS.md")
    roots = (
        Path(__file__).resolve().parents[2],  # repository checkout
        Path(__file__).resolve().parents[1],  # /app in the backend image
        Path.cwd(),
    )
    doc = next((root / relative for root in roots if (root / relative).is_file()), None)
    assert doc is not None, f"Day 6 execution spec not found under: {roots}"
    text = doc.read_text(encoding="utf-8")
    assert "assessment-set cognitive distribution validator" not in text
    assert "Day 10" in text
