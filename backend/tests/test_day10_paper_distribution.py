from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.education_intelligence.taxonomy_registry import TaxonomyRegistry
from app.models.education_intelligence import ValidationAuditRun
from app.paper_distribution.contracts import (
    DistributionTarget,
    PaperDistributionRequest,
    PaperItemInput,
)
from app.paper_distribution.enums import (
    MultiLabelPolicy,
    PaperDistributionIssueCode,
    PaperDistributionVerdict,
)
from app.paper_distribution.evaluator import (
    evaluate_paper_distribution,
    evaluate_paper_distribution_with_session,
)
from app.paper_distribution.fixtures import (
    build_demo_ten_question_paper,
    build_mismatched_target_paper,
)
from app.paper_distribution.trusted_validation import PaperDay6TrustContext

_HARNESS = PaperDay6TrustContext.synthetic_fixture_harness()
_SYNTHETIC = TrustExecutionMode.SYNTHETIC_FIXTURE


def test_demo_paper_matches_20_20_40_10_10() -> None:
    request = build_demo_ten_question_paper()
    result = evaluate_paper_distribution(
        request, taxonomy=TaxonomyRegistry(), day6_trust=_HARNESS,
        execution_mode=_SYNTHETIC,
    )
    assert result.verdict == PaperDistributionVerdict.PASS
    assert result.item_count == 10
    summary = result.cognitive_summary.count_percent
    assert summary["remember"] == 20.0
    assert summary["understand"] == 20.0
    assert summary["apply"] == 40.0
    assert summary["analyze"] == 10.0
    assert summary["evaluate"] == 10.0


def test_single_partial_cognitive_target_passes() -> None:
    request = build_demo_ten_question_paper()
    request = request.model_copy(
        update={
            "cognitive_targets": [
                DistributionTarget(dimension="cognitive", key="remember", exact_percent=20.0),
            ],
            "competency_targets": [],
        }
    )
    result = evaluate_paper_distribution(
        request, taxonomy=TaxonomyRegistry(), day6_trust=_HARNESS,
        execution_mode=_SYNTHETIC,
    )
    assert result.verdict == PaperDistributionVerdict.PASS
    assert result.cognitive_summary.status.value == "pass"


def test_mismatched_target_fails_paper_not_items() -> None:
    base = build_demo_ten_question_paper()
    mismatched = build_mismatched_target_paper(base)
    result = evaluate_paper_distribution(mismatched, taxonomy=TaxonomyRegistry())
    assert result.verdict == PaperDistributionVerdict.FAIL
    assert result.item_count == 10


def test_competency_target_mismatch_fails() -> None:
    request = build_demo_ten_question_paper()
    request = request.model_copy(
        update={
            "competency_targets": [
                DistributionTarget(dimension="competency", key="knowledge", exact_percent=100.0),
            ],
        }
    )
    result = evaluate_paper_distribution(
        request, taxonomy=TaxonomyRegistry(), day6_trust=_HARNESS,
        execution_mode=_SYNTHETIC,
    )
    assert result.verdict == PaperDistributionVerdict.FAIL
    assert result.competency_summary.status.value != "pass"


def test_create_level_rejected() -> None:
    request = build_demo_ten_question_paper()
    items = list(request.items)
    items[0] = items[0].model_copy(update={"cognitive_level": "create"})
    result = evaluate_paper_distribution(
        request.model_copy(update={"items": items}),
        taxonomy=TaxonomyRegistry(),
        day6_trust=_HARNESS,
        execution_mode=_SYNTHETIC,
    )
    assert PaperDistributionIssueCode.CREATE_LEVEL_REJECTED in result.issue_codes


def test_fractional_multi_label_conserves_denominator() -> None:
    request = build_demo_ten_question_paper()
    item = request.items[0].model_copy(
        update={
            "competency_codes": ["knowledge", "application"],
            "primary_competency_code": None,
        }
    )
    updated = request.model_copy(
        update={
            "items": [item],
            "multi_label_policy": MultiLabelPolicy.FRACTIONAL_SPLIT,
            "cognitive_targets": [],
            "competency_targets": [],
        }
    )
    result = evaluate_paper_distribution(
        updated, taxonomy=TaxonomyRegistry(), day6_trust=_HARNESS,
        execution_mode=_SYNTHETIC,
    )
    assert result.competency_summary.fractional_counts.get("knowledge") == 0.5
    assert result.competency_summary.fractional_counts.get("application") == 0.5
    assert sum(result.competency_summary.fractional_counts.values()) == 1.0
    assert result.competency_summary.counts.get("knowledge") is None
    assert result.competency_summary.fractional_counts.get("knowledge") == 0.5


def test_misplaced_target_dimension_fails() -> None:
    request = build_demo_ten_question_paper()
    request = request.model_copy(
        update={
            "cognitive_targets": [
                DistributionTarget(dimension="competency", key="knowledge", exact_percent=100.0),
            ],
            "competency_targets": [],
        }
    )
    result = evaluate_paper_distribution(
        request, taxonomy=TaxonomyRegistry(), day6_trust=_HARNESS,
        execution_mode=_SYNTHETIC,
    )
    assert result.verdict == PaperDistributionVerdict.FAIL
    assert PaperDistributionIssueCode.MALFORMED_TARGET_DIMENSION in result.issue_codes


def test_count_only_without_marks_attributes_items() -> None:
    request = PaperDistributionRequest(
        paper_id="count-only",
        include_mark_weighted=False,
        items=[
            PaperItemInput(
                item_id="q1",
                marks=None,
                cognitive_level="remember",
                competency_codes=["knowledge"],
                primary_competency_code="knowledge",
                day6_validated=True,
            )
        ],
    )
    result = evaluate_paper_distribution(
        request, taxonomy=TaxonomyRegistry(), day6_trust=_HARNESS,
        execution_mode=_SYNTHETIC,
    )
    assert result.verdict == PaperDistributionVerdict.PASS
    assert result.cognitive_summary.fractional_counts.get("remember") == 1.0
    assert result.competency_summary.fractional_counts.get("knowledge") == 1.0


def test_untrusted_day6_assertion_not_pass() -> None:
    request = PaperDistributionRequest(
        paper_id="untrusted-day6",
        items=[
            PaperItemInput(
                item_id="q1",
                cognitive_level="remember",
                competency_codes=["knowledge"],
                primary_competency_code="knowledge",
                day6_validated=True,
            )
        ],
    )
    result = evaluate_paper_distribution(request, taxonomy=TaxonomyRegistry())
    assert PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION in result.issue_codes
    assert result.verdict != PaperDistributionVerdict.PASS


def test_distinct_fingerprints_for_different_targets() -> None:
    base = build_demo_ten_question_paper()
    other = base.model_copy(
        update={
            "cognitive_targets": [
                DistributionTarget(dimension="cognitive", key="remember", exact_percent=30.0),
            ]
        }
    )
    first = evaluate_paper_distribution(
        base, taxonomy=TaxonomyRegistry(), day6_trust=_HARNESS, execution_mode=_SYNTHETIC
    )
    second = evaluate_paper_distribution(
        other, taxonomy=TaxonomyRegistry(), day6_trust=_HARNESS, execution_mode=_SYNTHETIC
    )
    assert first.result_fingerprint != second.result_fingerprint


def test_fractional_exact_count_uses_float_shares() -> None:
    request = build_demo_ten_question_paper()
    item = request.items[0].model_copy(
        update={"competency_codes": ["knowledge", "application"], "primary_competency_code": None}
    )
    updated = request.model_copy(
        update={
            "items": [item],
            "multi_label_policy": MultiLabelPolicy.FRACTIONAL_SPLIT,
            "cognitive_targets": [],
            "competency_targets": [
                DistributionTarget(dimension="competency", key="knowledge", exact_count=0),
            ],
        }
    )
    result = evaluate_paper_distribution(
        updated, taxonomy=TaxonomyRegistry(), day6_trust=_HARNESS,
        execution_mode=_SYNTHETIC,
    )
    assert result.verdict == PaperDistributionVerdict.FAIL
    assert PaperDistributionIssueCode.TARGET_MISMATCH in result.issue_codes


