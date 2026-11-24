"""Day 15 verification harness (D15-34) — containment milestone."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.learner_intelligence.containment import (
    CONTAINMENT_ACTIVE,
    DURABLE_LEARNER_EVIDENCE,
    PRODUCTION_ASSESSMENT_ELIGIBILITY,
    TRUSTED_MASTERY_EVIDENCE,
)
from app.learner_intelligence.contracts import TrustedActorContext
from app.learner_intelligence.diagnostic_pure import (
    pure_full_correct_scoring_diagnostic,
    pure_missing_item_scoring_diagnostic,
)
from app.learner_intelligence.eligibility import (
    diagnose_pure_catalog_structure,
    evaluate_assessment_eligibility,
    production_assessment_always_blocked,
)
from app.learner_intelligence.enums import EligibilityVerdict, IssueCode
from app.learner_intelligence.finalization import FinalizationError, finalize_attempt
from app.learner_intelligence.fixtures import (
    build_harness_attempt_request,
    forged_harness_attestation_copy,
)
from app.learner_intelligence.governance import build_day15_governance_record
from app.learner_intelligence.handoff import build_day16_handoff
from app.learner_intelligence.mastery import apply_mastery_update
from app.learner_intelligence.query import list_attempts_for_learner, read_mastery_summary
from app.learner_intelligence.scope_ledger import load_repo_scope_counts
from app.learner_intelligence.service import LearnerIntelligenceService
from app.models import Institution, Learner, Organization
from app.models.learner_intelligence import AssessmentAttempt, ScoreEvidenceEvent
from app.verification.candidate_revision import RevisionEvidence, resolve_revision_evidence


def _seed_attack_tenant(session: Session) -> TrustedActorContext:
    """Test-only DB seed (not a Day15 runtime API)."""

    org = Organization(code="d15-attack-org", name="Attack Org", active=True)
    session.add(org)
    session.flush()
    inst = Institution(
        organization_id=str(org.id),
        code="d15-attack-inst",
        name="Attack Inst",
        active=True,
    )
    session.add(inst)
    session.flush()
    learner = Learner(
        institution_id=str(inst.id),
        external_code="d15-attack-learner",
        display_name="Attack Learner",
        active=True,
    )
    session.add(learner)
    session.flush()
    return TrustedActorContext(
        organization_id=str(org.id),
        institution_id=str(inst.id),
        learner_id=str(learner.id),
    )


def _assert_no_learner_rows(session: Session) -> bool:
    attempts = int(session.scalar(select(func.count()).select_from(AssessmentAttempt)) or 0)
    events = int(session.scalar(select(func.count()).select_from(ScoreEvidenceEvent)) or 0)
    return attempts == 0 and events == 0


def _run_containment_verification(revision: RevisionEvidence) -> dict[str, object]:
    if revision.evidence_error or not revision.sha_aligned:
        return _revision_failure_report(revision)

    scope_counts = load_repo_scope_counts()
    governance = build_day15_governance_record()

    pure_partial = pure_missing_item_scoring_diagnostic()
    pure_full = pure_full_correct_scoring_diagnostic()

    actor = TrustedActorContext(
        organization_id="x",
        institution_id="y",
        learner_id="z",
    )
    create_req = build_harness_attempt_request(actor, assessment_key="v", idempotency_key="v1")
    forged = create_req.model_copy(
        update={"harness_attestation": forged_harness_attestation_copy()}
    )
    unattested = create_req.model_copy(update={"harness_attestation": None, "catalog_key": None})

    runtime_eligibility = evaluate_assessment_eligibility(create_req)
    structure_valid = diagnose_pure_catalog_structure(create_req)
    forged_structure = diagnose_pure_catalog_structure(forged)
    unattested_structure = diagnose_pure_catalog_structure(unattested)

    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)

    service_blocks: dict[str, bool] = {}
    with Session(engine) as session:
        attack_actor = _seed_attack_tenant(session)
        session.commit()
        pre_count = session.scalar(select(func.count()).select_from(Organization))

        svc = LearnerIntelligenceService()
        create_req_attacked = build_harness_attempt_request(
            attack_actor,
            assessment_key="attack",
            idempotency_key="attack-1",
        )
        attempt, create_out = svc.create_attempt(session, create_req_attacked)
        service_blocks["create"] = attempt is None and IssueCode.NOT_READY in create_out.issue_codes

        session.info["d15_harness_authorized"] = True
        session.info["d15_harness_binding_secret"] = "forged-secret"
        attempt2, create_out2 = svc.create_attempt(session, create_req_attacked)
        service_blocks["create_premarked_session"] = (
            attempt2 is None and IssueCode.NOT_READY in create_out2.issue_codes
        )

        views, view_issues = svc.learner_view_items(session, attack_actor, "fake-attempt")
        service_blocks["learner_view"] = view_issues == [IssueCode.NOT_READY] and views == []

        from app.learner_intelligence.contracts import FinalizeAttemptRequest, RecordResponseRequest
        from app.learner_intelligence.enums import ResponseKind

        record_ok, record_issues = svc.record_response(
            session,
            RecordResponseRequest(
                actor=attack_actor,
                attempt_id="fake",
                item_sequence=1,
                response_kind=ResponseKind.SINGLE_CHOICE,
                selected_option_keys=["A"],
            ),
        )
        service_blocks["record"] = not record_ok and IssueCode.NOT_READY in record_issues

        fin = svc.finalize(
            session,
            FinalizeAttemptRequest(
                actor=attack_actor,
                attempt_id="fake",
                idempotency_key="f",
                content_binding_fingerprint="00",
            ),
        )
        service_blocks["finalize"] = (
            fin.committed is False and IssueCode.NOT_READY in fin.issue_codes
        )

        abandon_issues = svc.abandon(session, attack_actor, "fake")
        service_blocks["abandon"] = abandon_issues == [IssueCode.NOT_READY]

        list_rows, list_issues = list_attempts_for_learner(session, attack_actor)
        service_blocks["query_list"] = list_rows == [] and IssueCode.NOT_READY in list_issues

        mastery_rows, mastery_issues = read_mastery_summary(session, attack_actor)
        service_blocks["query_mastery"] = (
            mastery_rows == [] and IssueCode.NOT_READY in mastery_issues
        )

        handoff = build_day16_handoff(session, attack_actor)
        service_blocks["handoff"] = (
            handoff.readiness == "NOT_READY"
            and not handoff.actionable
            and handoff.evidence_event_ids == []
        )

        finalization_blocked = False
        try:
            finalize_attempt(
                session,
                FinalizeAttemptRequest(
                    actor=attack_actor,
                    attempt_id="fake",
                    idempotency_key="f2",
                    content_binding_fingerprint="00",
                ),
            )
        except FinalizationError as exc:
            finalization_blocked = exc.code == IssueCode.NOT_READY

        helper_blocked = apply_mastery_update(
            session,
            organization_id=attack_actor.organization_id,
            institution_id=attack_actor.institution_id,
            learner_id=attack_actor.learner_id,
            concept_code="x",
            event=ScoreEvidenceEvent(
                attempt_id="a",
                organization_id=attack_actor.organization_id,
                learner_id=attack_actor.learner_id,
                item_sequence=1,
                verdict="correct",
                marks_awarded=0,
                max_marks=1,
                snapshot_fingerprint="fp",
            ),
        )
        service_blocks["mastery_helper"] = helper_blocked is None
        service_blocks["finalize_helper"] = finalization_blocked

        post_count = session.scalar(select(func.count()).select_from(Organization))
        service_blocks["no_extra_org_rows"] = post_count == pre_count
        service_blocks["no_learner_evidence_rows"] = _assert_no_learner_rows(session)
        session.rollback()

    containment_ok = (
        CONTAINMENT_ACTIVE
        and production_assessment_always_blocked()
        and not PRODUCTION_ASSESSMENT_ELIGIBILITY
        and not TRUSTED_MASTERY_EVIDENCE
        and not DURABLE_LEARNER_EVIDENCE
        and runtime_eligibility == EligibilityVerdict.BLOCKED_UNVERIFIED
        and structure_valid == EligibilityVerdict.ELIGIBLE
        and forged_structure == EligibilityVerdict.BLOCKED_FORGED_APPROVAL
        and unattested_structure == EligibilityVerdict.BLOCKED_UNVERIFIED
        and pure_partial["total_marks"] == "4"
        and pure_partial["max_marks"] == "8"
        and pure_partial["persisted"] == "false"
        and pure_full["persisted"] == "false"
        and all(service_blocks.values())
        and scope_counts.get("TOTAL") == 36
    )

    report: dict[str, object] = {
        "ok": containment_ok,
        "containment_milestone": "D15-MECHANICAL-CONTAINMENT-SEAL-01",
        "synthetic_harness_pass": False,
        "diagnostic_execution_ok": containment_ok,
        "diagnostic_only_pure_scoring": True,
        "durable_learner_evidence": False,
        "unimplemented_policies": [
            "mastery_v1_full",
            "day10_diagnostic_integration",
            "d15_runtime_persistence",
        ],
        "production_assessment_eligibility": PRODUCTION_ASSESSMENT_ELIGIBILITY,
        "production_assessment_blocked_unconditional": production_assessment_always_blocked(),
        "containment_active": CONTAINMENT_ACTIVE,
        "service_boundary_checks": service_blocks,
        "pure_diagnostics": {"partial": pure_partial, "full": pure_full},
        "governance": governance,
        "scope_ledger_counts": scope_counts,
        "eligibility": {
            "runtime_blocked": runtime_eligibility.value,
            "pure_structure_valid": structure_valid.value,
            "forged_structure_blocked": forged_structure.value,
            "unattested_structure_blocked": unattested_structure.value,
        },
        "handoff": handoff.model_dump(),
        "notes": {
            "compose_smoke": "NOT_RUN",
            "live_postgresql": "NOT_RUN",
            "full_historical_pytest": "NOT_RUN",
            "migration_0021_blocker": "DEFERRED",
            "d15_36_founder_signoff": "NOT_STARTED",
            "day14_issuance_containment_unchanged": True,
            "runtime_db_persistence": "DISABLED",
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
        "containment_milestone": "D15-MECHANICAL-CONTAINMENT-SEAL-01",
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
        report = _run_containment_verification(revision)
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