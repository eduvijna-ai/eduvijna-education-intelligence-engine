from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION, DiagnosticValidationStatus
from app.prerequisite_intelligence.fixtures import (
    load_day10_fixture_snapshot,
    seed_day10_prerequisite_fixture,
)
from app.root_cause_intelligence.contracts import RootCauseDiagnosticRequest
from app.root_cause_intelligence.enums import RootCauseIssueCode, RootCauseVerdictStatus
from app.root_cause_intelligence.service import RootCauseIntelligenceService
from app.root_cause_intelligence.trusted_validation import RootCauseTrustedValidationContext


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'd10-rc.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _trusted(**kwargs) -> RootCauseTrustedValidationContext:
    payload = {
        "item_id": "item-1",
        "option_key": "A",
        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        "taxonomy_version": DEFAULT_TAXONOMY_VERSION,
    }
    payload.update(kwargs)
    return RootCauseTrustedValidationContext.synthetic_fixture_harness(**payload)


def _tag(**kwargs) -> OptionDiagnosticTag:
    payload = {
        "item_id": "item-1",
        "option_key": "A",
        "is_correct": False,
        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        "validation_status": DiagnosticValidationStatus.PASS,
        "taxonomy_version": DEFAULT_TAXONOMY_VERSION,
    }
    payload.update(kwargs)
    return OptionDiagnosticTag(**payload)


def test_root_cause_returns_multiple_ranked_hypotheses(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    service = RootCauseIntelligenceService()
    result = service.analyze(
        RootCauseDiagnosticRequest(
            item_id="item-1",
            option_key="A",
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            tag=_tag(),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=snapshot,
            target_concept_code="multi-step-addition",
            allowed_source_revision_ids=[],
        ),
        trusted=_trusted(),
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
    )
    assert result.verdict_status in {
        RootCauseVerdictStatus.PASS,
        RootCauseVerdictStatus.REVIEW_REQUIRED,
    }
    assert len(result.hypotheses) >= 2
    assert all(hypothesis.paths for hypothesis in result.hypotheses)
    assert result.hypotheses[0].rank == 1


def test_correct_option_tag_is_blocked(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    service = RootCauseIntelligenceService()
    result = service.analyze(
        RootCauseDiagnosticRequest(
            item_id="item-1",
            option_key="B",
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            tag=_tag(is_correct=True, option_key="B"),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=snapshot,
            target_concept_code="multi-step-addition",
        ),
        trusted=_trusted(option_key="B"),
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
    )
    assert RootCauseIssueCode.CORRECT_OPTION_TAGGED in result.issue_codes


def test_zero_edge_graph_cannot_pass(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    empty = snapshot.model_copy(update={"edges": []})
    service = RootCauseIntelligenceService()
    result = service.analyze(
        RootCauseDiagnosticRequest(
            item_id="item-1",
            option_key="A",
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            tag=_tag(),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=empty,
            target_concept_code="multi-step-addition",
        ),
        trusted=_trusted(),
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
    )
    assert result.verdict_status != RootCauseVerdictStatus.PASS
    assert RootCauseIssueCode.NO_PREREQUISITE_PATH in result.issue_codes


def test_untrusted_tag_requires_review(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    service = RootCauseIntelligenceService()
    result = service.analyze(
        RootCauseDiagnosticRequest(
            item_id="item-1",
            option_key="A",
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            tag=_tag(),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=snapshot,
            target_concept_code="multi-step-addition",
        ),
    )
    assert RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION in result.issue_codes
    assert result.verdict_status == RootCauseVerdictStatus.REVIEW_REQUIRED


def test_snapshot_allowlist_spoof_blocked(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    spoofed = snapshot.model_copy(
        update={
            "metadata_json": {
                **snapshot.metadata_json,
                "authorized_revision_ids": ["forged-revision"],
            }
        }
    )
    service = RootCauseIntelligenceService()
    result = service.analyze(
        RootCauseDiagnosticRequest(
            item_id="item-1",
            option_key="A",
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            tag=_tag(),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=spoofed,
            target_concept_code="multi-step-addition",
            allowed_source_revision_ids=[],
        ),
        trusted=_trusted(),
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
    )
    assert RootCauseIssueCode.SNAPSHOT_ALLOWLIST_SPOOF in result.issue_codes
    assert result.verdict_status != RootCauseVerdictStatus.PASS


def test_forged_taxonomy_blocked_even_when_trusted(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    service = RootCauseIntelligenceService()
    forged_version = "forged-taxonomy"
    result = service.analyze(
        RootCauseDiagnosticRequest(
            item_id="item-1",
            option_key="A",
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version=forged_version,
            tag=_tag(taxonomy_version=forged_version),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=snapshot,
            target_concept_code="multi-step-addition",
        ),
        trusted=_trusted(taxonomy_version=forged_version),
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
    )
    assert RootCauseIssueCode.INACTIVE_TAXONOMY in result.issue_codes
    assert result.verdict_status != RootCauseVerdictStatus.PASS


def test_graph_audit_fail_returns_no_hypothesis_paths(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    spoofed = snapshot.model_copy(
        update={
            "metadata_json": {
                **snapshot.metadata_json,
                "authorized_revision_ids": ["forged-revision"],
            }
        }
    )
    service = RootCauseIntelligenceService()
    result = service.analyze(
        RootCauseDiagnosticRequest(
            item_id="item-1",
            option_key="A",
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            tag=_tag(),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=spoofed,
            target_concept_code="multi-step-addition",
            allowed_source_revision_ids=[],
        ),
        trusted=_trusted(),
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
    )
    assert result.hypotheses == []


def test_spoofed_pass_without_trusted_context_blocked(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    service = RootCauseIntelligenceService()
    result = service.analyze(
        RootCauseDiagnosticRequest(
            item_id="item-1",
            option_key="A",
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            tag=_tag(),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=snapshot,
            target_concept_code="multi-step-addition",
        ),
    )
    assert RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION in result.issue_codes
    assert result.verdict_status == RootCauseVerdictStatus.REVIEW_REQUIRED
