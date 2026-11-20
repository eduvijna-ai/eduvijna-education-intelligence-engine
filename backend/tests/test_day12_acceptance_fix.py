"""Issue #45 AC-F01…F05 consolidated acceptance-fix adversarial matrix."""

from __future__ import annotations

import math
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import create_database_engine
from app.jee_advanced.constants import BROCHURE_DISCOVERY_URL_ALTERNATE
from app.jee_advanced.constraint_precedence import (
    ConstraintLayer,
    resolve_authoritative_constraint_layer,
    resolve_constraint_layer,
)
from app.jee_advanced.core_test_fixtures import seed_persisted_math_questions
from app.jee_advanced.enums import AdvancedProfileKind, JeeAdvancedSourceTrustMode
from app.jee_advanced.exam_profile import ensure_exam_version, ensure_jee_advanced_exam_pack
from app.jee_advanced.historical_inventory import build_historical_inventory
from app.jee_advanced.independent_verification import (
    VerificationOutcome,
    verify_persisted_mcq,
    verify_persisted_multiselect,
    verify_persisted_numerical,
)
from app.jee_advanced.scope_ledger import load_repo_scope_counts
from app.jee_advanced.source_ingest_staging import stage_official_slot
from app.jee_advanced.source_registry import JEE_ADVANCED_2026_SOURCE_SLOTS
from app.jee_advanced.syllabus_catalogue import CatalogueStatus, build_reference_syllabus_catalogue
from app.jee_advanced.verification_orchestration import (
    run_scoped_generation_probe,
    verify_mcq_answer,
    verify_numerical_answer,
)
from app.models import Question, SourceRevision
from app.source_intelligence.security import SourceUrlFetcher
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage

_PUBLIC_RESOLVER = lambda _h: ["93.184.216.34"]  # noqa: E731


def _session(tmp_path: Path) -> tuple[Session, SourceIntelligenceService]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'acfix.sqlite'}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    storage = LocalSourceStorage(tmp_path / "private")
    service = SourceIntelligenceService(session, storage=storage)
    return session, service


