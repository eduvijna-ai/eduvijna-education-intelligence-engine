from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
from app.prerequisite_intelligence.fixtures import load_day10_fixture_snapshot, seed_day10_prerequisite_fixture
from app.root_cause_intelligence.contracts import RootCauseDiagnosticRequest
from app.root_cause_intelligence.enums import RootCauseIssueCode, RootCauseVerdictStatus
from app.root_cause_intelligence.service import RootCauseIntelligenceService


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'd10-rc.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _tag(**kwargs) -> OptionDiagnosticTag:
    payload = {
        "item_id": "item-1",
        "option_key": "A",
        "is_correct": False,
        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        "validation_status": DiagnosticValidationStatus.PASS,
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
            taxonomy_version="misconception-taxonomy@v1",
            tag=_tag(),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=snapshot,
            target_concept_code="multi-step-addition",
            allowed_source_revision_ids=[ctx["source_revision_id"]],
        )
    )
    assert result.verdict_status in {
        RootCauseVerdictStatus.PASS,
        RootCauseVerdictStatus.REVIEW_REQUIRED,
    }
    assert len(result.hypotheses) >= 2
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
            taxonomy_version="misconception-taxonomy@v1",
            tag=_tag(is_correct=True, option_key="B"),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=snapshot,
            target_concept_code="multi-step-addition",
        )
    )
    assert RootCauseIssueCode.CORRECT_OPTION_TAGGED in result.issue_codes
