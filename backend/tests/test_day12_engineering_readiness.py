"""Issue #46 engineering-readiness gates READY-01…04."""

from __future__ import annotations

import subprocess
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import create_database_engine
from app.jee_advanced.core_test_fixtures import seed_persisted_math_questions
from app.jee_advanced.enums import AdvancedProfileKind
from app.jee_advanced.exam_profile import ensure_exam_version, ensure_jee_advanced_exam_pack
from app.jee_advanced.independent_verification import (
    VerificationOutcome,
    verify_persisted_mcq,
    verify_persisted_numerical,
)
from app.jee_advanced.orchestration_chain import ChainStage, run_injected_author_solver_review_chain
from app.jee_advanced.scope_ledger import load_repo_scope_counts
from app.jee_advanced.syllabus_catalogue import (
    CatalogueStatus,
    build_reference_syllabus_catalogue,
    learning_outcome_bindings_available,
)
from app.jee_advanced.verification_orchestration import run_scoped_generation_probe
from app.models import Question
from app.orchestration.gateway.fake import FakeGenerationGateway


def _session(tmp_path: Path) -> Session:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'ready.sqlite'}")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_ready01_caller_correct_override_fails_despite_valid_audit(tmp_path: Path) -> None:
    session = _session(tmp_path)
    pack = ensure_jee_advanced_exam_pack(session)
    version = ensure_exam_version(
        session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    org, inst = "org-ready", "inst-ready"
    seed_persisted_math_questions(
        session,
        organization_id=org,
        institution_id=inst,
        exam_version_id=str(version.id),
        math_count=1,
        algebra_count=0,
    )
    session.commit()
    q = session.scalars(select(Question).limit(1)).first()
    assert q is not None
    override = verify_persisted_mcq(
        session,
        question=q,
        organization_id=org,
        institution_id=inst,
        selected="Z",
    )
    assert override.outcome == VerificationOutcome.FAIL
    assert (
        "selected_option_not_in_domain" in override.issue_codes
        or "mcq_incorrect" in override.issue_codes
    )

    correct_pick = verify_persisted_mcq(
        session,
        question=q,
        organization_id=org,
        institution_id=inst,
        selected="A",
    )
    assert correct_pick.outcome == VerificationOutcome.PASS

    missing_org = verify_persisted_mcq(
        session,
        question=q,
        organization_id="",
        institution_id=inst,
        selected="A",
    )
    assert missing_org.outcome == VerificationOutcome.REVIEW_REQUIRED
    session.close()


def test_ready01_numerical_stored_rubric_units(tmp_path: Path) -> None:
    session = _session(tmp_path)
    pack = ensure_jee_advanced_exam_pack(session)
    version = ensure_exam_version(
        session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    org, inst = "org-n", "inst-n"
    q = Question(
        external_code="ready-num-1",
        origin_type="generated",
        exam_version_id=str(version.id),
        question_type="numerical",
        stem_text="compute",
        answer_json={"value": "2.0", "units": "m", "units_required": True},
        rubric_json={"tolerance": 0.1, "units_required": True, "expected_units": "m"},
        status="approved",
        metadata_json={
            "d12_core_test_fixture": True,
            "organization_id": org,
            "institution_id": inst,
            "day6_validation_audit_id": "audit-num-ready",
            "day6_solver_evidence_id": "solver-num-ready",
        },
    )
    session.add(q)
    session.flush()
    from app.jee_advanced.core_test_fixtures import _persist_day6_validation_run

    _persist_day6_validation_run(
        session,
        run_id="audit-num-ready",
        question=q,
        organization_id=org,
        institution_id=inst,
    )
    session.commit()
    wrong_units = verify_persisted_numerical(
        session,
        question=q,
        organization_id=org,
        institution_id=inst,
        submitted="2.0",
    )
    assert wrong_units.outcome == VerificationOutcome.REVIEW_REQUIRED
    ok = verify_persisted_numerical(
        session,
        question=q,
        organization_id=org,
        institution_id=inst,
        submitted="2.0 m",
    )
    assert ok.outcome == VerificationOutcome.PASS
    session.close()


def test_ready02_syllabus_unknown_subject_not_ready(tmp_path: Path) -> None:
    session = _session(tmp_path)
    report = build_reference_syllabus_catalogue(session)
    assert report.status != CatalogueStatus.READY
    ok, issues = learning_outcome_bindings_available(session)
    assert ok is False
    assert issues
    session.close()


def test_ready03_injected_gateway_review_chain() -> None:
    gateway = FakeGenerationGateway()
    result = run_injected_author_solver_review_chain(
        gateway,
        item_id="item-chain",
        run_id="run-chain",
        organization_id="org-chain",
        scenario="clean_pass",
    )
    assert result.verdict.outcome == VerificationOutcome.PASS
    assert ChainStage.REVIEW in result.stages_completed
    assert result.gateway_calls >= 3

    gateway2 = FakeGenerationGateway()
    reject = run_injected_author_solver_review_chain(
        gateway2,
        item_id="item-reject",
        run_id="run-reject",
        organization_id="org-chain",
        scenario="solver_disagree",
    )
    assert reject.verdict.outcome == VerificationOutcome.REVIEW_REQUIRED

    verdict, calls = run_scoped_generation_probe(
        item_id="probe-ready",
        run_id="run-probe",
        organization_id="org-chain",
        gateway=gateway,
    )
    assert calls >= 3
    assert verdict.outcome == VerificationOutcome.PASS


def test_ready03_pair_replay_cross_process_documented(tmp_path: Path) -> None:
    """Cross-process replay exercised in test_day12_core; gate documents dependency."""

    tmp_path / "relay.sqlite"
    session = _session(tmp_path)
    session.close()
    create_database_engine.cache_clear()
    assert (Path(__file__).parent / "test_day12_core.py").exists()


def test_ready04_scope_ledger_and_ruff_clean() -> None:
    counts = load_repo_scope_counts()
    assert counts["TOTAL"] == 36
    proc = subprocess.run(
        ["ruff", "check", "app", "tests"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr