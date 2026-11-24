"""Day 15 verification harness (D15-34)."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.ca_imat_eapcet.containment import ISSUANCE_DISABLED
from app.ca_imat_eapcet.persistence_bridge import attempt_canonical_issuance
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.learner_intelligence.contracts import (
    CreateAttemptRequest,
    FinalizeAttemptRequest,
    RecordResponseRequest,
)
from app.learner_intelligence.eligibility import evaluate_assessment_eligibility
from app.learner_intelligence.enums import (
    AttemptState,
    EligibilityTrustMode,
    EligibilityVerdict,
    ResponseKind,
)
from app.learner_intelligence.fixtures import (
    VERIFY_HARNESS_PROOF,
    assessment_content_fingerprint,
    build_two_item_synthetic_assessment,
    seed_synthetic_tenant,
)
from app.learner_intelligence.governance import build_day15_governance_record
from app.learner_intelligence.handoff import build_day16_handoff
from app.learner_intelligence.scope_ledger import load_repo_scope_counts
from app.learner_intelligence.service import LearnerIntelligenceService
from app.models.learner_intelligence import (
    ConceptMasteryRecord,
    DiagnosticProfileEvent,
    ScoreEvidenceEvent,
)
from app.verification.candidate_revision import RevisionEvidence, resolve_revision_evidence


def build_verification_report(session: Session, *, revision: RevisionEvidence) -> dict[str, object]:
    if revision.evidence_error or not revision.sha_aligned:
        return _revision_failure_report(revision)

    actor = seed_synthetic_tenant(session)
    session.commit()
    items = build_two_item_synthetic_assessment()
    fp = assessment_content_fingerprint(items)
    svc = LearnerIntelligenceService()

    create_req = CreateAttemptRequest(
        actor=actor,
        trust_mode=EligibilityTrustMode.SYNTHETIC_D15_HARNESS,
        assessment_key="d15-verify-assessment",
        idempotency_key="d15-verify-attempt-1",
        items=items,
        synthetic_harness_proof=VERIFY_HARNESS_PROOF,
    )
    eligibility = evaluate_assessment_eligibility(create_req)
    attempt, created = svc.create_attempt(session, create_req)
    assert attempt is not None

    forged = create_req.model_copy(update={"synthetic_harness_proof": "FORGED_APPROVED_FLAG"})
    forged_verdict = evaluate_assessment_eligibility(forged)

    view = svc.learner_view_items(session, str(attempt.id))
    keys_leaked = False
    for row in view:
        opts = row.get("options")
        if not isinstance(opts, list):
            continue
        for opt in opts:
            if isinstance(opt, dict) and opt.get("is_correct") is not None:
                keys_leaked = True
                break
        if keys_leaked:
            break

    ok1, _ = svc.record_response(
        session,
        attempt,
        RecordResponseRequest(
            actor=actor,
            attempt_id=str(attempt.id),
            item_sequence=1,
            response_kind=ResponseKind.SINGLE_CHOICE,
            selected_option_keys=["A"],
        ),
    )
    ok2, _ = svc.record_response(
        session,
        attempt,
        RecordResponseRequest(
            actor=actor,
            attempt_id=str(attempt.id),
            item_sequence=2,
            response_kind=ResponseKind.NUMERIC,
            numeric_value="7",
        ),
    )

    fin = svc.finalize(
        session,
        attempt,
        FinalizeAttemptRequest(
            actor=actor,
            attempt_id=str(attempt.id),
            idempotency_key="d15-finalize-1",
            content_binding_fingerprint=fp,
        ),
    )
    replay = svc.finalize(
        session,
        attempt,
        FinalizeAttemptRequest(
            actor=actor,
            attempt_id=str(attempt.id),
            idempotency_key="d15-finalize-1",
            content_binding_fingerprint=fp,
        ),
    )

    score_count = session.scalar(select(ScoreEvidenceEvent.id).limit(1))
    mastery_count = session.scalar(select(ConceptMasteryRecord.id).limit(1))
    diag_count = session.scalar(select(DiagnosticProfileEvent.id).limit(1))
    handoff = build_day16_handoff(
        session,
        organization_id=actor.organization_id,
        institution_id=actor.institution_id,
        learner_id=actor.learner_id,
    )

    persistence_contained = attempt_canonical_issuance(
        session=session,
        questions=[],
        organization_id=actor.organization_id,
        institution_id=actor.institution_id,
        exam_version_id="none",
        source_version="synthetic",
        idempotency_key="d15-blocked",
    )

    scope_counts = load_repo_scope_counts()
    governance = build_day15_governance_record()

    synthetic_ok = (
        eligibility == EligibilityVerdict.ELIGIBLE
        and forged_verdict == EligibilityVerdict.BLOCKED_FORGED_APPROVAL
        and not keys_leaked
        and ok1
        and ok2
        and fin.state == AttemptState.FINALIZED
        and fin.committed
        and fin.total_marks == Decimal("3")
        and replay.total_marks == fin.total_marks
        and score_count is not None
        and mastery_count is not None
        and diag_count is not None
        and len(handoff.misconception_codes) >= 1
        and not persistence_contained.committed
        and ISSUANCE_DISABLED
    )

    report: dict[str, object] = {
        "ok": synthetic_ok,
        "synthetic_harness_pass": synthetic_ok,
        "production_assessment_eligibility": False,
        "diagnostic_execution_ok": synthetic_ok,
        "governance": governance,
        "scope_ledger_counts": scope_counts,
        "eligibility": {
            "synthetic_eligible": eligibility.value,
            "forged_blocked": forged_verdict.value,
        },
        "attempt": {
            "attempt_id": str(attempt.id),
            "state": fin.state.value,
            "total_marks": str(fin.total_marks),
            "max_marks": str(fin.max_marks),
        },
        "replay_idempotent": replay.total_marks == fin.total_marks,
        "persistence_containment": {
            "issuance_disabled": ISSUANCE_DISABLED,
            "day14_issuance_committed": persistence_contained.committed,
        },
        "handoff": handoff.model_dump(),
        "notes": {
            "compose_smoke": "NOT_RUN",
            "live_postgresql": "NOT_RUN",
            "full_historical_pytest": "NOT_RUN",
            "migration_0021_blocker": "DEFERRED",
            "d15_36_founder_signoff": "NOT_STARTED",
        },
    }
    report.update(revision.as_report_fields())
    return report


def _revision_failure_report(revision: RevisionEvidence) -> dict[str, object]:
    try:
        scope_counts = load_repo_scope_counts()
    except Exception:  # noqa: BLE001
        scope_counts = {"TOTAL": 0, "PARTIAL": 0, "SOURCE_PENDING": 0, "NOT_STARTED": 0}
    return {
        "ok": False,
        "synthetic_harness_pass": False,
        "failure_reason": revision.evidence_error or "SHA_ALIGNMENT_FAILED",
        "scope_ledger_counts": scope_counts,
        **revision.as_report_fields(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Day 15 verification harness")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    revision = resolve_revision_evidence(cwd=Path(__file__).resolve().parents[1])

    try:
        engine = create_engine("sqlite:///:memory:")
        enable_sqlite_foreign_keys(engine)
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            report = build_verification_report(session, revision=revision)
    except Exception as exc:  # noqa: BLE001
        report = {
            "ok": False,
            "failure_reason": f"verification_exception:{type(exc).__name__}",
            **revision.as_report_fields(),
        }

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("Day 15 verification:", "PASS" if report.get("ok") else "FAIL")

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())