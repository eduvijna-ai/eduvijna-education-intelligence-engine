from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learner_intelligence.attempt_meta import (
    catalog_key_from_attempt,
    harness_binding_from_attempt,
)
from app.learner_intelligence.context import authorize_actor, load_bound_attempt
from app.learner_intelligence.contracts import (
    AttemptOutcome,
    CreateAttemptRequest,
    FinalizeAttemptRequest,
    RecordResponseRequest,
    SnapshotItem,
    TrustedActorContext,
)
from app.learner_intelligence.eligibility import evaluate_assessment_eligibility
from app.learner_intelligence.enums import AttemptState, EligibilityVerdict, IssueCode
from app.learner_intelligence.finalization import FinalizationError, finalize_attempt
from app.learner_intelligence.gate import blocked_outcome, require_harness_or_blocked
from app.learner_intelligence.harness_runtime import HARNESS_BIND_KEY
from app.learner_intelligence.lifecycle import (
    abandon_attempt,
    transition_attempt,
    validate_and_store_response,
)
from app.learner_intelligence.snapshot import (
    compute_assessment_fingerprint,
    compute_item_fingerprint,
    learner_facing_snapshot,
    validate_items_structure,
    verify_item_matches_persisted_row,
)
from app.models.learner_intelligence import (
    AssessmentAttempt,
    IssuedItemSnapshot,
    LearnerProfileVersion,
)


def _harness_binding_for_session(session: Session) -> str | None:
    secret = session.info.get(HARNESS_BIND_KEY)
    return str(secret) if secret else None


def _require_harness(
    session: Session,
    *,
    attempt: AssessmentAttempt | None = None,
) -> IssueCode | None:
    gate = require_harness_or_blocked(session)
    if gate is not None:
        return gate
    binding = _harness_binding_for_session(session)
    if attempt is not None:
        expected = harness_binding_from_attempt(attempt)
        if expected and binding != expected:
            return IssueCode.NOT_ELIGIBLE
    return None


