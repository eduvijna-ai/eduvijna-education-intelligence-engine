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


class HistoricalPaperDiscovery(BaseModel):
    """Link-only NTA publication metadata, not approved question-level evidence."""

    year: int
    session: str
    examination_date: str
    shift: str
    source_url: str
    subject_codes: list[str]
    status: str = "official_portal_link_discovered_pdf_not_curator_approved"
    rights_status: str = "official_public_link_only_no_question_redistribution"


# NTA's official JEE Main portal links to these nine April 2026 Paper-1 shifts.
# Discovery is not source ingestion: SHA-256, original PDF review, answer-key
# matching and topic adjudication must be completed before counting frequencies.
# Link source: https://jeemain.nta.nic.in/ (Question Papers menu, 2026-11-12).
OFFICIAL_2026_PAPER_DISCOVERY: list[HistoricalPaperDiscovery] = [
    HistoricalPaperDiscovery(
        year=2026,
        session="session-2",
        examination_date=day,
        shift=shift,
        source_url=url,
        subject_codes=["mathematics", "physics", "chemistry"],
    )
    for day, shift, url in [
        ("2026-04-02", "shift-1", "https://cdnbbsr.s3waas.gov.in/s3f8e59f4b2fe7c5705bf878bbd494ccdf/uploads/2026/04/202604092096865379.pdf"),
        ("2026-04-02", "shift-2", "https://cdnbbsr.s3waas.gov.in/s3f8e59f4b2fe7c5705bf878bbd494ccdf/uploads/2026/04/20260409481957146.pdf"),
        ("2026-04-04", "shift-1", "https://cdnbbsr.s3waas.gov.in/s3f8e59f4b2fe7c5705bf878bbd494ccdf/uploads/2026/04/202604091916616339.pdf"),
        ("2026-04-04", "shift-2", "https://cdnbbsr.s3waas.gov.in/s3f8e59f4b2fe7c5705bf878bbd494ccdf/uploads/2026/04/20260409432593766.pdf"),
        ("2026-04-05", "shift-1", "https://cdnbbsr.s3waas.gov.in/s3f8e59f4b2fe7c5705bf878bbd494ccdf/uploads/2026/04/20260409828731207.pdf"),
        ("2026-04-05", "shift-2", "https://cdnbbsr.s3waas.gov.in/s3f8e59f4b2fe7c5705bf878bbd494ccdf/uploads/2026/04/20260409829414602.pdf"),
        ("2026-04-06", "shift-1", "https://cdnbbsr.s3waas.gov.in/s3f8e59f4b2fe7c5705bf878bbd494ccdf/uploads/2026/04/202604092007095665.pdf"),
        ("2026-04-06", "shift-2", "https://cdnbbsr.s3waas.gov.in/s3f8e59f4b2fe7c5705bf878bbd494ccdf/uploads/2026/04/20260409725707538.pdf"),
        ("2026-04-08", "shift-2", "https://cdnbbsr.s3waas.gov.in/s3f8e59f4b2fe7c5705bf878bbd494ccdf/uploads/2026/04/20260409932754345.pdf"),
    ]
]


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
        "official_2026_discovered_link_count": len(OFFICIAL_2026_PAPER_DISCOVERY),
        "official_2026_discovered_links": [
            item.model_dump(mode="json") for item in OFFICIAL_2026_PAPER_DISCOVERY
        ],
        "original_pdf_source_revisions_approved": 0,
        "historical_topic_frequencies_verified": False,
        "mandatory_nta_quotas_invented": False,
    }
