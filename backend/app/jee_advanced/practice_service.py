from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.jee_advanced.constants import (
    EDUVIJNA_DERIVED_TOPIC_GROUP,
    MATHEMATICS_SUBJECT,
)
from app.jee_advanced.contracts import (
    PracticeQuestionRef,
    SubjectPracticeRequest,
    SubjectPracticeResult,
    TopicPracticeRequest,
    TopicPracticeResult,
)
from app.jee_advanced.enums import (
    AdvancedIssueCode,
    AdvancedPlanVerdict,
    AdvancedProfileKind,
    JeeAdvancedSourceTrustMode,
)
from app.jee_advanced.persisted_practice import select_trusted_questions
from app.jee_advanced.scope_guard import (
    validate_exam_pack_scope,
    validate_mathematics_topic,
    validate_subject_scope,
)
from app.jee_advanced.source_registry import reference_evidence_ready
from app.jee_advanced.synthetic_fixtures import SyntheticFixturePool, build_synthetic_fixture_pool
from app.jee_advanced.trust_guard import validate_trust_coherence


class JeeAdvancedPracticeService:
    """D12-18 / D12-19 exact-count practice; synthetic fixtures; reference fail-closed."""

    def __init__(self, *, fixture_pool: SyntheticFixturePool | None = None) -> None:
        self._pool = fixture_pool or build_synthetic_fixture_pool()

    def allocate_subject(
        self,
        request: SubjectPracticeRequest,
        *,
        session: Session | None = None,
        exam_version_id: str | None = None,
    ) -> SubjectPracticeResult:
        issues = list(validate_exam_pack_scope(request.exam_pack_code))
        issues.extend(validate_subject_scope(request.subject_code))
        issues.extend(
            validate_trust_coherence(
                profile_kind=request.profile_kind,
                trust_mode=request.trust_mode,
                academic_year=request.metadata_json.get("academic_year", "2026"),
            )
        )
        if issues:
            return self._shortage_result_subject(
                request,
                verdict=AdvancedPlanVerdict.FAIL,
                issues=issues,
                delivered=[],
            )

        if request.metadata_json.get("use_persisted_pool") and session and exam_version_id:
            org = str(request.organization_id or "")
            if not org:
                return self._shortage_result_subject(
                    request,
                    verdict=AdvancedPlanVerdict.FAIL,
                    issues=[AdvancedIssueCode.TENANT_ISOLATION],
                    delivered=[],
                )
            selected, alloc_issues, verdict = select_trusted_questions(
                session,
                organization_id=org,
                institution_id=request.metadata_json.get("institution_id"),
                exam_version_id=exam_version_id,
                subject_code=request.subject_code,
                topic_group=None,
                requested_count=request.requested_count,
            )
            return SubjectPracticeResult(
                verdict=verdict,
                subject_code=request.subject_code,
                requested_count=request.requested_count,
                delivered_count=len(selected),
                questions=selected,
                issue_codes=alloc_issues,
                trust_mode=request.trust_mode,
                result_fingerprint=self._fingerprint(request.model_dump(), selected),
                metadata_json={"persisted_selection": True},
            )

        if request.trust_mode is not JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE:
            needs_ref = request.profile_kind is AdvancedProfileKind.REFERENCE_2026
            if needs_ref and not reference_evidence_ready(session):
                return self._shortage_result_subject(
                    request,
                    verdict=AdvancedPlanVerdict.SOURCE_PENDING,
                    issues=[*issues, AdvancedIssueCode.UNAPPROVED_SOURCE],
                    delivered=[],
                )
            return self._shortage_result_subject(
                request,
                verdict=AdvancedPlanVerdict.REFERENCE_NOT_VERIFIED,
                issues=[*issues, AdvancedIssueCode.UNAPPROVED_SOURCE],
                delivered=[],
            )

        if issues:
            return self._shortage_result_subject(
                request,
                verdict=AdvancedPlanVerdict.FAIL,
                issues=issues,
                delivered=[],
            )

        if request.subject_code.lower() != MATHEMATICS_SUBJECT:
            return self._shortage_result_subject(
                request,
                verdict=AdvancedPlanVerdict.FAIL,
                issues=[AdvancedIssueCode.WRONG_SUBJECT],
                delivered=[],
            )

        pool = list(self._pool.mathematics)
        selected, alloc_issues, verdict = self._select_exact(pool, request.requested_count)
        return SubjectPracticeResult(
            verdict=verdict,
            subject_code=request.subject_code,
            requested_count=request.requested_count,
            delivered_count=len(selected),
            questions=selected,
            issue_codes=alloc_issues,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            result_fingerprint=self._fingerprint(request.model_dump(), selected),
            metadata_json={"fixture_pool_fingerprint": self._pool.pool_fingerprint},
        )

    def allocate_topic(
        self,
        request: TopicPracticeRequest,
        *,
        session: Session | None = None,
        exam_version_id: str | None = None,
    ) -> TopicPracticeResult:
        issues = list(validate_exam_pack_scope(request.exam_pack_code))
        issues.extend(
            validate_mathematics_topic(request.topic_group, subject_code=request.subject_code)
        )
        issues.extend(
            validate_trust_coherence(
                profile_kind=request.profile_kind,
                trust_mode=request.trust_mode,
                academic_year=request.metadata_json.get("academic_year", "2026"),
            )
        )
        if issues:
            return TopicPracticeResult(
                verdict=AdvancedPlanVerdict.FAIL,
                subject_code=request.subject_code,
                topic_group=request.topic_group,
                requested_count=request.requested_count,
                delivered_count=0,
                questions=[],
                issue_codes=issues,
                trust_mode=request.trust_mode,
                metadata_json={},
            )

        if request.metadata_json.get("use_persisted_pool") and session and exam_version_id:
            org = str(request.organization_id or "")
            if not org:
                return TopicPracticeResult(
                    verdict=AdvancedPlanVerdict.FAIL,
                    subject_code=request.subject_code,
                    topic_group=request.topic_group,
                    requested_count=request.requested_count,
                    delivered_count=0,
                    questions=[],
                    issue_codes=[AdvancedIssueCode.TENANT_ISOLATION],
                    trust_mode=request.trust_mode,
                    metadata_json={},
                )
            selected, alloc_issues, verdict = select_trusted_questions(
                session,
                organization_id=org,
                institution_id=request.metadata_json.get("institution_id"),
                exam_version_id=exam_version_id,
                subject_code=request.subject_code,
                topic_group=request.topic_group,
                requested_count=request.requested_count,
            )
            return TopicPracticeResult(
                verdict=verdict,
                subject_code=request.subject_code,
                topic_group=request.topic_group,
                requested_count=request.requested_count,
                delivered_count=len(selected),
                questions=selected,
                issue_codes=alloc_issues,
                trust_mode=request.trust_mode,
                result_fingerprint=self._fingerprint(request.model_dump(), selected),
                metadata_json={"persisted_selection": True},
            )

        if request.trust_mode is not JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE:
            return TopicPracticeResult(
                verdict=AdvancedPlanVerdict.SOURCE_PENDING,
                subject_code=request.subject_code,
                topic_group=request.topic_group,
                requested_count=request.requested_count,
                delivered_count=0,
                questions=[],
                issue_codes=[*issues, AdvancedIssueCode.UNAPPROVED_SOURCE],
                trust_mode=request.trust_mode,
                metadata_json={},
            )

        if issues:
            return TopicPracticeResult(
                verdict=AdvancedPlanVerdict.FAIL,
                subject_code=request.subject_code,
                topic_group=request.topic_group,
                requested_count=request.requested_count,
                delivered_count=0,
                questions=[],
                issue_codes=issues,
                trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
                metadata_json={},
            )

        if request.topic_group.lower() != EDUVIJNA_DERIVED_TOPIC_GROUP:
            return TopicPracticeResult(
                verdict=AdvancedPlanVerdict.FAIL,
                subject_code=request.subject_code,
                topic_group=request.topic_group,
                requested_count=request.requested_count,
                delivered_count=0,
                questions=[],
                issue_codes=[AdvancedIssueCode.WRONG_TOPIC, AdvancedIssueCode.OFF_TOPIC_FILLER],
                trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
                metadata_json={},
            )

        pool = list(self._pool.algebra)
        selected, alloc_issues, verdict = self._select_exact(pool, request.requested_count)
        return TopicPracticeResult(
            verdict=verdict,
            subject_code=request.subject_code,
            topic_group=request.topic_group,
            requested_count=request.requested_count,
            delivered_count=len(selected),
            questions=selected,
            issue_codes=alloc_issues,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            result_fingerprint=self._fingerprint(request.model_dump(), selected),
            metadata_json={
                "derived_topic_group": True,
                "fixture_pool_fingerprint": self._pool.pool_fingerprint,
            },
        )

    def _select_exact(
        self,
        pool: list[PracticeQuestionRef],
        requested: int,
    ) -> tuple[list[PracticeQuestionRef], list[AdvancedIssueCode], AdvancedPlanVerdict]:
        validated = [q for q in pool if q.independently_validated]
        if len(validated) < requested:
            return (
                validated,
                [AdvancedIssueCode.COUNT_SHORTAGE],
                AdvancedPlanVerdict.SHORTAGE,
            )
        chosen = validated[:requested]
        if len(chosen) != requested:
            return chosen, [AdvancedIssueCode.COUNT_SHORTAGE], AdvancedPlanVerdict.SHORTAGE
        if any(not q.independently_validated for q in chosen):
            return [], [AdvancedIssueCode.UNVALIDATED_QUESTION], AdvancedPlanVerdict.FAIL
        return chosen, [], AdvancedPlanVerdict.PASS

    def _shortage_result_subject(
        self,
        request: SubjectPracticeRequest,
        *,
        verdict: AdvancedPlanVerdict,
        issues: list[AdvancedIssueCode],
        delivered: list[PracticeQuestionRef],
    ) -> SubjectPracticeResult:
        return SubjectPracticeResult(
            verdict=verdict,
            subject_code=request.subject_code,
            requested_count=request.requested_count,
            delivered_count=len(delivered),
            questions=delivered,
            issue_codes=issues,
            trust_mode=request.trust_mode,
            metadata_json={},
        )

    @staticmethod
    def _fingerprint(
        request_payload: dict[str, object],
        questions: list[PracticeQuestionRef],
    ) -> str:
        body = {
            "request": request_payload,
            "question_ids": [q.question_id for q in questions],
        }
        return hashlib.sha256(
            json.dumps(body, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()
