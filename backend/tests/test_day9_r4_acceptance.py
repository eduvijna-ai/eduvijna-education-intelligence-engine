from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DiagnosticQuestionItem,
    DiagnosticQuestionOption,
    DistractorDiagnosticResult,
    OptionDiagnosticTag,
)
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION
from app.diagnostic_intelligence.fixtures import build_fixture_mcq_item, build_fixture_tags
from app.diagnostic_intelligence.integration.revision_tenancy import load_revision_tenant_records
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.diagnostic_intelligence.validators.signal import validate_signal_alignment
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
    build_orchestration_request,
)
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.human_decision import HumanResumeDecision


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_redundant_distractor_uses_canonical_text_without_metadata() -> None:
    service = DiagnosticIntelligenceService()
    item = DiagnosticQuestionItem(
        item_id="redundant-1",
        stem_text="Synthetic fixture: What is 7 + 5?",
        question_type="single_choice",
        options=[
            DiagnosticQuestionOption(option_key="A", text="same wrong", is_correct=False),
            DiagnosticQuestionOption(option_key="B", text="12", is_correct=True),
            DiagnosticQuestionOption(option_key="C", text="same wrong", is_correct=False),
        ],
        source_revision_ids=["00000000-0000-0000-0000-000000000001"],
    )
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        competency_codes=["application"],
        learning_outcome_ids=["lo-fixture-1"],
        allowed_evidence_refs=["[CIT-1]"],
        allowed_source_revision_ids=item.source_revision_ids,
    )
    tags = [
        OptionDiagnosticTag(
            item_id=item.item_id,
            option_key="A",
            is_correct=False,
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            metadata_json={},
        ),
        OptionDiagnosticTag(
            item_id=item.item_id,
            option_key="B",
            is_correct=True,
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            metadata_json={},
        ),
        OptionDiagnosticTag(
            item_id=item.item_id,
            option_key="C",
            is_correct=False,
            misconception_code="MATH.ADD.WHOLE.SUM_AS_NEXT",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            metadata_json={},
        ),
    ]
    from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates

    codes = {c.misconception_code for c in resolve_misconception_candidates(request)}
    verdict = service.validate_result(
        request,
        DistractorDiagnosticResult(
            item_id=item.item_id,
            question_type=item.question_type,
            option_tags=tags,
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            source_revision_ids=item.source_revision_ids,
        ),
        candidate_codes=codes,
    )
    assert "redundant_distractor" in verdict.issue_codes
    assert verdict.status.value != "pass"


def test_result_integrity_taxonomy_and_provenance_mismatches() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id="prov-1")
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        competency_codes=["application"],
        learning_outcome_ids=["lo-fixture-1"],
        allowed_evidence_refs=["[CIT-1]"],
        allowed_source_revision_ids=item.source_revision_ids,
    )
    tags = build_fixture_tags(item)
    codes = {"MATH.ADD.WHOLE.OFF_BY_ONE_LOW", "MATH.ADD.WHOLE.SUM_AS_NEXT"}

    bad_tag_item = tags[0].model_copy(update={"item_id": "other-item"})
    verdict_tag = service.validate_result(
        request,
        DistractorDiagnosticResult(
            item_id=item.item_id,
            question_type=item.question_type,
            option_tags=[bad_tag_item, tags[1], tags[2]],
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            source_revision_ids=item.source_revision_ids,
        ),
        candidate_codes=codes,
    )
    assert "tag_item_id_mismatch" in verdict_tag.issue_codes

    verdict_tax = service.validate_result(
        request,
        DistractorDiagnosticResult(
            item_id=item.item_id,
            question_type=item.question_type,
            option_tags=tags,
            taxonomy_version="fake-version",
            source_revision_ids=item.source_revision_ids,
        ),
        candidate_codes=codes,
    )
    assert "result_taxonomy_version_mismatch" in verdict_tax.issue_codes

    verdict_src = service.validate_result(
        request,
        DistractorDiagnosticResult(
            item_id=item.item_id,
            question_type=item.question_type,
            option_tags=tags,
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            source_revision_ids=["FOREIGN-REVISION"],
        ),
        candidate_codes=codes,
    )
    assert "result_source_revision_mismatch" in verdict_src.issue_codes


def test_sum_as_next_signal_operand_numbers_do_not_match() -> None:
    stem = "Synthetic fixture: What is 7 + 5?"
    for option_text in ("7", "5", "17"):
        issues = validate_signal_alignment(
            OptionDiagnosticTag(
                item_id="x",
                option_key="A",
                is_correct=False,
                misconception_code="MATH.ADD.WHOLE.SUM_AS_NEXT",
                taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            ),
            option_text,
            stem_text=stem,
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        )
        assert "signal_text_mismatch" in issues
    assert not validate_signal_alignment(
        OptionDiagnosticTag(
            item_id="x",
            option_key="A",
            is_correct=False,
            misconception_code="MATH.ADD.WHOLE.SUM_AS_NEXT",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        ),
        "13 successor",
        stem_text=stem,
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
    )


