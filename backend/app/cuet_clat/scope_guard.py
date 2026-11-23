from __future__ import annotations

from app.cuet_clat.constants import CLAT_PACK_CODE, CUET_PACK_CODE, MATHEMATICS_DOMAIN
from app.cuet_clat.enums import IssueCode

_SUPPORTED_CUET_MEDIUMS = frozenset({"english", "hindi"})


def validate_cuet_pack(exam_pack_code: str) -> list[IssueCode]:
    if exam_pack_code != CUET_PACK_CODE:
        return [IssueCode.WRONG_EXAM_PACK]
    return []


def validate_clat_pack(exam_pack_code: str) -> list[IssueCode]:
    if exam_pack_code != CLAT_PACK_CODE:
        return [IssueCode.WRONG_EXAM_PACK]
    return []


def validate_cuet_subject(test_subject_code: str) -> list[IssueCode]:
    if not test_subject_code or test_subject_code.startswith("jee_"):
        return [IssueCode.JEE_MAIN_FALLBACK, IssueCode.WRONG_SUBJECT]
    return []


def validate_cuet_medium(medium_code: str) -> list[IssueCode]:
    if medium_code not in _SUPPORTED_CUET_MEDIUMS:
        return [IssueCode.WRONG_MEDIUM]
    return []


def validate_cuet_math_practice(test_subject_code: str) -> list[IssueCode]:
    if test_subject_code != MATHEMATICS_DOMAIN:
        return [IssueCode.WRONG_SUBJECT]
    return []


def validate_tenant(organization_id: str | None, *, required: bool = False) -> list[IssueCode]:
    if required and not organization_id:
        return [IssueCode.TENANT_ISOLATION]
    return []