def _mock_fetcher(handlers: dict[str, bytes]) -> SourceUrlFetcher:
    def route(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for key, payload in handlers.items():
            if key in url:
                return httpx.Response(
                    200,
                    request=request,
                    headers={"content-type": "application/pdf"},
                    content=payload,
                )
        return httpx.Response(404, request=request)

    return SourceUrlFetcher(
        timeout_seconds=3,
        max_bytes=8_000_000,
        max_redirects=3,
        resolver=_PUBLIC_RESOLVER,
        transport=httpx.MockTransport(route),
    )


# --- AC-F01 ---


def test_f01_forged_solver_dict_never_passes() -> None:
    verdict = verify_mcq_answer(
        selected="A",
        correct="A",
        independent_solver_evidence={"kind": "independent_solver"},
    )
    assert verdict.outcome == VerificationOutcome.REVIEW_REQUIRED
    assert "caller_supplied_solver_evidence_rejected" in verdict.issue_codes


def test_f01_infinite_tolerance_rejected() -> None:
    verdict = verify_numerical_answer(
        submitted="1",
        expected="1",
        tolerance=float("inf"),
        units_required=False,
        independent_solver_evidence=None,
    )
    assert verdict.outcome == VerificationOutcome.REVIEW_REQUIRED


def test_f01_persisted_mcq_pass_and_stale_fail(tmp_path: Path) -> None:
    session, _ = _session(tmp_path)
    pack = ensure_jee_advanced_exam_pack(session)
    version = ensure_exam_version(
        session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    org, inst = "org-ac", "inst-ac"
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
    ok = verify_persisted_mcq(
        session,
        question=q,
        organization_id=org,
        institution_id=inst,
        selected="A",
        correct="A",
    )
    assert ok.outcome == VerificationOutcome.PASS
    assert ok.demonstration_only is True

    foreign = verify_persisted_mcq(
        session,
        question=q,
        organization_id="other-org",
        institution_id=inst,
        selected="A",
        correct="A",
    )
    assert foreign.outcome == VerificationOutcome.REVIEW_REQUIRED

    q.stem_text = q.stem_text + " tampered"
    session.flush()
    stale = verify_persisted_mcq(
        session,
        question=q,
        organization_id=org,
        institution_id=inst,
        selected="A",
        correct="A",
    )
    assert stale.outcome == VerificationOutcome.REVIEW_REQUIRED


def test_f01_multiselect_full_set(tmp_path: Path) -> None:
    session, _ = _session(tmp_path)
    pack = ensure_jee_advanced_exam_pack(session)
    version = ensure_exam_version(
        session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    org, inst = "org-ms", "inst-ms"
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
    miss = verify_persisted_multiselect(
        session,
        question=q,
        organization_id=org,
        institution_id=inst,
        selected=frozenset({"A", "B"}),
        correct=frozenset({"A"}),
    )
    assert miss.outcome == VerificationOutcome.FAIL


def test_f01_numerical_finite_tolerance(tmp_path: Path) -> None:
    session, _ = _session(tmp_path)
    pack = ensure_jee_advanced_exam_pack(session)
    version = ensure_exam_version(
        session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    org, inst = "org-num", "inst-num"
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
    bad_tol = verify_persisted_numerical(
        session,
        question=q,
        organization_id=org,
        institution_id=inst,
        submitted="1.0",
        expected="1.0",
        tolerance=float("nan"),
        units_required=False,
    )
    assert bad_tol.outcome == VerificationOutcome.REVIEW_REQUIRED
    assert not math.isfinite(float("nan"))


# --- AC-F02 ---


def test_f02_caller_flag_does_not_grant_official() -> None:
    layer = resolve_constraint_layer(
        trust_mode=JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026,
        official_rule_pin_present=True,
    )
    assert layer != ConstraintLayer.OFFICIAL_APPROVED


def test_f02_db_backed_official_fail_closed(tmp_path: Path) -> None:
    session, _ = _session(tmp_path)
    pack = ensure_jee_advanced_exam_pack(session)
    version = ensure_exam_version(
        session,
        pack=pack,
        profile_kind=AdvancedProfileKind.REFERENCE_2026,
        academic_year="2026",
    )
    layer, issues = resolve_authoritative_constraint_layer(
        session,
        exam_version_id=str(version.id),
        trust_mode=JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026,
    )
    assert layer != ConstraintLayer.OFFICIAL_APPROVED
    assert issues


# --- AC-F03 ---


def test_f03_syllabus_not_ready_without_authority(tmp_path: Path) -> None:
    session, _ = _session(tmp_path)
    report = build_reference_syllabus_catalogue(session)
    assert report.status in {CatalogueStatus.SOURCE_PENDING, CatalogueStatus.MAPPING_REVIEW_PENDING}
    assert report.status != CatalogueStatus.READY


# --- AC-F04 ---


def test_f04_gateway_probe_executes_calls() -> None:
    verdict, calls = run_scoped_generation_probe(item_id="probe-1", run_id="run-probe-1")
    assert calls >= 2
    assert verdict.outcome == VerificationOutcome.PASS


def test_f04_historical_inventory_not_analyzable(tmp_path: Path) -> None:
    session, _ = _session(tmp_path)
    report = build_historical_inventory(session)
    assert "item_level_evidence_not_analyzable" in report.issue_codes


# --- AC-F05 ---


def test_f05_brochure_alternate_requested_url_persisted(tmp_path: Path) -> None:
    from app.jee_advanced.core_test_fixtures import _simple_pdf_bytes

    slot = next(s for s in JEE_ADVANCED_2026_SOURCE_SLOTS if "brochure" in s.slot_id)
    session, service = _session(tmp_path)
    payload = _simple_pdf_bytes("JEE Advanced information brochure 2026 IBEnglish")
    service.fetcher = _mock_fetcher({BROCHURE_DISCOVERY_URL_ALTERNATE: payload})
    report = stage_official_slot(session, service, slot)
    session.commit()
    assert report.revision_id
    revision = session.get(SourceRevision, report.revision_id)
    assert revision is not None
    meta = revision.metadata_json or {}
    assert BROCHURE_DISCOVERY_URL_ALTERNATE in str(meta.get("requested_url") or "")


def test_f05_scope_map_sums_to_36_rows() -> None:
    counts = load_repo_scope_counts()
    assert counts["TOTAL"] == 36
    assert sum(counts[s] for s in ("PASS", "PARTIAL", "SOURCE_PENDING", "NOT_STARTED")) == 36