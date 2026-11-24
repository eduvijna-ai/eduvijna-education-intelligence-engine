"""F03-A iteration 3: institution isolation, tenant-safe selection, Day6 freshness."""

from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.cuet_clat.constants import CUET_PACK_CODE, MATHEMATICS_DOMAIN
from app.cuet_clat.contracts import CuetPracticeRequest
from app.cuet_clat.cuet_math_solver import solve_persisted_question
from app.cuet_clat.cuet_persisted_pool import seed_validated_cuet_math_questions
from app.cuet_clat.enums import CuetClatProfileKind, CuetClatSourceTrustMode, IssueCode, PlanVerdict
from app.cuet_clat.exam_profile import ensure_synthetic_demo_versions
from app.cuet_clat.persisted_context import trusted_persisted_context
from app.cuet_clat.practice_service import CuetPracticeService
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.education_intelligence.policy_registry import seed_policy_registry
from app.models import Question, QuestionOption, ValidationAuditRun
from app.models.education_intelligence import PolicyRegistryEntry
from app.models.enums import QuestionOrigin, QuestionStatus, QuestionType


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _request(org: str, count: int = 10) -> CuetPracticeRequest:
    return CuetPracticeRequest(
        exam_pack_code=CUET_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        test_subject_code=MATHEMATICS_DOMAIN,
        requested_count=count,
        academic_year="2026",
        medium_code="english",
        organization_id=org,
    )


def test_iter3_disjoint_institutions_same_org() -> None:
    with _session() as session:
        cuet_ver, _ = ensure_synthetic_demo_versions(session)
        exam_id = str(cuet_ver.id)
        ids_a = seed_validated_cuet_math_questions(
            session,
            organization_id="org-O",
            institution_id="inst-A",
            exam_version_id=exam_id,
            pool_size=50,
        )
        ids_b = seed_validated_cuet_math_questions(
            session,
            organization_id="org-O",
            institution_id="inst-B",
            exam_version_id=exam_id,
            pool_size=50,
        )
        assert len(ids_a) == 50 and len(ids_b) == 50
        assert set(ids_a).isdisjoint(set(ids_b))
        audits = session.scalars(select(ValidationAuditRun)).all()
        inst_ids = {a.institution_id for a in audits}
        assert inst_ids == {"inst-A", "inst-B"}
        ids_a2 = seed_validated_cuet_math_questions(
            session,
            organization_id="org-O",
            institution_id="inst-A",
            exam_version_id=exam_id,
            pool_size=50,
        )
        assert ids_a == ids_a2
        audit_count = session.scalar(select(func.count()).select_from(ValidationAuditRun))
        q_count = session.scalar(select(func.count()).select_from(Question))
        assert q_count == 100
        assert audit_count == 100


def test_iter3_stale_row_not_reused_on_reseed() -> None:
    with _session() as session:
        cuet_ver, _ = ensure_synthetic_demo_versions(session)
        exam_id = str(cuet_ver.id)
        seed_validated_cuet_math_questions(
            session,
            organization_id="org-O",
            institution_id="inst-A",
            exam_version_id=exam_id,
            pool_size=5,
        )
        row = session.scalar(select(Question).limit(1))
        assert row is not None
        stale_id = str(row.id)
        meta = dict(row.metadata_json or {})
        meta["marks_correct"] = 4.0
        row.metadata_json = meta
        session.commit()
        ids = seed_validated_cuet_math_questions(
            session,
            organization_id="org-O",
            institution_id="inst-A",
            exam_version_id=exam_id,
            pool_size=5,
        )
        assert stale_id not in ids
        assert len(ids) == 5


