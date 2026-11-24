from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learner_intelligence.contracts import (
    AttemptOutcome,
    CreateAttemptRequest,
    FinalizeAttemptRequest,
    RecordResponseRequest,
    SnapshotItem,
)
from app.learner_intelligence.eligibility import evaluate_assessment_eligibility
from app.learner_intelligence.enums import AttemptState, EligibilityVerdict, IssueCode
from app.learner_intelligence.finalization import finalize_attempt
from app.learner_intelligence.lifecycle import (
    abandon_attempt,
    validate_and_store_response,
)
from app.learner_intelligence.snapshot import (
    compute_assessment_fingerprint,
    learner_facing_snapshot,
)
from app.models.learner_intelligence import (
    AssessmentAttempt,
    IssuedItemSnapshot,
    LearnerProfileVersion,
)


class LearnerIntelligenceService:
    """Day 15 orchestration — synthetic harness eligible path only."""

    def create_attempt(
        self, session: Session, request: CreateAttemptRequest
    ) -> tuple[AssessmentAttempt | None, AttemptOutcome]:
        verdict = evaluate_assessment_eligibility(request)
        if verdict != EligibilityVerdict.ELIGIBLE:
            return None, AttemptOutcome(
                attempt_id="",
                state=AttemptState.CREATED,
                eligibility_verdict=verdict,
                issue_codes=[IssueCode.NOT_ELIGIBLE],
            )

        existing = session.scalar(
            select(AssessmentAttempt).where(
                AssessmentAttempt.organization_id == request.actor.organization_id,
                AssessmentAttempt.learner_id == request.actor.learner_id,
                AssessmentAttempt.idempotency_key == request.idempotency_key,
            )
        )
        if existing is not None:
            return existing, AttemptOutcome(
                attempt_id=str(existing.id),
                state=AttemptState(existing.state),
                eligibility_verdict=EligibilityVerdict.ELIGIBLE,
                committed=AttemptState(existing.state) == AttemptState.FINALIZED,
                total_marks=existing.total_marks,
                max_marks=existing.max_marks,
            )

        fingerprint = compute_assessment_fingerprint(request.items)
        attempt = AssessmentAttempt(
            organization_id=request.actor.organization_id,
            institution_id=request.actor.institution_id,
            learner_id=request.actor.learner_id,
            state=AttemptState.CREATED.value,
            trust_mode=request.trust_mode.value,
            assessment_key=request.assessment_key,
            exam_pack_code=request.exam_pack_code,
            exam_version_id=request.exam_version_id,
            performance_mode=request.performance_mode.value,
            idempotency_key=request.idempotency_key,
            content_fingerprint=fingerprint,
            synthetic_harness_only=True,
        )
        session.add(attempt)
        session.flush()
        for item in request.items:
            session.add(
                IssuedItemSnapshot(
                    attempt_id=str(attempt.id),
                    item_sequence=item.item_sequence,
                    question_id=item.question_id,
                    snapshot_json=item.model_dump(mode="json"),
                    content_fingerprint=item.content_fingerprint,
                    marks_if_correct=item.marks_if_correct,
                    marks_if_incorrect=item.marks_if_incorrect,
                    marks_if_blank=item.marks_if_blank,
                    scoring_policy_version=item.scoring_policy_version,
                )
            )
        profile = session.scalar(
            select(LearnerProfileVersion).where(
                LearnerProfileVersion.learner_id == request.actor.learner_id
            )
        )
        if profile is None:
            session.add(
                LearnerProfileVersion(
                    organization_id=request.actor.organization_id,
                    institution_id=request.actor.institution_id,
                    learner_id=request.actor.learner_id,
                    profile_version=1,
                    mastery_policy_version="mastery-policy@v1",
                    state_json={"status": "initialized"},
                    synthetic_harness_only=True,
                )
            )
        session.commit()
        return attempt, AttemptOutcome(
            attempt_id=str(attempt.id),
            state=AttemptState.CREATED,
            eligibility_verdict=EligibilityVerdict.ELIGIBLE,
        )

    def learner_view_items(self, session: Session, attempt_id: str) -> list[dict[str, object]]:
        rows = session.scalars(
            select(IssuedItemSnapshot)
            .where(IssuedItemSnapshot.attempt_id == attempt_id)
            .order_by(IssuedItemSnapshot.item_sequence)
        ).all()
        views = []
        for row in rows:
            item = SnapshotItem.model_validate(row.snapshot_json)
            views.append(learner_facing_snapshot(item))
        return views

    def record_response(
        self,
        session: Session,
        attempt: AssessmentAttempt,
        request: RecordResponseRequest,
    ) -> tuple[bool, list[IssueCode]]:
        row = session.scalar(
            select(IssuedItemSnapshot).where(
                IssuedItemSnapshot.attempt_id == str(attempt.id),
                IssuedItemSnapshot.item_sequence == request.item_sequence,
            )
        )
        if row is None:
            return False, [IssueCode.UNKNOWN_QUESTION]
        SnapshotItem.model_validate(row.snapshot_json)
        resp, issues = validate_and_store_response(
            session, attempt, request, item_model_json=row.snapshot_json
        )
        if issues:
            return False, issues
        session.commit()
        return resp is not None, []

    def finalize(
        self, session: Session, attempt: AssessmentAttempt, request: FinalizeAttemptRequest
    ) -> AttemptOutcome:
        return finalize_attempt(session, attempt, request)

    def abandon(self, session: Session, attempt: AssessmentAttempt) -> None:
        abandon_attempt(session, attempt)
        session.commit()