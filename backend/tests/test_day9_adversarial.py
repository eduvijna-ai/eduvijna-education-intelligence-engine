from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates
from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
)
from app.diagnostic_intelligence.fixtures import (
    build_fixture_mcq_item,
    build_fixture_result,
    build_fixture_tags,
)
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _authoring(item_id: str = "adv-1") -> DiagnosticAuthoringRequest:
    item = build_fixture_mcq_item(item_id=item_id)
    return DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=item.source_revision_ids,
        allowed_evidence_refs=["[CIT-1]"],
    )


def _codes(request: DiagnosticAuthoringRequest) -> set[str]:
    return {c.misconception_code for c in resolve_misconception_candidates(request)}


def test_adversarial_unknown_misconception_code() -> None:
    service = DiagnosticIntelligenceService()
    request = _authoring()
    tags = build_fixture_tags(request.item)
    tags[0] = tags[0].model_copy(update={"misconception_code": "MATH.HALLUCINATED"})
    verdict = service.validate_result(
        request,
        build_fixture_result(request.item, tags),
        candidate_codes=_codes(request),
    )
    assert verdict.blocking is True
    assert "unknown_misconception_code" in verdict.issue_codes


def test_adversarial_inactive_misconception() -> None:
    service = DiagnosticIntelligenceService()
    request = _authoring("adv-inactive")
    tags = build_fixture_tags(request.item)
    tags[0] = tags[0].model_copy(
        update={"misconception_code": "MATH.ADD.WHOLE.INACTIVE_SAMPLE"}
    )
    codes = _codes(request) | {"MATH.ADD.WHOLE.INACTIVE_SAMPLE"}
    verdict = service.validate_result(
        request,
        build_fixture_result(request.item, tags),
        candidate_codes=codes,
    )
    assert "inactive_misconception" in verdict.issue_codes


def test_adversarial_forged_evidence_ref() -> None:
    service = DiagnosticIntelligenceService()
    request = _authoring("adv-2")
    tags = build_fixture_tags(request.item)
    tags[0] = tags[0].model_copy(update={"evidence_refs": ["FORGED-REF"]})
    verdict = service.validate_result(
        request,
        build_fixture_result(request.item, tags),
        candidate_codes=_codes(request),
    )
    assert "forged_evidence_ref" in verdict.issue_codes


def test_adversarial_duplicate_misconception_tags() -> None:
    service = DiagnosticIntelligenceService()
    request = _authoring("adv-dup")
    tags = build_fixture_tags(request.item)
    tags[2] = tags[2].model_copy(
        update={
            "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            "diagnostic_signal": "off-by-one-low",
        }
    )
    tags[2].metadata_json["option_text"] = "11 off-by-one-low"
    verdict = service.validate_result(
        request,
        build_fixture_result(request.item, tags),
        candidate_codes=_codes(request),
    )
    assert "duplicate_misconception" in verdict.issue_codes


def test_orchestration_rejects_unknown_diagnostic_code() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    result = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_unknown_code",
            idempotency_key="day9-adv-unknown",
        )
    )
    assert result.status == OrchestrationRunStatus.FAILED
    session.close()


def test_orchestration_rejects_inactive_and_correct_mislabeled() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    inactive = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_inactive",
            idempotency_key="day9-adv-inactive",
        )
    )
    mislabeled = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_correct_mislabeled",
            idempotency_key="day9-adv-mislabel",
        )
    )
    assert inactive.status == OrchestrationRunStatus.FAILED
    assert mislabeled.status == OrchestrationRunStatus.FAILED
    session.close()


def test_orchestration_gateway_timeout_401_5xx() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    timeout = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            scenario="gateway_timeout",
            idempotency_key="day9-adv-timeout",
        )
    )
    unauthorized = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            scenario="gateway_401",
            idempotency_key="day9-adv-401",
        )
    )
    unavailable = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            scenario="gateway_5xx",
            idempotency_key="day9-adv-5xx",
        )
    )
    assert timeout.status == OrchestrationRunStatus.RETRY_REQUIRED
    assert unauthorized.status == OrchestrationRunStatus.FAILED
    assert unavailable.status == OrchestrationRunStatus.RETRY_REQUIRED
    session.close()


