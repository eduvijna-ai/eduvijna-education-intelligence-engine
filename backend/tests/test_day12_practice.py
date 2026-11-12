from app.jee_advanced.constants import EDUVIJNA_DERIVED_TOPIC_GROUP, JEE_ADVANCED_PACK_CODE, MATHEMATICS_SUBJECT
from app.jee_advanced.contracts import SubjectPracticeRequest, TopicPracticeRequest
from app.jee_advanced.enums import AdvancedPlanVerdict, AdvancedProfileKind, JeeAdvancedSourceTrustMode
from app.jee_advanced.practice_service import JeeAdvancedPracticeService


def test_d12_18_mathematics_ten_exact_synthetic() -> None:
    svc = JeeAdvancedPracticeService()
    result = svc.allocate_subject(
        SubjectPracticeRequest(
            exam_pack_code=JEE_ADVANCED_PACK_CODE,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            subject_code=MATHEMATICS_SUBJECT,
            requested_count=10,
        )
    )
    assert result.verdict == AdvancedPlanVerdict.PASS
    assert result.delivered_count == 10
    assert len(result.questions) == 10
    assert all(q.independently_validated for q in result.questions)


def test_d12_19_algebra_ten_exact_synthetic() -> None:
    svc = JeeAdvancedPracticeService()
    result = svc.allocate_topic(
        TopicPracticeRequest(
            exam_pack_code=JEE_ADVANCED_PACK_CODE,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            subject_code=MATHEMATICS_SUBJECT,
            topic_group=EDUVIJNA_DERIVED_TOPIC_GROUP,
            requested_count=10,
        )
    )
    assert result.verdict == AdvancedPlanVerdict.PASS
    assert result.delivered_count == 10


def test_shortage_nine_of_ten_is_typed_shortage() -> None:
    svc = JeeAdvancedPracticeService()
    result = svc.allocate_subject(
        SubjectPracticeRequest(
            exam_pack_code=JEE_ADVANCED_PACK_CODE,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            subject_code=MATHEMATICS_SUBJECT,
            requested_count=25,
        )
    )
    assert result.verdict == AdvancedPlanVerdict.SHORTAGE
    assert result.delivered_count < 25
