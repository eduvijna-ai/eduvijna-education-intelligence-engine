from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SYNTHETIC_PAPER_TRUST_TOKEN = "d10-internal-paper-harness-v1"


class PaperDay6ItemBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str
    validation_run_id: str


class PaperDay6TrustContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trust_source: Literal[
        "validation_run", "per_item_bindings", "synthetic_fixture_harness"
    ]
    validation_run_id: str | None = None
    item_bindings: tuple[PaperDay6ItemBinding, ...] = ()
    harness_token: str | None = Field(default=None, repr=False)

    @classmethod
    def from_validation_run(cls, validation_run_id: str) -> PaperDay6TrustContext:
        return cls(
            trust_source="validation_run",
            validation_run_id=validation_run_id,
        )

    @classmethod
    def from_item_bindings(
        cls, bindings: list[PaperDay6ItemBinding]
    ) -> PaperDay6TrustContext:
        return cls(
            trust_source="per_item_bindings",
            item_bindings=tuple(bindings),
        )

    def binding_for(self, item_id: str) -> PaperDay6ItemBinding | None:
        for binding in self.item_bindings:
            if binding.item_id == item_id:
                return binding
        return None

    def day6_audit_identity_digest(self) -> str:
        if self.trust_source == "per_item_bindings":
            pairs = sorted(
                (binding.item_id, binding.validation_run_id)
                for binding in self.item_bindings
            )
            return "|".join(f"{item}:{run}" for item, run in pairs)
        return self.validation_run_id or ""

    @classmethod
    def synthetic_fixture_harness(cls) -> PaperDay6TrustContext:
        return cls(
            trust_source="synthetic_fixture_harness",
            harness_token=SYNTHETIC_PAPER_TRUST_TOKEN,
        )