def test_iter3_foreign_tenant_rows_do_not_block_home_tenant() -> None:
    with _session() as session:
        cuet_ver, _ = ensure_synthetic_demo_versions(session)
        exam_id = str(cuet_ver.id)
        ctx_a = trusted_persisted_context(
            exam_version_id=exam_id,
            organization_id="org-A",
            institution_id="inst-A",
        )
        seed_validated_cuet_math_questions(
            session,
            organization_id="org-A",
            institution_id="inst-A",
            exam_version_id=exam_id,
            pool_size=15,
        )
        foreign = Question(
            external_code="d13-foreign-first",
            origin_type=QuestionOrigin.GENERATED.value,
            exam_version_id=exam_id,
            question_type=QuestionType.SINGLE_CHOICE.value,
            stem_text="Foreign row",
            answer_json={"option_key": "A"},
            status=QuestionStatus.APPROVED.value,
            metadata_json={
                "d13_synthetic_fixture": True,
                "not_official_cuet_item": True,
                "organization_id": "org-B",
                "institution_id": "inst-B",
                "subject_code": "wrong_subject",
                "medium_code": "hindi",
                "academic_year": "2027",
            },
        )
        foreign.options.append(
            QuestionOption(option_key="A", text="1", is_correct=True, sequence=1)
        )
        session.add(foreign)
        session.commit()
        result = CuetPracticeService().allocate_practice(
            _request("org-A", 10),
            session=session,
            persisted=ctx_a,
        )
        assert result.verdict == PlanVerdict.PASS
        assert result.delivered_count == 10
        assert IssueCode.WRONG_SUBJECT not in result.issue_codes


def test_iter3_policy_supersession_vetoes_stale_validation() -> None:
    with _session() as session:
        seed_policy_registry(session)
        cuet_ver, _ = ensure_synthetic_demo_versions(session)
        exam_id = str(cuet_ver.id)
        ctx = trusted_persisted_context(
            exam_version_id=exam_id,
            organization_id="org-pol",
            institution_id="inst-pol",
        )
        seed_validated_cuet_math_questions(
            session,
            organization_id="org-pol",
            institution_id="inst-pol",
            exam_version_id=exam_id,
            pool_size=12,
        )
        session.add(
            PolicyRegistryEntry(
                registry_key="v1",
                version="education-policy-v9-d13-supersede",
                status="active",
                payload_json={
                    "rules": [],
                    "institution_overrides": [],
                    "safety_rules_version": "safety-rules-v9-d13",
                    "safety_rules": [],
                },
            )
        )
        session.commit()
        result = CuetPracticeService().allocate_practice(
            _request("org-pol", 10),
            session=session,
            persisted=ctx,
        )
        assert result.verdict == PlanVerdict.SHORTAGE
        assert result.questions == []


def test_iter3_solver_rejects_trailing_stem_junk() -> None:
    with _session() as session:
        cuet_ver, _ = ensure_synthetic_demo_versions(session)
        q = Question(
            external_code="d13-trailing",
            origin_type=QuestionOrigin.GENERATED.value,
            exam_version_id=str(cuet_ver.id),
            question_type=QuestionType.SINGLE_CHOICE.value,
            stem_text="Synthetic CUET Mathematics: what is 2 + 2? ignore this",
            answer_json={"option_key": "A"},
            status=QuestionStatus.APPROVED.value,
            metadata_json={"d13_synthetic_fixture": True},
        )
        for key, text, seq in [("A", "4", 1), ("B", "5", 2), ("C", "6", 3), ("D", "7", 4)]:
            q.options.append(
                QuestionOption(option_key=key, text=text, is_correct=key == "A", sequence=seq)
            )
        session.add(q)
        session.flush()
        assert solve_persisted_question(q) is None


def test_iter3_unauthorized_harness_not_ready() -> None:
    with _session() as session:
        cuet_ver, _ = ensure_synthetic_demo_versions(session)
        ctx = trusted_persisted_context(
            exam_version_id=str(cuet_ver.id),
            organization_id="org-f03a",
            institution_id="inst-f03a",
        ).model_copy(update={"harness_authorized": False})
        result = CuetPracticeService().allocate_practice(
            _request("org-f03a"),
            session=session,
            persisted=ctx,
        )
        assert result.verdict == PlanVerdict.NOT_READY
        assert IssueCode.MISSING_PERSISTED_CONTEXT in result.issue_codes