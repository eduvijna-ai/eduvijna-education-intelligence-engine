from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cuet_clat.constants import CUET_PACK_CODE, VERSION_SYNTHETIC_DEMO
from app.cuet_clat.contracts import (
    CuetPracticeRequest,
    CuetSingleTestRequest,
    resolve_academic_year_string,
    validate_academic_year_explicit,
)
from app.cuet_clat.enums import IssueCode, PlanVerdict
from app.models.examination import ExamPack, ExamVersion

PERSISTED_SELECTION_TOKEN = "validated_persisted_synthetic"


class PersistedCuetSelectionContext(BaseModel):
    """Trusted persisted-selection scope — not caller-spoofable via metadata flags."""

    model_config = ConfigDict(extra="forbid")

    exam_version_id: str
    organization_id: str
    institution_id: str
    medium_code: str = "english"
    academic_year: str = "2026"
    selection_token: str = Field(
        description="Must equal PERSISTED_SELECTION_TOKEN; no implicit default auth",
    )
    harness_authorized: bool = Field(
        default=False,
        description="True only when issued by trusted test/service harness (not public callers)",
    )


def trusted_persisted_context(
    *,
    exam_version_id: str,
    organization_id: str,
    institution_id: str,
    medium_code: str = "english",
    academic_year: str = "2026",
) -> PersistedCuetSelectionContext:
    return PersistedCuetSelectionContext(
        exam_version_id=exam_version_id,
        organization_id=organization_id,
        institution_id=institution_id,
        medium_code=medium_code,
        academic_year=academic_year,
        selection_token=PERSISTED_SELECTION_TOKEN,
        harness_authorized=True,
    )


def assert_trusted_persisted_context(context: PersistedCuetSelectionContext) -> bool:
    return (
        context.selection_token == PERSISTED_SELECTION_TOKEN and context.harness_authorized is True
    )


def resolve_trusted_exam_version(
    session: Session,
    *,
    exam_version_id: str,
) -> tuple[ExamVersion | None, list[IssueCode]]:
    row = session.scalar(select(ExamVersion).where(ExamVersion.id == exam_version_id))
    if row is None:
        return None, [IssueCode.WRONG_EXAM_PACK]
    pack = session.scalar(select(ExamPack).where(ExamPack.id == row.exam_pack_id))
    if pack is None or pack.code != CUET_PACK_CODE:
        return None, [IssueCode.WRONG_EXAM_PACK]
    if row.version_code != VERSION_SYNTHETIC_DEMO:
        return None, [IssueCode.WRONG_YEAR]
    meta = dict(row.metadata_json or {})
    if meta.get("trust_mode") != "synthetic_fixture":
        return None, [IssueCode.UNAPPROVED_SOURCE]
    if row.academic_year != "2026":
        return None, [IssueCode.WRONG_YEAR]
    return row, []


def validate_persisted_practice_alignment(
    request: CuetPracticeRequest,
    *,
    context: PersistedCuetSelectionContext,
    session: Session,
) -> tuple[list[IssueCode], PlanVerdict | None]:
    issues: list[IssueCode] = []
    if not assert_trusted_persisted_context(context):
        return [IssueCode.MISSING_PERSISTED_CONTEXT], PlanVerdict.NOT_READY
    year_issues = validate_academic_year_explicit(request)
    if year_issues:
        return year_issues, PlanVerdict.FAIL
    academic_year = resolve_academic_year_string(request)
    if not request.organization_id or request.organization_id.strip() != context.organization_id:
        issues.append(IssueCode.TENANT_ISOLATION)
    if request.medium_code.strip().lower() != context.medium_code.strip().lower():
        issues.append(IssueCode.WRONG_MEDIUM)
    if academic_year != context.academic_year:
        issues.append(IssueCode.WRONG_YEAR)
    if request.exam_pack_code != CUET_PACK_CODE:
        issues.append(IssueCode.WRONG_EXAM_PACK)
    _, exam_issues = resolve_trusted_exam_version(session, exam_version_id=context.exam_version_id)
    issues.extend(exam_issues)
    if issues:
        return list(dict.fromkeys(issues)), PlanVerdict.FAIL
    return [], None


def validate_persisted_single_test_alignment(
    request: CuetSingleTestRequest,
    *,
    context: PersistedCuetSelectionContext,
    session: Session,
) -> tuple[list[IssueCode], PlanVerdict | None]:
    issues: list[IssueCode] = []
    if not assert_trusted_persisted_context(context):
        return [IssueCode.MISSING_PERSISTED_CONTEXT], PlanVerdict.NOT_READY
    year_issues = validate_academic_year_explicit(request)
    if year_issues:
        return year_issues, PlanVerdict.FAIL
    academic_year = resolve_academic_year_string(request)
    org = request.organization_id
    if not org or str(org).strip() != context.organization_id:
        issues.append(IssueCode.TENANT_ISOLATION)
    if request.medium_code.strip().lower() != context.medium_code.strip().lower():
        issues.append(IssueCode.WRONG_MEDIUM)
    if academic_year != context.academic_year:
        issues.append(IssueCode.WRONG_YEAR)
    if request.exam_pack_code != CUET_PACK_CODE:
        issues.append(IssueCode.WRONG_EXAM_PACK)
    _, exam_issues = resolve_trusted_exam_version(session, exam_version_id=context.exam_version_id)
    issues.extend(exam_issues)
    if issues:
        return list(dict.fromkeys(issues)), PlanVerdict.FAIL
    return [], None