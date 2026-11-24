from app.ca_imat_eapcet.authority import resolve_ca_authority, resolve_eapcet_authority
from app.ca_imat_eapcet.constants import CA_FOUNDATION_PACK_CODE
from app.ca_imat_eapcet.content_validation import (
    derive_content_fingerprint,
    validate_and_bind_question_ref,
)
from app.ca_imat_eapcet.contracts import AllocateRequest, QuestionRef
from app.ca_imat_eapcet.eapcet_bilingual import evaluate_bilingual_pair, validate_bilingual_medium
from app.ca_imat_eapcet.enums import (
    Day14ProfileKind,
    Day14SourceTrustMode,
    EapcetStream,
    PlanVerdict,
)
from app.ca_imat_eapcet.imat_solver_check import independent_imat_answer_check
from app.ca_imat_eapcet.practice_service import Day14PracticeService
from app.ca_imat_eapcet.request_guards import validate_requested_count
from app.ca_imat_eapcet.scope_guard import validate_tenant
from app.ca_imat_eapcet.synthetic_fixtures import build_imat_pool


def test_trust_mismatch_fail_closed() -> None:
    svc = Day14PracticeService()
    r = svc.allocate(
        AllocateRequest(
            exam_pack_code=CA_FOUNDATION_PACK_CODE,
            profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
            trust_mode=Day14SourceTrustMode.CA_ICAI_REFERENCE,
            paper_or_section="paper3_quantitative_aptitude",
            requested_count=5,
        )
    )
    assert r.verdict == PlanVerdict.FAIL


def test_invalid_request_count() -> None:
    assert validate_requested_count(0)
    assert validate_requested_count(-1)


def test_tenant_isolation() -> None:
    assert validate_tenant(organization_id="org-a", expected_org="org-b")


def test_ca_future_session() -> None:
    d = resolve_ca_authority(
        profile_kind=Day14ProfileKind.CA_FUTURE_SESSION,
        session_code="future_jan2028",
    )
    assert d.verdict == PlanVerdict.OFFICIAL_NOT_VERIFIED


def test_eapcet_official_without_curator() -> None:
    d = resolve_eapcet_authority(
        profile_kind=Day14ProfileKind.EAPCET_ENGINEERING_2026,
        stream=EapcetStream.ENGINEERING,
        exam_year="2026",
    )
    assert d.verdict == PlanVerdict.SOURCE_PENDING


def test_shortage_typed() -> None:
    svc = Day14PracticeService()
    r = svc.allocate(
        AllocateRequest(
            exam_pack_code=CA_FOUNDATION_PACK_CODE,
            profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            paper_or_section="paper4_business_economics",
            requested_count=200,
        )
    )
    assert r.verdict == PlanVerdict.SHORTAGE


def test_unsupported_bilingual() -> None:
    assert validate_bilingual_medium("hindi_only")


def test_bilingual_requires_evidence() -> None:
    v = evaluate_bilingual_pair(
        "english_telugu",
        english="What is force?",
        vernacular="బలం అంటే ఏమిటి?",
    )
    assert v.verdict == PlanVerdict.REVIEW_REQUIRED


def test_f02_imat_wrong_option_count_fails() -> None:
    bad = QuestionRef(
        question_id="bad",
        paper_or_section="biology",
        fingerprint="x",
        correct_key="A",
        marks_if_correct=1.0,
        marks_if_incorrect=0.0,
        stem_text="IMAT_BIO: Which organelle is primarily responsible for cellular respiration?",
        options={"A": "a", "B": "b", "C": "c", "D": "d"},
    )
    verdict, _, _ = independent_imat_answer_check(bad)
    assert verdict == PlanVerdict.FAIL


def test_f04_fingerprint_tamper() -> None:
    q = build_imat_pool()[0]
    tampered = q.model_copy(update={"fingerprint": "forged"})
    _, verdict, issues = validate_and_bind_question_ref(tampered, options_required=5)
    assert verdict == PlanVerdict.FAIL
    assert issues


def test_imat_biology_topic_filter() -> None:
    svc = Day14PracticeService()
    r = svc.allocate(
        AllocateRequest(
            exam_pack_code="imat",
            profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            paper_or_section="biology",
            requested_count=5,
            topic_code="biology_cell",
        )
    )
    assert r.verdict == PlanVerdict.PASS
    assert all(q.topic_code == "biology_cell" for q in r.questions)
    fp = derive_content_fingerprint(
        stem_text=r.questions[0].stem_text or "",
        options=r.questions[0].options,
        correct_key=r.questions[0].correct_key,
    )
    assert r.questions[0].fingerprint == fp