from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.education_intelligence.fixtures import seed_cbse_fixture_curriculum
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.models.education_intelligence import PolicyRegistryEntry, ValidationAuditRun
from app.models.education_intelligence import ValidationAuditRun as _Run
from app.paper_distribution.contracts import (
    DistributionTarget,
    PaperDistributionRequest,
    PaperItemInput,
)
from app.paper_distribution.enums import PaperDistributionIssueCode
from app.paper_distribution.evaluator import evaluate_paper_distribution_with_session
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    PAPER_TARGET_REGISTRY_KEY,
    ensure_paper_target_policy_configured,
)
from app.paper_distribution.trusted_validation import PaperDay6TrustContext


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'd10-r7.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _persist_day6_passing_run(session: Session) -> tuple[str, dict]:
    ctx = seed_cbse_fixture_curriculum(session)
    session.flush()
    from app.education_intelligence.fixtures import positive_cbse_item

    item = positive_cbse_item(ctx)
    service = EducationIntelligenceValidationService(session)
    summary = service.validate_item(item, board_code="cbse", persist=True, actor_id="actor-1")
    session.flush()
    record = session.scalars(
        select(_Run).where(_Run.run_id == summary.run_id)
    ).first()
    assert record is not None
    validated = (record.metadata_json or {}).get("validated_items", [])[0]
    return str(record.id), validated


def test_missing_day6_input_hash_fails_production(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ensure_paper_target_policy_configured(session)
    run_id, validated = _persist_day6_passing_run(session)
    session.commit()
    paper = PaperDistributionRequest(
        paper_id="no-hash",
        requested_count=1,
        items=[
            PaperItemInput(
                item_id=str(validated["item_id"]),
                marks=1.0,
                cognitive_level=str(validated.get("declared_cognitive_level")),
                competency_codes=list(validated.get("competency_codes") or []),
                day6_validated=True,
            )
        ],
    )
    result = evaluate_paper_distribution_with_session(
        session,
        paper,
        day6_trust=PaperDay6TrustContext.from_validation_run(run_id),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(),
    )
    assert PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION in result.issue_codes


def test_blocking_day6_run_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ensure_paper_target_policy_configured(session)
    run_id, validated = _persist_day6_passing_run(session)
    record = session.get(ValidationAuditRun, run_id)
    assert record is not None
    record.blocking_failure = True
    session.commit()
    paper = PaperDistributionRequest(
        paper_id="blocking",
        requested_count=1,
        items=[
            PaperItemInput(
                item_id=str(validated["item_id"]),
                marks=1.0,
                cognitive_level=str(validated.get("declared_cognitive_level")),
                competency_codes=list(validated.get("competency_codes") or []),
                day6_validated=True,
                metadata_json={
                    "day6_input_hash": validated["input_hash"],
                    "curriculum_version_id": validated.get("curriculum_version_id"),
                    "grade_year_code": validated.get("grade_year_code"),
                    "medium_code": validated.get("medium_code"),
                    "subject_code": validated.get("subject_code"),
                    "learning_outcome_ids": list(validated.get("learning_outcome_ids") or []),
                },
            )
        ],
    )
    result = evaluate_paper_distribution_with_session(
        session,
        paper,
        day6_trust=PaperDay6TrustContext.from_validation_run(run_id),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(),
    )
    assert PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION in result.issue_codes


def test_revoked_target_policy_stays_revoked(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ensure_paper_target_policy_configured(session)
    row = session.scalar(
        select(PolicyRegistryEntry).where(
            PolicyRegistryEntry.registry_key == PAPER_TARGET_REGISTRY_KEY,
            PolicyRegistryEntry.version == PAPER_TARGET_POLICY_VERSION,
        )
    )
    assert row is not None
    row.status = "revoked"
    session.commit()
    run_id, validated = _persist_day6_passing_run(session)
    paper = PaperDistributionRequest(
        paper_id="policy",
        requested_count=1,
        target_policy_version=PAPER_TARGET_POLICY_VERSION,
        items=[
            PaperItemInput(
                item_id=str(validated["item_id"]),
                marks=1.0,
                cognitive_level=str(validated.get("declared_cognitive_level")),
                competency_codes=list(validated.get("competency_codes") or []),
                day6_validated=True,
                metadata_json={
                    "day6_input_hash": validated["input_hash"],
                    "curriculum_version_id": validated.get("curriculum_version_id"),
                    "grade_year_code": validated.get("grade_year_code"),
                    "medium_code": validated.get("medium_code"),
                    "subject_code": validated.get("subject_code"),
                    "learning_outcome_ids": list(validated.get("learning_outcome_ids") or []),
                },
            )
        ],
        cognitive_targets=[
            DistributionTarget(dimension="cognitive", key="remember", exact_percent=100.0)
        ],
    )
    result = evaluate_paper_distribution_with_session(
        session,
        paper,
        day6_trust=PaperDay6TrustContext.from_validation_run(run_id),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(),
    )
    assert (
        PaperDistributionIssueCode.UNSUPPORTED_TAXONOMY in result.issue_codes
        or PaperDistributionIssueCode.TARGET_INFEASIBLE in result.issue_codes
    )
    still_revoked = session.scalar(
        select(PolicyRegistryEntry).where(PolicyRegistryEntry.id == row.id)
    )
    assert still_revoked is not None
    assert still_revoked.status == "revoked"


def test_long_institution_uuid_audit_run_id(tmp_path: Path) -> None:
    session = _session(tmp_path)
    inst = str(uuid4())
    request = PaperDistributionRequest(
        paper_id="uuid-inst",
        requested_count=1,
        items=[
            PaperItemInput(
                item_id="q1",
                marks=1.0,
                cognitive_level="remember",
                competency_codes=["knowledge"],
                day6_validated=True,
            )
        ],
    )
    result = evaluate_paper_distribution_with_session(
        session,
        request,
        day6_trust=PaperDay6TrustContext.synthetic_fixture_harness(),
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
        execution_context=PaperExecutionContext(institution_id=inst, actor_id="actor"),
    )
    assert result.audit_ref is not None
    record = session.get(ValidationAuditRun, result.audit_ref)
    assert record is not None
    assert len(record.run_id) <= 64
