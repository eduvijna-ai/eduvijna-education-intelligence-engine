"""Issue #49 snapshot replay gate and solver/answer binding."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import create_database_engine
from app.jee_advanced.core_test_fixtures import (
    seed_persisted_arithmetic_mcq_pair,
)
from app.jee_advanced.enums import AdvancedProfileKind
from app.jee_advanced.exam_profile import ensure_exam_version, ensure_jee_advanced_exam_pack
from app.jee_advanced.paper_pair_persistence import PaperPairOutcome
from app.jee_advanced.production_orchestration import run_labeled_synthetic_pair_integration
from app.models import Question, TestDefinition
from app.models.enums import QuestionStatus
from app.orchestration.enums import GenerationNodeRole
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.types import GenerationRequest

MATCH_SCENARIO = "bound_synthetic_control"


def _session(tmp_path: Path) -> Session:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'f49.sqlite'}")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed(tmp_path: Path) -> tuple[Session, str, str, tuple[str, str]]:
    session = _session(tmp_path)
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
        organization_id="org-f49",
        institution_id="inst-f49",
        exam_version_id=vid,
    )
    session.commit()
    return session, vid, "org-f49", (qids[0], qids[1])


def _kw(vid: str, org: str, qids: tuple[str, str], key: str) -> dict:
    return dict(
        organization_id=org,
        institution_id="inst-f49",
        exam_version_id=vid,
        question_ids=qids,
        idempotency_key=key,
        pair_correlation_id=f"pair-{key}",
    )


def test_f49_02_echo_scenario_rejected_at_integration(tmp_path: Path) -> None:
    session, vid, org, qids = _seed(tmp_path)
    gateway = FakeGenerationGateway()
    result = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        scenario="solver_match_persisted",
        **_kw(vid, org, qids, "f49-echo"),
    )
    assert result.persist.outcome == PaperPairOutcome.CONFLICT
    assert "echo_solver_scenario_rejected" in result.persist.issue_codes
    session.close()


def test_f49_02_clean_pass_solver_b_blocks_issuance(tmp_path: Path) -> None:
    session, vid, org, qids = _seed(tmp_path)
    gateway = FakeGenerationGateway()
    calls0 = len(gateway.call_history())
    result = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        scenario="clean_pass",
        **_kw(vid, org, qids, "f49-neg"),
    )
    assert result.persist.outcome == PaperPairOutcome.CONFLICT
    assert "solver_answer_mismatch" in result.persist.issue_codes
    assert session.scalar(select(func.count()).select_from(TestDefinition)) == 0
    assert len(gateway.call_history()) > calls0
    session.close()


def test_f49_02_paper2_mismatch_vetoes_pair(tmp_path: Path) -> None:
    session, vid, org, qids = _seed(tmp_path)

    class Paper2MismatchGateway(FakeGenerationGateway):
        def __init__(self) -> None:
            super().__init__()
            self._solver_calls = 0

        def generate(self, request: GenerationRequest):
            if request.role == GenerationNodeRole.SOLVER:
                self._solver_calls += 1
                if self._solver_calls == 2:
                    request = replace(request, scenario="clean_pass")
            return super().generate(request)

    gateway = Paper2MismatchGateway()
    result = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        scenario=MATCH_SCENARIO,
        **_kw(vid, org, qids, "f49-p2"),
    )
    assert result.persist.outcome == PaperPairOutcome.CONFLICT
    assert any(
        c in result.persist.issue_codes
        for c in ("solver_answer_mismatch", "author_solver_disagreement")
    )
    assert session.scalar(select(func.count()).select_from(TestDefinition)) == 0
    session.close()


def test_f49_01_replay_after_question_rejected(tmp_path: Path) -> None:
    session, vid, org, qids = _seed(tmp_path)
    gateway = FakeGenerationGateway()
    first = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        scenario=MATCH_SCENARIO,
        **_kw(vid, org, qids, "f49-rej"),
    )
    session.commit()
    assert first.persist.outcome == PaperPairOutcome.CREATED

    q = session.get(Question, qids[0])
    assert q is not None
    q.status = QuestionStatus.REJECTED.value
    session.commit()

    calls_before = len(gateway.call_history())
    replay = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        scenario=MATCH_SCENARIO,
        **_kw(vid, org, qids, "f49-rej"),
    )
    assert replay.persist.outcome == PaperPairOutcome.CONFLICT
    assert any("not_approved" in code for code in replay.persist.issue_codes)
    assert replay.gateway_calls == 0
    assert len(gateway.call_history()) == calls_before
    session.close()


def test_f49_01_replay_after_stem_drift(tmp_path: Path) -> None:
    session, vid, org, qids = _seed(tmp_path)
    gateway = FakeGenerationGateway()
    first = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        scenario=MATCH_SCENARIO,
        **_kw(vid, org, qids, "f49-stem"),
    )
    session.commit()
    assert first.persist.outcome == PaperPairOutcome.CREATED

    q = session.get(Question, qids[1])
    assert q is not None
    q.stem_text = f"{q.stem_text} mutated"
    session.commit()

    replay = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        scenario=MATCH_SCENARIO,
        **_kw(vid, org, qids, "f49-stem"),
    )
    assert replay.persist.outcome == PaperPairOutcome.CONFLICT
    assert any("content_drift" in code for code in replay.persist.issue_codes)
    assert replay.gateway_calls == 0
    session.close()


def test_f49_01_integrated_replay_cross_process(tmp_path: Path) -> None:
    db_path = tmp_path / "f49-xproc.db"
    engine = create_database_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    version_id = ""
    org = "org-f49"
    qids: tuple[str, str] = ("", "")
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
            institution_id="inst-f49",
            exam_version_id=version_id,
        )
        qids = (seeded[0], seeded[1])
        gw = FakeGenerationGateway()
        first = run_labeled_synthetic_pair_integration(
            session,
            gw,
            organization_id=org,
            institution_id="inst-f49",
            exam_version_id=version_id,
            question_ids=qids,
            idempotency_key="f49-xp",
            pair_correlation_id="pair-f49-xp",
            scenario=MATCH_SCENARIO,
        )
        session.commit()
        assert first.persist.outcome == PaperPairOutcome.CREATED

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
        institution_id="inst-f49",
        exam_version_id="{version_id}",
        question_ids=("{qids[0]}", "{qids[1]}"),
        idempotency_key="f49-xp",
        pair_correlation_id="pair-f49-xp",
        scenario="{MATCH_SCENARIO}",
    )
    session.commit()
    print(result.persist.outcome)
    print(result.gateway_calls)
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
    create_database_engine.cache_clear()