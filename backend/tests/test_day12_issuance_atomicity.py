"""Issue #48 issuance atomicity: preflight-before-gateway and dual validation."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import create_database_engine
from app.jee_advanced.core_test_fixtures import (
    seed_persisted_arithmetic_mcq_pair,
)
from app.jee_advanced.enums import AdvancedProfileKind
from app.jee_advanced.exam_profile import ensure_exam_version, ensure_jee_advanced_exam_pack
from app.jee_advanced.paper_pair_persistence import PaperPairOutcome
from app.jee_advanced.production_orchestration import (
    build_labeled_synthetic_pair_request,
    run_labeled_synthetic_pair_integration,
)
from app.models import Question
from app.models import TestDefinition as TestDefinitionRow
from app.models.enums import QuestionStatus
from app.orchestration.gateway.fake import FakeGenerationGateway

_MATCH_SCENARIO = "bound_synthetic_control"


def _session(tmp_path: Path) -> Session:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'p48.sqlite'}")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_pair_context(session: Session) -> tuple[str, str, tuple[str, str]]:
    pack = ensure_jee_advanced_exam_pack(session)
    version = ensure_exam_version(
        session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    vid = str(version.id)
    qids = seed_persisted_arithmetic_mcq_pair(
        session,
        organization_id="org-p48",
        institution_id="inst-p48",
        exam_version_id=vid,
    )
    session.commit()
    return vid, "org-p48", (qids[0], qids[1])


def test_p48_01_replay_same_process_zero_gateway(tmp_path: Path) -> None:
    session = _session(tmp_path)
    vid, org, qids = _seed_pair_context(session)
    gateway = FakeGenerationGateway()
    kw = dict(
        organization_id=org,
        institution_id="inst-p48",
        exam_version_id=vid,
        question_ids=qids,
        idempotency_key="idem-p48",
        pair_correlation_id="pair-p48",
    )
    first = run_labeled_synthetic_pair_integration(
        session, gateway, scenario=_MATCH_SCENARIO, **kw
    )
    session.commit()
    assert first.persist.outcome == PaperPairOutcome.CREATED
    assert first.gateway_calls >= 6

    calls_before = len(gateway.call_history())
    second = run_labeled_synthetic_pair_integration(
        session, gateway, scenario=_MATCH_SCENARIO, **kw
    )
    assert second.replayed is True
    assert second.persist.outcome == PaperPairOutcome.REPLAYED
    assert second.gateway_calls == 0
    assert len(gateway.call_history()) == calls_before
    assert first.persist.test_definition_ids == second.persist.test_definition_ids
    session.close()


def test_p48_01_conflict_before_gateway_changed_marks(tmp_path: Path) -> None:
    session = _session(tmp_path)
    vid, org, qids = _seed_pair_context(session)
    gateway = FakeGenerationGateway()
    first = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        organization_id=org,
        institution_id="inst-p48",
        exam_version_id=vid,
        question_ids=qids,
        idempotency_key="idem-p48c",
        pair_correlation_id="pair-p48c",
        scenario=_MATCH_SCENARIO,
    )
    session.commit()
    assert first.persist.outcome == PaperPairOutcome.CREATED

    bad_req = build_labeled_synthetic_pair_request(
        organization_id=org,
        institution_id="inst-p48",
        exam_version_id=vid,
        question_ids=qids,
        idempotency_key="idem-p48c",
        pair_correlation_id="pair-p48c",
    )
    papers = list(bad_req.paper_definitions)
    items = list(papers[0]["question_items"])
    items[0] = {**items[0], "marks": 99}
    papers[0] = {**papers[0], "question_items": items}
    gateway2 = FakeGenerationGateway()
    calls0 = len(gateway2.call_history())
    from app.jee_advanced.paper_pair_persistence import preflight_two_paper_pair

    conflict = preflight_two_paper_pair(
        session,
        replace(bad_req, paper_definitions=(papers[0], papers[1])),
    )
    assert conflict is not None
    assert conflict.outcome == PaperPairOutcome.CONFLICT
    assert len(gateway2.call_history()) == calls0
    session.close()


def test_p48_02_one_invalid_question_blocks_before_gateway(tmp_path: Path) -> None:
    session = _session(tmp_path)
    vid, org, qids = _seed_pair_context(session)
    q = session.get(Question, qids[1])
    assert q is not None
    q.status = QuestionStatus.REJECTED.value
    session.commit()
    gateway = FakeGenerationGateway()
    calls0 = len(gateway.call_history())
    result = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        organization_id=org,
        institution_id="inst-p48",
        exam_version_id=vid,
        question_ids=qids,
        idempotency_key="idem-inv",
        pair_correlation_id="pair-inv",
        scenario=_MATCH_SCENARIO,
    )
    assert result.persist.outcome == PaperPairOutcome.CONFLICT
    assert "question_not_approved" in result.persist.issue_codes
    assert result.gateway_calls == 0
    assert len(gateway.call_history()) == calls0
    session.close()


def test_p48_03_integrated_cross_process_zero_gateway(tmp_path: Path) -> None:
    db_path = tmp_path / "p48-int.db"
    engine = create_database_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    version_id = ""
    org = "org-p48"
    qids: tuple[str, str] = ("", "")
    first_def_ids: tuple[str, ...] = ()
    with Session(engine) as session:
        pack = ensure_jee_advanced_exam_pack(session)
        version = ensure_exam_version(
            session,
            pack=pack,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            academic_year="2026",
        )
        version_id = str(version.id)
        seeded = seed_persisted_arithmetic_mcq_pair(
            session,
            organization_id=org,
            institution_id="inst-p48",
            exam_version_id=version_id,
        )
        qids = (seeded[0], seeded[1])
        gw = FakeGenerationGateway()
        first = run_labeled_synthetic_pair_integration(
            session,
            gw,
            organization_id=org,
            institution_id="inst-p48",
            exam_version_id=version_id,
            question_ids=qids,
            idempotency_key="idem-p48x",
            pair_correlation_id="pair-p48x",
            scenario=_MATCH_SCENARIO,
        )
        session.commit()
        assert first.persist.outcome == PaperPairOutcome.CREATED
        first_def_ids = first.persist.test_definition_ids

    script = f'''
from sqlalchemy.orm import Session
import app.models  # noqa: F401
from app.db.session import create_database_engine
from app.jee_advanced.production_orchestration import run_labeled_synthetic_pair_integration
from app.orchestration.gateway.fake import FakeGenerationGateway

engine = create_database_engine("sqlite:///{db_path}")
with Session(engine) as session:
    gw = FakeGenerationGateway()
    result = run_labeled_synthetic_pair_integration(
        session,
        gw,
        organization_id="{org}",
        institution_id="inst-p48",
        exam_version_id="{version_id}",
        question_ids=("{qids[0]}", "{qids[1]}"),
        idempotency_key="idem-p48x",
        pair_correlation_id="pair-p48x",
        scenario="{_MATCH_SCENARIO}",
    )
    session.commit()
    print(result.persist.outcome)
    print(result.gateway_calls)
    print(",".join(result.persist.test_definition_ids))
'''
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert lines[0] == "replayed"
    assert lines[1] == "0"
    assert lines[2] == ",".join(first_def_ids)
    create_database_engine.cache_clear()

    with Session(engine) as session:
        count = len(session.scalars(select(TestDefinitionRow)).all())
        assert count == 2