from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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
        default="validated_persisted_synthetic",
        description="Explicit opt-in gate for persisted selection mode",
    )