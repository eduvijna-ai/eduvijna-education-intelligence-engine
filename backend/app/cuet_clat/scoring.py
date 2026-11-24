from __future__ import annotations

from app.cuet_clat.constants import (
    CLAT_MARK_BLANK,
    CLAT_MARK_CORRECT,
    CLAT_MARK_INCORRECT,
    CUET_MARK_CORRECT,
    CUET_MARK_INCORRECT,
)


def score_cuet_response(*, selected_key: str | None, correct_key: str) -> float:
    if not selected_key:
        return 0.0
    if selected_key == correct_key:
        return CUET_MARK_CORRECT
    return CUET_MARK_INCORRECT


def score_clat_response(*, selected_key: str | None, correct_key: str) -> float:
    if not selected_key:
        return CLAT_MARK_BLANK
    if selected_key == correct_key:
        return CLAT_MARK_CORRECT
    return CLAT_MARK_INCORRECT