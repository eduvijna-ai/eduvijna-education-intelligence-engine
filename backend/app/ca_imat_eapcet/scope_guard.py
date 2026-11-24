from __future__ import annotations

from app.ca_imat_eapcet.constants import (
    CA_FOUNDATION_PACK_CODE,
    CA_PAPER_CODES,
    EAPCET_PACK_CODE,
    IMAT_PACK_CODE,
)
from app.ca_imat_eapcet.enums import IssueCode


def validate_ca_pack(exam_pack_code: str) -> list[IssueCode]:
    if exam_pack_code != CA_FOUNDATION_PACK_CODE:
        return [IssueCode.WRONG_EXAM_PACK]
    return []


def validate_imat_pack(exam_pack_code: str) -> list[IssueCode]:
    if exam_pack_code != IMAT_PACK_CODE:
        return [IssueCode.WRONG_EXAM_PACK]
    return []


def validate_eapcet_pack(exam_pack_code: str) -> list[IssueCode]:
    if exam_pack_code != EAPCET_PACK_CODE:
        return [IssueCode.WRONG_EXAM_PACK]
    return []


def validate_ca_paper(paper_code: str) -> list[IssueCode]:
    if paper_code not in CA_PAPER_CODES:
        return [IssueCode.WRONG_PAPER]
    return []


def validate_tenant(
    *,
    organization_id: str | None,
    expected_org: str | None,
) -> list[IssueCode]:
    if expected_org and organization_id and organization_id != expected_org:
        return [IssueCode.TENANT_ISOLATION]
    return []