"""Issue #50 independent solver, author binding, and replay integrity."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import create_database_engine
from app.jee_advanced.author_draft_binding import solver_payload_has_answer_leak
from app.jee_advanced.core_test_fixtures import (
    seed_persisted_arithmetic_mcq_pair,
)
from app.jee_advanced.enums import AdvancedProfileKind
from app.jee_advanced.exam_profile import ensure_exam_version, ensure_jee_advanced_exam_pack
from app.jee_advanced.orchestration_chain import run_injected_author_solver_review_chain
from app.jee_advanced.paper_pair_persistence import PaperPairOutcome
from app.jee_advanced.production_orchestration import run_labeled_synthetic_pair_integration
from app.models import Question, TestDefinition
from app.orchestration.enums import GenerationNodeRole
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.types import GenerationRequest

POSITIVE_SCENARIO = "bound_synthetic_control"


def _session(tmp_path: Path) -> Session:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'f50.sqlite'}")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_arithmetic(tmp_path: Path) -> tuple[Session, str, str, tuple[str, str]]:
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
        organization_id="org-f50",
        institution_id="inst-f50",
        exam_version_id=vid,
    )
    session.commit()
    return session, vid, "org-f50", qids


def _kw(vid: str, org: str, qids: tuple[str, str], key: str) -> dict:
    return dict(
        organization_id=org,
        institution_id="inst-f50",
        exam_version_id=vid,
        question_ids=qids,
        idempotency_key=key,
        pair_correlation_id=f"pair-{key}",
    )


def test_f50_01_solver_request_has_no_answer_leak(tmp_path: Path) -> None:
    session, vid, org, qids = _seed_arithmetic(tmp_path)
    gateway = FakeGenerationGateway()
    run_injected_author_solver_review_chain(
        gateway,
        item_id=qids[0],
        run_id="leak-check",
        organization_id=org,
        scenario=POSITIVE_SCENARIO,
        author_user_extensions={
            "bound_display": {
                "stem_text": "What is 7 + 5?",
                "question_type": "single_choice",
                "options": [
                    {"option_key": "A", "text": "12", "sequence": 1},
                    {"option_key": "B", "text": "11", "sequence": 2},
                ],
            }
        },
    )
    assert len(gateway.call_history()) >= 2
    sample = {
        "item_id": qids[0],
        "run_id": "x",
        "display_candidate": {
            "stem_text": "What is 7 + 5?",
            "options": [{"option_key": "A", "text": "12"}, {"option_key": "B", "text": "11"}],
        },
    }
    assert not solver_payload_has_answer_leak(sample)
    leaky = {"display_candidate": {"options": [{"is_correct": True}]}}
    assert solver_payload_has_answer_leak(leaky)
    session.close()


def test_f50_01_echo_scenario_rejected(tmp_path: Path) -> None:
    session, vid, org, qids = _seed_arithmetic(tmp_path)
    gateway = FakeGenerationGateway()
    result = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        scenario="solver_match_persisted",
        **_kw(vid, org, qids, "f50-echo"),
    )
    assert result.persist.outcome == PaperPairOutcome.CONFLICT
    assert "echo_solver_scenario_rejected" in result.persist.issue_codes
    assert len(gateway.call_history()) == 0
    session.close()


def test_f50_01_clean_pass_solver_b_blocks_on_arithmetic(tmp_path: Path) -> None:
    session, vid, org, qids = _seed_arithmetic(tmp_path)
    gateway = FakeGenerationGateway()
    result = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        scenario="clean_pass",
        **_kw(vid, org, qids, "f50-neg"),
    )
    assert result.persist.outcome == PaperPairOutcome.CONFLICT
    conflict_codes = (
        "solver_answer_mismatch",
        "author_draft_content_mismatch",
        "generated_draft_not_bound",
    )
    assert any(code in result.persist.issue_codes for code in conflict_codes)
    assert session.scalar(select(func.count()).select_from(TestDefinition)) == 0
    session.close()


def test_f50_02_bound_control_issues_pair(tmp_path: Path) -> None:
    session, vid, org, qids = _seed_arithmetic(tmp_path)
    gateway = FakeGenerationGateway()
    first = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        scenario=POSITIVE_SCENARIO,
        **_kw(vid, org, qids, "f50-pos"),
    )
    session.commit()
    assert first.persist.outcome == PaperPairOutcome.CREATED
    assert first.gateway_calls >= 6
    meta = (session.get(TestDefinition, first.persist.test_definition_ids[0]).metadata_json or {})
    record = meta.get("issuance_record") or {}
    assert record.get("issuance_record_version") == "d12-f52-v1"
    session.close()


def test_f50_03_replay_after_day6_audit_drift(tmp_path: Path) -> None:
    session, vid, org, qids = _seed_arithmetic(tmp_path)
    gateway = FakeGenerationGateway()
    first = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        scenario=POSITIVE_SCENARIO,
        **_kw(vid, org, qids, "f50-audit"),
    )
    session.commit()
    assert first.persist.outcome == PaperPairOutcome.CREATED
    q = session.get(Question, qids[0])
    assert q is not None
    meta = dict(q.metadata_json or {})
    meta["day6_validation_audit_id"] = "audit-tampered"
    q.metadata_json = meta
    session.commit()
    replay = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        scenario=POSITIVE_SCENARIO,
        **_kw(vid, org, qids, "f50-audit"),
    )
    assert replay.persist.outcome == PaperPairOutcome.CONFLICT
    assert any("day6" in code for code in replay.persist.issue_codes)
    assert replay.gateway_calls == 0
    session.close()


def test_f50_author_mismatch_blocks_even_if_solver_matches(tmp_path: Path) -> None:
    session, vid, org, qids = _seed_arithmetic(tmp_path)
    gateway = FakeGenerationGateway()
    result = run_labeled_synthetic_pair_integration(
        session,
        gateway,
        scenario="clean_pass",
        **_kw(vid, org, qids, "f50-auth"),
    )
    assert result.persist.outcome == PaperPairOutcome.CONFLICT
    session.close()


def test_f50_paper2_mismatch_vetoes_pair(tmp_path: Path) -> None:
    session, vid, org, qids = _seed_arithmetic(tmp_path)

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
        scenario=POSITIVE_SCENARIO,
        **_kw(vid, org, qids, "f50-p2"),
    )
    assert result.persist.outcome == PaperPairOutcome.CONFLICT
    assert session.scalar(select(func.count()).select_from(TestDefinition)) == 0
    session.close()


def test_f50_integrated_cross_process_replay(tmp_path: Path) -> None:
    db_path = tmp_path / "f50-xp.db"
    engine = create_database_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    version_id = ""
    org = "org-f50"
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
        qids = seed_persisted_arithmetic_mcq_pair(
            session,
            organization_id=org,
            institution_id="inst-f50",
            exam_version_id=version_id,
        )
        gw = FakeGenerationGateway()
        first = run_labeled_synthetic_pair_integration(
            session,
            gw,
            organization_id=org,
            institution_id="inst-f50",
            exam_version_id=version_id,
            question_ids=qids,
            idempotency_key="f50-xp",
            pair_correlation_id="pair-f50-xp",
            scenario=POSITIVE_SCENARIO,
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
        institution_id="inst-f50",
        exam_version_id="{version_id}",
        question_ids=("{qids[0]}", "{qids[1]}"),
        idempotency_key="f50-xp",
        pair_correlation_id="pair-f50-xp",
        scenario="{POSITIVE_SCENARIO}",
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