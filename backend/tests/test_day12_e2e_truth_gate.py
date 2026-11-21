"""Issue #51 final E2E truth gate: three-party answers and replay evidence."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import create_database_engine
from app.jee_advanced.author_draft_binding import (
    author_claimed_answer_key,
    author_payload_has_answer_leak,
    display_candidate_from_question,
    solver_payload_has_answer_leak,
)
from app.jee_advanced.core_test_fixtures import seed_persisted_arithmetic_mcq_pair
from app.jee_advanced.enums import AdvancedProfileKind
from app.jee_advanced.exam_profile import ensure_exam_version, ensure_jee_advanced_exam_pack
from app.jee_advanced.orchestration_chain import run_injected_author_solver_review_chain
from app.jee_advanced.paper_pair_persistence import PaperPairOutcome
from app.jee_advanced.production_orchestration import run_labeled_synthetic_pair_integration
from app.models import Question, TestDefinition
from app.models.enums import QuestionStatus
from app.orchestration.enums import GenerationNodeRole
from app.orchestration.gateway.fake import FakeGenerationGateway

POSITIVE = "bound_synthetic_control"


def _session(tmp_path: Path) -> Session:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'f51.sqlite'}")
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
        organization_id="org-f51",
        institution_id="inst-f51",
        exam_version_id=vid,
    )
    session.commit()
    return session, vid, "org-f51", qids


def _kw(vid: str, org: str, qids: tuple[str, str], key: str) -> dict:
    return dict(
        organization_id=org,
        institution_id="inst-f51",
        exam_version_id=vid,
        question_ids=qids,
        idempotency_key=key,
        pair_correlation_id=f"pair-{key}",
    )


def test_author_claim_extractor_rejects_double_true_with_explicit() -> None:
    key, issues = author_claimed_answer_key(
        {
            "options": [
                {"option_key": "A", "is_correct": True},
                {"option_key": "B", "is_correct": True},
            ],
            "answer_json": {"option_key": "A"},
        }
    )
    assert key is None
    assert "author_answer_ambiguous" in issues


def test_author_claim_all_false_flags_with_explicit_key() -> None:
    key, issues = author_claimed_answer_key(
        {
            "options": [
                {"option_key": "A", "is_correct": False},
                {"option_key": "B", "is_correct": False},
            ],
            "answer_json": {"option_key": "A"},
        }
    )
    assert key is None
    assert "author_answer_mismatch" in issues


class _RecordingAuthorGateway(FakeGenerationGateway):
    def __init__(self) -> None:
        super().__init__()
        self.author_payloads: list[dict[str, object]] = []

    def generate(self, request):
        if request.role == GenerationNodeRole.AUTHOR:
            self.author_payloads.append(dict(request.user_payload))
        return super().generate(request)


def test_f51_01_triple_agreement_created(tmp_path: Path) -> None:
    session, vid, org, qids = _seed(tmp_path)
    gateway = _RecordingAuthorGateway()
    first = run_labeled_synthetic_pair_integration(
        session, gateway, scenario=POSITIVE, **_kw(vid, org, qids, "f51-aaa")
    )
    session.commit()
    assert first.persist.outcome == PaperPairOutcome.CREATED
    test_row = session.get(TestDefinition, first.persist.test_definition_ids[0])
    assert test_row is not None
    record = (test_row.metadata_json or {}).get("issuance_record")
    assert record and record.get("issuance_record_version") == "d12-f52-v1"
    for qid in qids:
        ev = record["chain_evidence"][qid]
        assert ev["author_claimed_answer_key"] == "A"
        assert ev["proposed_answer_key"] == "A"
        assert ev["stored_answer_key"] == "A"
        assert ev.get("reviewer_verdict")
    assert gateway.author_payloads
    assert all("bound_correct_key" not in p for p in gateway.author_payloads)
    assert all(not author_payload_has_answer_leak(p) for p in gateway.author_payloads)
    session.close()


def test_f51_01_author_all_false_blocks(tmp_path: Path) -> None:
    session, vid, org, qids = _seed(tmp_path)
    class AllFalseAuthorGateway(FakeGenerationGateway):
        def generate(self, request):
            if request.role == GenerationNodeRole.AUTHOR:
                payload = dict(request.user_payload)
                payload["bound_author_all_false"] = True
                request = replace(request, user_payload=payload)
            return super().generate(request)

    gateway = AllFalseAuthorGateway()
    result = run_labeled_synthetic_pair_integration(
        session, gateway, scenario=POSITIVE, **_kw(vid, org, qids, "f51-nof")
    )
    assert result.persist.outcome == PaperPairOutcome.CONFLICT
    assert any(
        c in result.persist.issue_codes
        for c in ("author_answer_missing", "author_answer_mismatch")
    )
    assert session.scalar(select(func.count()).select_from(TestDefinition)) == 0
    session.close()


def test_f51_01_author_wrong_claim_blocks(tmp_path: Path) -> None:
    session, vid, org, qids = _seed(tmp_path)

    class WrongAuthorGateway(FakeGenerationGateway):
        def generate(self, request):
            if request.role == GenerationNodeRole.AUTHOR:
                payload = dict(request.user_payload)
                payload["bound_author_wrong_key"] = "B"
                request = replace(request, user_payload=payload)
            return super().generate(request)

    gateway = WrongAuthorGateway()
    result = run_labeled_synthetic_pair_integration(
        session, gateway, scenario=POSITIVE, **_kw(vid, org, qids, "f51-wrong")
    )
    assert result.persist.outcome == PaperPairOutcome.CONFLICT
    assert any(
        c in result.persist.issue_codes
        for c in ("author_answer_mismatch", "author_solver_disagreement")
    )
    session.close()


def test_f51_01_default_clean_pass_blocks(tmp_path: Path) -> None:
    session, vid, org, qids = _seed(tmp_path)
    result = run_labeled_synthetic_pair_integration(
        session,
        FakeGenerationGateway(),
        scenario="clean_pass",
        **_kw(vid, org, qids, "f51-clean"),
    )
    assert result.persist.outcome == PaperPairOutcome.CONFLICT
    session.close()


def test_f51_01_solver_payload_no_leak(tmp_path: Path) -> None:
    session, vid, org, qids = _seed(tmp_path)
    q = session.get(Question, qids[0])
    assert q is not None
    visible = display_candidate_from_question(q)
    gateway = FakeGenerationGateway()
    run_injected_author_solver_review_chain(
        gateway,
        item_id=qids[0],
        run_id="leak",
        organization_id=org,
        scenario=POSITIVE,
        author_user_extensions={"bound_display": visible},
        persisted_visible_fingerprint="x",
    )
    assert len(gateway.call_history()) >= 2
    assert not solver_payload_has_answer_leak(
        {"display_candidate": visible, "item_id": qids[0], "run_id": "leak"}
    )
    session.close()


def test_f51_02_replay_rejects_legacy_f51_record_version(tmp_path: Path) -> None:
    session, vid, org, qids = _seed(tmp_path)
    gateway = FakeGenerationGateway()
    first = run_labeled_synthetic_pair_integration(
        session, gateway, scenario=POSITIVE, **_kw(vid, org, qids, "f51-legacy")
    )
    session.commit()
    assert first.persist.outcome == PaperPairOutcome.CREATED
    for tid in first.persist.test_definition_ids:
        t = session.get(TestDefinition, tid)
        assert t is not None
        meta = dict(t.metadata_json or {})
        record = dict(meta.get("issuance_record") or {})
        record["issuance_record_version"] = "d12-f51-v1"
        meta["issuance_record"] = record
        t.metadata_json = meta
    session.commit()
    replay = run_labeled_synthetic_pair_integration(
        session, gateway, scenario=POSITIVE, **_kw(vid, org, qids, "f51-legacy")
    )
    assert replay.persist.outcome == PaperPairOutcome.CONFLICT
    assert "issuance_record_version_unsupported" in replay.persist.issue_codes
    assert replay.gateway_calls == 0
    session.close()


def test_f51_02_replay_missing_paper2_chain_evidence(tmp_path: Path) -> None:
    session, vid, org, qids = _seed(tmp_path)
    gateway = FakeGenerationGateway()
    first = run_labeled_synthetic_pair_integration(
        session, gateway, scenario=POSITIVE, **_kw(vid, org, qids, "f51-p2ev")
    )
    session.commit()
    assert first.persist.outcome == PaperPairOutcome.CREATED
    for tid in first.persist.test_definition_ids:
        t = session.get(TestDefinition, tid)
        assert t is not None
        meta = dict(t.metadata_json or {})
        record = dict(meta.get("issuance_record") or {})
        chain = dict(record.get("chain_evidence") or {})
        chain.pop(qids[1], None)
        record["chain_evidence"] = chain
        meta["issuance_record"] = record
        t.metadata_json = meta
    session.commit()
    replay = run_labeled_synthetic_pair_integration(
        session, gateway, scenario=POSITIVE, **_kw(vid, org, qids, "f51-p2ev")
    )
    assert replay.persist.outcome == PaperPairOutcome.CONFLICT
    assert any("chain" in c for c in replay.persist.issue_codes)
    assert replay.gateway_calls == 0
    session.close()


def test_f51_02_integrated_cross_process_replay(tmp_path: Path) -> None:
    db_path = tmp_path / "f51-xp.db"
    engine = create_database_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    org = "org-f51"
    version_id = ""
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
            institution_id="inst-f51",
            exam_version_id=version_id,
        )
        gw = FakeGenerationGateway()
        first = run_labeled_synthetic_pair_integration(
            session,
            gw,
            organization_id=org,
            institution_id="inst-f51",
            exam_version_id=version_id,
            question_ids=qids,
            idempotency_key="f51-xp",
            pair_correlation_id="pair-f51-xp",
            scenario=POSITIVE,
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
        institution_id="inst-f51",
        exam_version_id="{version_id}",
        question_ids=("{qids[0]}", "{qids[1]}"),
        idempotency_key="f51-xp",
        pair_correlation_id="pair-f51-xp",
        scenario="{POSITIVE}",
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


def test_f51_02_replay_after_question_status_revoked(tmp_path: Path) -> None:
    session, vid, org, qids = _seed(tmp_path)
    gateway = FakeGenerationGateway()
    created = run_labeled_synthetic_pair_integration(
        session, gateway, scenario=POSITIVE, **_kw(vid, org, qids, "f51-rev")
    )
    session.commit()
    assert created.persist.outcome == PaperPairOutcome.CREATED
    q = session.get(Question, qids[0])
    assert q is not None
    q.status = QuestionStatus.REJECTED.value
    session.commit()
    replay = run_labeled_synthetic_pair_integration(
        session, gateway, scenario=POSITIVE, **_kw(vid, org, qids, "f51-rev")
    )
    assert replay.persist.outcome == PaperPairOutcome.CONFLICT
    assert replay.gateway_calls == 0
    session.close()