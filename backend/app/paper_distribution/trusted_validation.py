from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SYNTHETIC_PAPER_TRUST_TOKEN = "d10-internal-paper-harness-v1"


class PaperDay6TrustContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trust_source: Literal["validation_run", "synthetic_fixture_harness"]
    validation_run_id: str | None = None
    harness_token: str | None = Field(default=None, repr=False)

    @classmethod
    def from_validation_run(cls, validation_run_id: str) -> PaperDay6TrustContext:
        return cls(
            trust_source="validation_run",
            validation_run_id=validation_run_id,
        )

    @classmethod
    def synthetic_fixture_harness(cls) -> PaperDay6TrustContext:
        return cls(
            trust_source="synthetic_fixture_harness",
            harness_token=SYNTHETIC_PAPER_TRUST_TOKEN,
        )
