from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HistoricalPaperProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int
    session: str
    shift: str | None = None
    subject_code: str
    question_number: int | None = None
    source_authority: str
    answer_key_ref: str | None = None
    sample_denominator: int | None = None
    rights_status: str
    evidence_quality: str
    topic_code: str | None = None
    question_type: str | None = None
    marks: float | None = None


class HistoricalFrequencyPrior(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_code: str
    topic_code: str
    observed_count: int
    sample_denominator: int
    years_sampled: list[int] = Field(default_factory=list)
    shifts_sampled: list[str] = Field(default_factory=list)
    is_mandatory_nta_quota: bool = False
    uncertainty_note: str
    source_refs: list[str] = Field(default_factory=list)


# Lawful metadata-only inventory (no copyrighted paper text in Git).
SYNTHETIC_HISTORICAL_INVENTORY: list[HistoricalPaperProvenance] = [
    HistoricalPaperProvenance(
        year=2026,
        session="session-1",
        shift="shift-1",
        subject_code="mathematics",
        source_authority="NTA official response sheet metadata (fixture)",
        rights_status="metadata_only_not_redistributed",
        evidence_quality="official_primary_metadata",
        sample_denominator=25,
    ),
]

SYNTHETIC_FREQUENCY_PRIORS: list[HistoricalFrequencyPrior] = [
    HistoricalFrequencyPrior(
        subject_code="mathematics",
        topic_code="complex-numbers-quadratic",
        observed_count=4,
        sample_denominator=20,
        years_sampled=[2024, 2025, 2026],
        shifts_sampled=["shift-1", "shift-2"],
        is_mandatory_nta_quota=False,
        uncertainty_note="Soft statistical prior; not an official NTA chapter quota.",
        source_refs=["synthetic-historical@v1"],
    ),
]


def build_historical_analytics_report() -> dict[str, Any]:
    return {
        "inventory_count": len(SYNTHETIC_HISTORICAL_INVENTORY),
        "frequency_priors": [p.model_dump() for p in SYNTHETIC_FREQUENCY_PRIORS],
        "mandatory_nta_quotas_invented": False,
    }