def test_primary_only_orphan_primary_fails() -> None:
    request = PaperDistributionRequest(
        paper_id="orphan-primary",
        items=[
            PaperItemInput(
                item_id="q1",
                cognitive_level="remember",
                competency_codes=[],
                primary_competency_code="knowledge",
                day6_validated=True,
            )
        ],
    )
    result = evaluate_paper_distribution(
        request, taxonomy=TaxonomyRegistry(), day6_trust=_HARNESS,
        execution_mode=_SYNTHETIC,
    )
    assert PaperDistributionIssueCode.MISSING_COMPETENCY in result.issue_codes
    assert result.verdict != PaperDistributionVerdict.PASS


def test_requested_count_mismatch_fails() -> None:
    request = build_demo_ten_question_paper().model_copy(update={"requested_count": 9})
    result = evaluate_paper_distribution(
        request, taxonomy=TaxonomyRegistry(), day6_trust=_HARNESS,
        execution_mode=_SYNTHETIC,
    )
    assert PaperDistributionIssueCode.REQUESTED_COUNT_MISMATCH in result.issue_codes
    assert result.verdict == PaperDistributionVerdict.FAIL


def test_session_audit_persisted_idempotent(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'paper-audit.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)
    request = build_demo_ten_question_paper()
    first = evaluate_paper_distribution_with_session(
        session, request, day6_trust=_HARNESS,
        execution_mode=_SYNTHETIC,
    )
    second = evaluate_paper_distribution_with_session(
        session, request, day6_trust=_HARNESS,
        execution_mode=_SYNTHETIC,
    )
    assert first.audit_ref is not None
    assert first.audit_ref == second.audit_ref
    record = session.get(ValidationAuditRun, first.audit_ref)
    assert record is not None
    assert record.metadata_json.get("kind") == "paper_distribution"
    session.commit()
    session.close()


def test_fake_validation_run_id_not_pass() -> None:
    request = build_demo_ten_question_paper()
    trust = PaperDay6TrustContext.from_validation_run("not-a-real-run")
    result = evaluate_paper_distribution(
        request,
        taxonomy=TaxonomyRegistry(),
        day6_trust=trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
    )
    assert PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION in result.issue_codes


def test_paper_audit_isolated_by_institution(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'paper-tenant.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)
    base = build_demo_ten_question_paper()
    inst_a = base.model_copy(
        update={"paper_id": "inst-a", "metadata_json": {"institution_id": "inst-a"}}
    )
    inst_b = base.model_copy(
        update={"paper_id": "inst-b", "metadata_json": {"institution_id": "inst-b"}}
    )
    ref_a = evaluate_paper_distribution_with_session(
        session, inst_a, day6_trust=_HARNESS, execution_mode=_SYNTHETIC
    ).audit_ref
    ref_b = evaluate_paper_distribution_with_session(
        session, inst_b, day6_trust=_HARNESS, execution_mode=_SYNTHETIC
    ).audit_ref
    session.commit()
    assert ref_a is not None and ref_b is not None
    assert ref_a != ref_b
    session.close()


def test_impossible_min_max_target_infeasible() -> None:
    request = build_demo_ten_question_paper().model_copy(
        update={
            "cognitive_targets": [
                DistributionTarget(
                    dimension="cognitive",
                    key="remember",
                    min_percent=80.0,
                    max_percent=10.0,
                ),
            ],
            "competency_targets": [],
        }
    )
    result = evaluate_paper_distribution(
        request, taxonomy=TaxonomyRegistry(), day6_trust=_HARNESS,
        execution_mode=_SYNTHETIC,
    )
    assert PaperDistributionIssueCode.TARGET_INFEASIBLE in result.issue_codes