def test_adversarial_scope_mismatches_on_full_tags() -> None:
    service = DiagnosticIntelligenceService()
    request = _authoring("adv-scope")
    tags = build_fixture_tags(request.item)
    tags[0] = tags[0].model_copy(
        update={"misconception_code": "MATH.ADD.ALGEBRA_TOPIC_ONLY", "diagnostic_signal": "algebra"}
    )
    verdict = service.validate_result(
        request,
        build_fixture_result(request.item, tags),
        candidate_codes=_codes(request) | {"MATH.ADD.ALGEBRA_TOPIC_ONLY"},
    )
    assert "curriculum_scope_mismatch" in verdict.issue_codes

    wrong_grade = request.model_copy(update={"grade_year_code": "grade-10"})
    verdict_grade = service.validate_result(
        wrong_grade,
        build_fixture_result(request.item, build_fixture_tags(request.item)),
        candidate_codes=_codes(wrong_grade),
    )
    assert verdict_grade.issue_codes

    wrong_subject = request.model_copy(update={"subject_code": "physics"})
    tags_subject = build_fixture_tags(request.item)
    tags_subject[0] = tags_subject[0].model_copy(
        update={"misconception_code": "SCI.PHYS.FORCE.WRONG_SUBJECT"}
    )
    verdict_subject = service.validate_result(
        wrong_subject,
        build_fixture_result(request.item, tags_subject),
        candidate_codes=_codes(wrong_subject) | {"SCI.PHYS.FORCE.WRONG_SUBJECT"},
    )
    assert "curriculum_scope_mismatch" in verdict_subject.issue_codes


def test_adversarial_second_correct_distractor() -> None:
    service = DiagnosticIntelligenceService()
    request = _authoring("adv-second-correct")
    tags = build_fixture_tags(request.item)
    tags[0] = tags[0].model_copy(
        update={"misconception_code": "MATH.ADD.WHOLE.SUM_AS_NEXT", "diagnostic_signal": "12"}
    )
    verdict = service.validate_result(
        request,
        build_fixture_result(request.item, tags),
        candidate_codes=_codes(request),
    )
    assert (
        "second_correct_distractor" in verdict.issue_codes
        or "signal_text_mismatch" in verdict.issue_codes
    )


def test_orchestration_tenant_foreign_revisions_rejected() -> None:
    from app.orchestration.day9_tenant_fixtures import seed_day9_foreign_tenant_revisions

    session = _session()
    ctx, service = build_day8_test_service(session)
    foreign = seed_day9_foreign_tenant_revisions(session, ctx)

    def _run(revision_id: str, key: str) -> list[str]:
        result = service.run(
            build_diagnostic_orchestration_request(
                ctx,
                diagnostic_scenario="diagnostic_foreign_revision",
                diagnostic_foreign_revision_id=revision_id,
                idempotency_key=key,
            )
        )
        codes: list[str] = []
        for entry in result.metadata_json.get("diagnostic_results") or []:
            for tag in entry.get("option_tags") or []:
                codes.extend(tag.get("issue_codes") or [])
        return codes

    org_codes = _run(foreign.foreign_organization_revision_id, "day9-adv-tenant-org")
    inst_codes = _run(foreign.foreign_institution_revision_id, "day9-adv-tenant-inst")
    teacher_codes = _run(foreign.foreign_teacher_revision_id, "day9-adv-tenant-teacher")
    assert "tenant_evidence_mismatch" in org_codes
    assert "tenant_evidence_mismatch" in inst_codes
    assert "tenant_evidence_mismatch" in teacher_codes
    session.close()


def test_orchestration_injection_and_second_correct() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    injection = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            scenario="injection_evidence",
            idempotency_key="day9-adv-injection",
        )
    )
    second = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_second_correct",
            idempotency_key="day9-adv-second-correct",
            max_repairs=0,
        )
    )
    injection_rev = ctx["injection_revision_id"]
    if injection.status == OrchestrationRunStatus.COMPLETED:
        assert all(item.marks == 1.0 for item in injection.items)
        for item in injection.items:
            assert injection_rev in item.source_revision_ids
            assert "ignore previous instructions" not in item.stem_text.lower()
    else:
        payload = injection.metadata_json.get("interrupt_payload") or {}
        deterministic = payload.get("deterministic_validation") or []
        assert any(
            "injection_evidence_control" in (d.get("issue_codes") or []) for d in deterministic
        )
    assert second.status in {
        OrchestrationRunStatus.FAILED,
        OrchestrationRunStatus.REVIEW_REQUIRED,
    }
    session.close()

