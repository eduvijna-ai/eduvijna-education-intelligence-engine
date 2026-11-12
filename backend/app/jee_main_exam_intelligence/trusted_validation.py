from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.common.trust_execution import TrustExecutionMode
from app.jee_main_exam_intelligence.constants import SYNTHETIC_FIXTURE_HARNESS_VERSION

SYNTHETIC_JEE_MAIN_TRUST_TOKEN = "d11-internal-jee-main-harness-v1"


class JeeMainQuestionTrustContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trust_source: Literal["synthetic_fixture_harness"]
    harness_token: str = Field(repr=False)
    harness_version: str = SYNTHETIC_FIXTURE_HARNESS_VERSION

    @classmethod
    def synthetic_fixture_harness(cls) -> JeeMainQuestionTrustContext:
        return cls(
            trust_source="synthetic_fixture_harness",
            harness_token=SYNTHETIC_JEE_MAIN_TRUST_TOKEN,
        )


def synthetic_trust_permitted(execution_mode: TrustExecutionMode) -> bool:
    return execution_mode == TrustExecutionMode.SYNTHETIC_FIXTURE