def test_tenant_isolation_without_blocked_metadata_list() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    from app.orchestration.day9_tenant_fixtures import seed_day9_foreign_tenant_revisions

    foreign = seed_day9_foreign_tenant_revisions(session, ctx)
    records = load_revision_tenant_records(
        session,
        [
            foreign.foreign_organization_revision_id,
            foreign.foreign_institution_revision_id,
            foreign.foreign_teacher_revision_id,
            ctx["official_revision_id"],
        ],
    )

    def _assert_tenant_fail(revision_id: str, key: str) -> None:
        result = service.run(
            build_diagnostic_orchestration_request(
                ctx,
                diagnostic_scenario="diagnostic_foreign_revision",
                diagnostic_foreign_revision_id=revision_id,
                idempotency_key=key,
            )
        )
        issue_codes: list[str] = []
        for entry in result.metadata_json.get("diagnostic_results") or []:
            for tag in entry.get("option_tags") or []:
                issue_codes.extend(tag.get("issue_codes") or [])
        assert "tenant_evidence_mismatch" in issue_codes

    _assert_tenant_fail(foreign.foreign_organization_revision_id, "day9-r4-tenant-org")
    _assert_tenant_fail(foreign.foreign_institution_revision_id, "day9-r4-tenant-inst")
    _assert_tenant_fail(foreign.foreign_teacher_revision_id, "day9-r4-tenant-teacher")

    allowed_item = build_fixture_mcq_item().model_copy(
        update={"source_revision_ids": [ctx["official_revision_id"]]}
    )
    allowed_request = DiagnosticAuthoringRequest(
        item=allowed_item,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[ctx["official_revision_id"]],
        allowed_evidence_refs=["[CIT-1]"],
        revision_tenant_records=records,
    )
    tags = build_fixture_tags(allowed_item)
    diag_service = DiagnosticIntelligenceService()
    from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates

    codes = {c.misconception_code for c in resolve_misconception_candidates(allowed_request)}
    from app.diagnostic_intelligence.fixtures import build_fixture_result

    ok = diag_service.validate_result(
        allowed_request,
        build_fixture_result(allowed_request.item, tags),
        candidate_codes=codes,
    )
    assert ok.status.value == "pass"
    session.close()


def test_diagnostic_review_required_human_approve_completes() -> None:
    session = _session()
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_orchestration_request(
        ctx,
        scenario="non_arithmetic_diagnostic_review",
        idempotency_key="day9-r4-hitl-review",
        max_repairs=0,
    )
    request = request.model_copy(
        update={
            "metadata_json": {
                **request.metadata_json,
                "diagnostic_enrichment_enabled": True,
                "diagnostic_fixture_scenario": "diagnostic_clean_pass",
            },
        }
    )
    paused_deterministic = service.run(request)
    assert paused_deterministic.status == OrchestrationRunStatus.REVIEW_REQUIRED
    after_deterministic = service.run(
        request, resume=HumanResumeDecision(action="approve")
    )
    assert after_deterministic.status == OrchestrationRunStatus.REVIEW_REQUIRED
    payload = after_deterministic.metadata_json.get("interrupt_payload") or {}
    assert payload.get("diagnostic_validation")
    assert payload.get("diagnostic_results")
    assert any(entry.get("review_required") for entry in payload.get("diagnostic_validation") or [])
    completed = service.run(request, resume=HumanResumeDecision(action="approve"))
    assert completed.status == OrchestrationRunStatus.COMPLETED
    assert completed.metadata_json.get("diagnostic_results")
    session.close()


def test_diagnostic_review_required_human_reject_fails() -> None:
    session = _session()
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_orchestration_request(
        ctx,
        scenario="non_arithmetic_diagnostic_review",
        idempotency_key="day9-r4-hitl-review-reject",
        max_repairs=0,
    )
    request = request.model_copy(
        update={
            "metadata_json": {
                **request.metadata_json,
                "diagnostic_enrichment_enabled": True,
                "diagnostic_fixture_scenario": "diagnostic_clean_pass",
            },
        }
    )
    assert service.run(request).status == OrchestrationRunStatus.REVIEW_REQUIRED
    mid = service.run(request, resume=HumanResumeDecision(action="approve"))
    assert mid.status == OrchestrationRunStatus.REVIEW_REQUIRED
    rejected = service.run(request, resume=HumanResumeDecision(action="reject"))
    assert rejected.status == OrchestrationRunStatus.FAILED
    session.close()


def test_diagnostic_hitl_invalid_resume_fails() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    request = build_orchestration_request(
        ctx,
        scenario="non_arithmetic_diagnostic_review",
        idempotency_key="day9-r4-hitl-invalid",
        max_repairs=0,
    )
    request = request.model_copy(
        update={
            "metadata_json": {
                **request.metadata_json,
                "diagnostic_enrichment_enabled": True,
                "diagnostic_fixture_scenario": "diagnostic_clean_pass",
            },
        }
    )
    assert service.run(request).status == OrchestrationRunStatus.REVIEW_REQUIRED
    service.run(request, resume=HumanResumeDecision(action="approve"))
    failed = service.run(request, resume={"action": "not-valid"})
    assert failed.status == OrchestrationRunStatus.FAILED
    assert "invalid_human_resume" in failed.errors
    session.close()


def test_injection_evidence_does_not_change_marks() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    request = build_diagnostic_orchestration_request(
        ctx,
        scenario="injection_evidence",
        idempotency_key="day9-r4-injection",
    )
    result = service.run(request)
    injection_rev = ctx["injection_revision_id"]
    if result.status == OrchestrationRunStatus.COMPLETED:
        assert all(item.marks == 1.0 for item in result.items)
        for item in result.items:
            assert injection_rev in item.source_revision_ids
            assert "ignore previous instructions" not in item.stem_text.lower()
    else:
        assert result.status == OrchestrationRunStatus.REVIEW_REQUIRED
        payload = result.metadata_json.get("interrupt_payload") or {}
        deterministic = payload.get("deterministic_validation") or []
        assert any(
            "injection_evidence_control" in (d.get("issue_codes") or []) for d in deterministic
        )
    session.close()
