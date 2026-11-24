from __future__ import annotations

from pydantic import BaseModel, Field

from app.ca_imat_eapcet.enums import PlanVerdict


class HistoricalEvidenceRecord(BaseModel):
    """D14-27: statistical prior-paper evidence separated from official hard rules."""

    exam_family: str
    source_version: str
    denominator: int
    sample_size: int
    confidence: float
    rights_status: str
    provenance_locator: str
    official_rule: bool = False
    metadata_json: dict[str, object] = Field(default_factory=dict)


def evaluate_historical_vs_official(record: HistoricalEvidenceRecord) -> PlanVerdict:
    if record.official_rule:
        return PlanVerdict.REVIEW_REQUIRED
    if record.rights_status == "SOURCE_PENDING":
        return PlanVerdict.SOURCE_PENDING
    if record.sample_size < 1 or record.denominator < 1:
        return PlanVerdict.FAIL
    return PlanVerdict.PASS