class LearnerIntelligenceService:
    """Day 15 orchestration — isolated harness session only."""

    def create_attempt(
        self, session: Session, request: CreateAttemptRequest
    ) -> tuple[AssessmentAttempt | None, AttemptOutcome]:
        harness_err = _require_harness(session)
        if harness_err is not None:
            return None, blocked_outcome(code=harness_err)
        auth_err = authorize_actor(session, request.actor)
        if auth_err is not None:
            return None, AttemptOutcome(
                attempt_id="",
                state=AttemptState.CREATED,
                eligibility_verdict=EligibilityVerdict.BLOCKED_UNVERIFIED,
                issue_codes=[auth_err],
            )
        verdict = evaluate_assessment_eligibility(request)
        if verdict != EligibilityVerdict.ELIGIBLE:
            return None, AttemptOutcome(
                attempt_id="",
                state=AttemptState.CREATED,
                eligibility_verdict=verdict,
                issue_codes=[IssueCode.NOT_ELIGIBLE],
            )
        structural = validate_items_structure(request.items)
        if structural is not None:
            return None, AttemptOutcome(
                attempt_id="",
                state=AttemptState.CREATED,
                eligibility_verdict=EligibilityVerdict.BLOCKED_SCOPE,
                issue_codes=[structural],
            )

        existing = session.scalar(
            select(AssessmentAttempt).where(
                AssessmentAttempt.organization_id == request.actor.organization_id,
                AssessmentAttempt.institution_id == request.actor.institution_id,
                AssessmentAttempt.learner_id == request.actor.learner_id,
                AssessmentAttempt.idempotency_key == request.idempotency_key,
            )
        )
        if existing is not None:
            if existing.assessment_key != request.assessment_key:
                return None, blocked_outcome(
                    attempt_id=str(existing.id), code=IssueCode.IDEMPOTENCY_CONFLICT
                )
            if catalog_key_from_attempt(existing) != (request.catalog_key or ""):
                return None, blocked_outcome(
                    attempt_id=str(existing.id), code=IssueCode.IDEMPOTENCY_CONFLICT
                )
            server_items_replay = [
                SnapshotItem.model_validate(r.snapshot_json)
                for r in session.scalars(
                    select(IssuedItemSnapshot)
                    .where(IssuedItemSnapshot.attempt_id == str(existing.id))
                    .order_by(IssuedItemSnapshot.item_sequence)
                ).all()
            ]
            if compute_assessment_fingerprint(server_items_replay) != existing.content_fingerprint:
                return None, blocked_outcome(
                    attempt_id=str(existing.id), code=IssueCode.IDEMPOTENCY_CONFLICT
                )
            return existing, AttemptOutcome(
                attempt_id=str(existing.id),
                state=AttemptState(existing.state),
                eligibility_verdict=EligibilityVerdict.ELIGIBLE,
                committed=AttemptState(existing.state) == AttemptState.FINALIZED,
                total_marks=existing.total_marks,
                max_marks=existing.max_marks,
            )

        server_items: list[SnapshotItem] = []
        for item in request.items:
            fp = compute_item_fingerprint(item)
            if item.content_fingerprint != fp:
                return None, AttemptOutcome(
                    attempt_id="",
                    state=AttemptState.CREATED,
                    eligibility_verdict=EligibilityVerdict.BLOCKED_UNVERIFIED,
                    issue_codes=[IssueCode.SNAPSHOT_MISMATCH],
                )
            server_items.append(item.model_copy(update={"content_fingerprint": fp}))
        fingerprint = compute_assessment_fingerprint(server_items)
        binding = _harness_binding_for_session(session) or ""
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
            metadata_json={
                "catalog_key": request.catalog_key or "",
                "harness_binding_secret": binding,
            },
        )
        session.add(attempt)
        session.flush()
        for item in server_items:
            item_json = item.model_dump(mode="json")
            fp = compute_item_fingerprint(item)
            session.add(
                IssuedItemSnapshot(
                    attempt_id=str(attempt.id),
                    item_sequence=item.item_sequence,
                    question_id=item.question_id,
                    snapshot_json=item_json,
                    content_fingerprint=fp,
                    marks_if_correct=item.marks_if_correct,
                    marks_if_incorrect=item.marks_if_incorrect,
                    marks_if_blank=item.marks_if_blank,
                    scoring_policy_version=item.scoring_policy_version,
                )
            )
        profile = session.scalar(
            select(LearnerProfileVersion).where(
                LearnerProfileVersion.learner_id == request.actor.learner_id,
                LearnerProfileVersion.organization_id == request.actor.organization_id,
                LearnerProfileVersion.institution_id == request.actor.institution_id,
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
                    state_json={"status": "harness_initialized"},
                    synthetic_harness_only=True,
                )
            )
        session.flush()
        return attempt, AttemptOutcome(
            attempt_id=str(attempt.id),
            state=AttemptState.CREATED,
            eligibility_verdict=EligibilityVerdict.ELIGIBLE,
        )

    def learner_view_items(
        self,
        session: Session,
        actor: TrustedActorContext,
        attempt_id: str,
    ) -> tuple[list[dict[str, object]], list[IssueCode]]:
        harness_err = _require_harness(session)
        if harness_err is not None:
            return [], [harness_err]
        err = authorize_actor(session, actor)
        if err is not None:
            return [], [err]
        attempt, load_err = load_bound_attempt(session, actor, attempt_id)
        if load_err is not None or attempt is None:
            return [], [load_err or IssueCode.OUT_OF_SCOPE]
        bind_err = _require_harness(session, attempt=attempt)
        if bind_err is not None:
            return [], [bind_err]
        rows = session.scalars(
            select(IssuedItemSnapshot)
            .where(IssuedItemSnapshot.attempt_id == str(attempt.id))
            .order_by(IssuedItemSnapshot.item_sequence)
        ).all()
        views: list[dict[str, object]] = []
        for row in rows:
            item = SnapshotItem.model_validate(row.snapshot_json)
            if not verify_item_matches_persisted_row(
                item,
                row_fingerprint=row.content_fingerprint,
                row_marks_correct=row.marks_if_correct,
                row_marks_incorrect=row.marks_if_incorrect,
                row_marks_blank=row.marks_if_blank,
                policy_version=row.scoring_policy_version,
                row_question_id=row.question_id,
                row_item_sequence=row.item_sequence,
            ):
                return [], [IssueCode.SNAPSHOT_MISMATCH]
            views.append(learner_facing_snapshot(item, snapshot_row_id=str(row.id)))
        return views, []

    def record_response(
        self,
        session: Session,
        request: RecordResponseRequest,
    ) -> tuple[bool, list[IssueCode]]:
        harness_err = _require_harness(session)
        if harness_err is not None:
            return False, [harness_err]
        err = authorize_actor(session, request.actor)
        if err is not None:
            return False, [err]
        attempt, load_err = load_bound_attempt(session, request.actor, request.attempt_id)
        if load_err is not None or attempt is None:
            return False, [load_err or IssueCode.OUT_OF_SCOPE]
        bind_err = _require_harness(session, attempt=attempt)
        if bind_err is not None:
            return False, [bind_err]

        row = session.scalar(
            select(IssuedItemSnapshot).where(
                IssuedItemSnapshot.attempt_id == str(attempt.id),
                IssuedItemSnapshot.item_sequence == request.item_sequence,
            )
        )
        if row is None:
            return False, [IssueCode.UNKNOWN_QUESTION]
        item = SnapshotItem.model_validate(row.snapshot_json)
        if not verify_item_matches_persisted_row(
            item,
            row_fingerprint=row.content_fingerprint,
            row_marks_correct=row.marks_if_correct,
            row_marks_incorrect=row.marks_if_incorrect,
            row_marks_blank=row.marks_if_blank,
            policy_version=row.scoring_policy_version,
            row_question_id=row.question_id,
            row_item_sequence=row.item_sequence,
        ):
            return False, [IssueCode.SNAPSHOT_MISMATCH]
        resp, issues = validate_and_store_response(
            session, attempt, request, item_model_json=row.snapshot_json
        )
        if issues:
            return False, issues
        if AttemptState(attempt.state) == AttemptState.CREATED:
            transition_attempt(session, attempt, AttemptState.IN_PROGRESS)
        session.flush()
        return resp is not None, []

    def finalize(self, session: Session, request: FinalizeAttemptRequest) -> AttemptOutcome:
        harness_err = _require_harness(session)
        if harness_err is not None:
            return blocked_outcome(attempt_id=request.attempt_id, code=harness_err)
        try:
            return finalize_attempt(session, request)
        except FinalizationError as exc:
            return AttemptOutcome(
                attempt_id=request.attempt_id,
                state=AttemptState.IN_PROGRESS,
                eligibility_verdict=EligibilityVerdict.ELIGIBLE,
                issue_codes=[exc.code],
                committed=False,
            )

    def abandon(
        self, session: Session, actor: TrustedActorContext, attempt_id: str
    ) -> list[IssueCode]:
        harness_err = _require_harness(session)
        if harness_err is not None:
            return [harness_err]
        err = authorize_actor(session, actor)
        if err is not None:
            return [err]
        attempt, load_err = load_bound_attempt(session, actor, attempt_id)
        if load_err is not None or attempt is None:
            return [load_err or IssueCode.OUT_OF_SCOPE]
        bind_err = _require_harness(session, attempt=attempt)
        if bind_err is not None:
            return [bind_err]
        abandon_attempt(session, attempt)
        session.flush()
        return []