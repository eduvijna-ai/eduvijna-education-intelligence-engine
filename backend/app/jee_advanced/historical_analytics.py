from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class HistoricalAnalyticsStatus(StrEnum):
    NOT_ANALYZABLE = "not_analyzable"
    OBSERVED = "observed"


@dataclass(frozen=True, slots=True)
class HistoricalFrequencyReport:
    status: HistoricalAnalyticsStatus
    numerator: int
    denominator: int
    sampled_years: tuple[int, ...]
    sampled_papers: tuple[str, ...]
    uncertainty_note: str


def topic_frequency_without_item_evidence() -> HistoricalFrequencyReport:
    """D12-15: fail closed when item-level originals are unavailable."""

    return HistoricalFrequencyReport(
        status=HistoricalAnalyticsStatus.NOT_ANALYZABLE,
        numerator=0,
        denominator=0,
        sampled_years=(),
        sampled_papers=(),
        uncertainty_note="Item-level evidence required; metadata-only discovery is insufficient.",
    )
