from app.ca_imat_eapcet.authority import resolve_ca_authority, resolve_eapcet_authority
from app.ca_imat_eapcet.constants import CA_FOUNDATION_PACK_CODE
from app.ca_imat_eapcet.contracts import AllocateRequest
from app.ca_imat_eapcet.eapcet_bilingual import validate_bilingual_medium
from app.ca_imat_eapcet.enums import (
    Day14ProfileKind,
    Day14SourceTrustMode,
    EapcetStream,
    PlanVerdict,
)
from app.ca_imat_eapcet.practice_service import Day14PracticeService
from app.ca_imat_eapcet.scope_guard import validate_tenant
from app.ca_imat_eapcet.trust_guard import validate_trust_coherence


def test_trust_mismatch_fail_closed() -> None:
    issues = validate_trust_coherence(
        profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
        trust_mode=Day14SourceTrustMode.CA_ICAI_REFERENCE,
        exam_family="ca",
    )
    assert issues


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
            requested_count=10_000,
        )
    )
    assert r.verdict == PlanVerdict.SHORTAGE


def test_unsupported_bilingual() -> None:
    assert validate_bilingual_medium("hindi_only")