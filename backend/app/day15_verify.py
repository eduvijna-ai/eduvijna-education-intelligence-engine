"""Day 15 verification harness (D15-34)."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.learner_intelligence.contracts import FinalizeAttemptRequest, RecordResponseRequest
from app.learner_intelligence.eligibility import (
    evaluate_assessment_eligibility,
    production_assessment_always_blocked,
)
from app.learner_intelligence.enums import AttemptState, EligibilityVerdict, ResponseKind
from app.learner_intelligence.fixtures import (
    assessment_content_fingerprint,
    build_harness_attempt_request,
    forged_harness_attestation_copy,
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
    create_req = build_harness_attempt_request(
        actor,
        assessment_key="d15-verify-assessment",
        idempotency_key="d15-verify-attempt-1",
    )
    fp = assessment_content_fingerprint(create_req.items)
    svc = LearnerIntelligenceService()

    eligibility = evaluate_assessment_eligibility(create_req)
    attempt, _ = svc.create_attempt(session, create_req)
    assert attempt is not None

    forged = create_req.model_copy(
        update={"harness_attestation": forged_harness_attestation_copy()}
    )
    forged_verdict = evaluate_assessment_eligibility(forged)
    unattested = create_req.model_copy(update={"harness_attestation": None, "catalog_key": None})
    unattested_verdict = evaluate_assessment_eligibility(unattested)

    view, view_issues = svc.learner_view_items(session, actor, str(attempt.id))
    keys_leaked = False
    fingerprint_leaked = "content_fingerprint" in json.dumps(view)
    for row in view:
        opts = row.get("options")
        if not isinstance(opts, list):
            continue
        for opt in opts:
            if isinstance(opt, dict) and opt.get("is_correct") is not None:
                keys_leaked = True

    ok1, _ = svc.record_response(
        session,
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
        FinalizeAttemptRequest(
            actor=actor,
            attempt_id=str(attempt.id),
            idempotency_key="d15-finalize-1",
            content_binding_fingerprint=fp,
        ),
    )
    replay = svc.finalize(
        session,
        FinalizeAttemptRequest(
            actor=actor,
            attempt_id=str(attempt.id),
            idempotency_key="d15-finalize-1",
            content_binding_fingerprint=fp,
        ),
    )

    score_count = session.scalar(select(func.count()).select_from(ScoreEvidenceEvent)) or 0
    mastery_count = session.scalar(select(func.count()).select_from(ConceptMasteryRecord)) or 0
    diag_count = session.scalar(select(func.count()).select_from(DiagnosticProfileEvent)) or 0
    handoff = build_day16_handoff(session, actor)

    scope_counts = load_repo_scope_counts()
    governance = build_day15_governance_record()

    synthetic_ok = (
        production_assessment_always_blocked()
        and eligibility == EligibilityVerdict.ELIGIBLE
        and forged_verdict == EligibilityVerdict.BLOCKED_FORGED_APPROVAL
        and unattested_verdict == EligibilityVerdict.BLOCKED_UNVERIFIED
        and not view_issues
        and not keys_leaked
        and not fingerprint_leaked
        and ok1
        and ok2
        and fin.state == AttemptState.FINALIZED
        and fin.committed
        and fin.total_marks == Decimal("3")
        and fin.max_marks == Decimal("8")
        and replay.total_marks == fin.total_marks
        and score_count == 2
        and mastery_count >= 1
        and diag_count >= 1
        and len(handoff.misconception_codes) >= 1
        and len(handoff.evidence_event_ids) >= 1
        and scope_counts.get("TOTAL") == 36
    )

    report: dict[str, object] = {
        "ok": synthetic_ok,
        "synthetic_harness_pass": synthetic_ok,
        "production_assessment_eligibility": False,
        "production_assessment_blocked_unconditional": production_assessment_always_blocked(),
        "diagnostic_execution_ok": synthetic_ok,
        "governance": governance,
        "scope_ledger_counts": scope_counts,
        "eligibility": {
            "synthetic_eligible": eligibility.value,
            "forged_blocked": forged_verdict.value,
            "unattested_blocked": unattested_verdict.value,
        },
        "attempt": {
            "attempt_id": str(attempt.id),
            "state": fin.state.value,
            "total_marks": str(fin.total_marks),
            "max_marks": str(fin.max_marks),
        },
        "persisted_counts": {
            "score_events": score_count,
            "mastery_records": mastery_count,
            "diagnostic_events": diag_count,
        },
        "replay_idempotent": replay.total_marks == fin.total_marks and replay.committed,
        "handoff": handoff.model_dump(),
        "notes": {
            "compose_smoke": "NOT_RUN",
            "live_postgresql": "NOT_RUN",
            "full_historical_pytest": "NOT_RUN",
            "migration_0021_blocker": "DEFERRED",
            "d15_36_founder_signoff": "NOT_STARTED",
            "day14_issuance_containment_unchanged": True,
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