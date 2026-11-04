from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
from app.prerequisite_intelligence.contracts import PrerequisiteGraphSnapshot

SYNTHETIC_FIXTURE_TRUST_TOKEN = "d10-internal-synthetic-harness-v1"


class RootCauseTrustedValidationContext(BaseModel):
    """Internal-only proof that Day9 tag validation was accepted for this item/option."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str
    option_key: str
    misconception_code: str
    taxonomy_version: str
    validation_status: DiagnosticValidationStatus
    trust_source: Literal["day9_accepted_verdict", "synthetic_fixture_harness"]
    day9_audit_ref: str | None = None
    validation_run_id: str | None = None
    harness_token: str | None = Field(default=None, repr=False)

    @classmethod
    def from_day9_accepted(
        cls,
        *,
        item_id: str,
        option_key: str,
        misconception_code: str,
        taxonomy_version: str,
        day9_audit_ref: str | None = None,
        validation_run_id: str | None = None,
    ) -> RootCauseTrustedValidationContext:
        return cls(
            item_id=item_id,
            option_key=option_key,
            misconception_code=misconception_code,
            taxonomy_version=taxonomy_version,
            validation_status=DiagnosticValidationStatus.PASS,
            trust_source="day9_accepted_verdict",
            day9_audit_ref=day9_audit_ref,
            validation_run_id=validation_run_id,
        )

    @classmethod
    def synthetic_fixture_harness(
        cls,
        *,
        item_id: str,
        option_key: str,
        misconception_code: str,
        taxonomy_version: str,
    ) -> RootCauseTrustedValidationContext:
        return cls(
            item_id=item_id,
            option_key=option_key,
            misconception_code=misconception_code,
            taxonomy_version=taxonomy_version,
            validation_status=DiagnosticValidationStatus.PASS,
            trust_source="synthetic_fixture_harness",
            harness_token=SYNTHETIC_FIXTURE_TRUST_TOKEN,
        )


def trusted_context_matches_request(
    request_item_id: str,
    request_option_key: str,
    request_misconception: str,
    request_taxonomy: str,
    trusted: RootCauseTrustedValidationContext,
) -> bool:
    return (
        trusted.item_id == request_item_id
        and trusted.option_key == request_option_key
        and trusted.misconception_code == request_misconception
        and trusted.taxonomy_version == request_taxonomy
        and trusted.validation_status == DiagnosticValidationStatus.PASS
    )


def synthetic_harness_allowed(snapshot: PrerequisiteGraphSnapshot) -> bool:
    meta = snapshot.metadata_json or {}
    if meta.get("synthetic_fixture") or meta.get("fixture"):
        return True
    return all(edge.provenance_class.value == "synthetic" for edge in snapshot.edges)
