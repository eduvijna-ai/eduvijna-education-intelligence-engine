"""D17-02 server-owned capability readiness registry — deny by default."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.adaptive_remediation.containment import (
    PRODUCTION_REMEDIATION_DISABLED,
    SYNTHETIC_DIAGNOSTIC_ONLY,
)
from app.ca_imat_eapcet.containment import ACADEMIC_VALIDATION_DISABLED, ISSUANCE_DISABLED
from app.platform.errors import CapabilityNotReadyError

_UNTRUSTED_AUTHORITY_KEYS = frozenset(
    {
        "ready",
        "readiness",
        "approved",
        "force_ready",
        "bypass",
        "synthetic_success",
        "caller_ready",
        "environment_ready",
        "skip_validation",
        "official",
        "verified",
    }
)


class CapabilityDisposition(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"
    NOT_READY = "not_ready"
    DIAGNOSTIC_ONLY = "diagnostic_only"
    SOURCE_PENDING = "source_pending"


@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    code: str
    disposition: CapabilityDisposition
    reason: str
    scopes: frozenset[str]


def reject_untrusted_authority_fields(payload: dict[str, Any]) -> None:
    for key in payload:
        normalized = key.strip().lower()
        if normalized in _UNTRUSTED_AUTHORITY_KEYS:
            raise ValueError(f"Untrusted authority field rejected: {key}")


_REGISTRY: dict[str, CapabilityRecord] = {
    "capabilities.list": CapabilityRecord(
        code="capabilities.list",
        disposition=CapabilityDisposition.READY,
        reason="Catalogue is always readable to authenticated principals.",
        scopes=frozenset({"capabilities:read"}),
    ),
    "curriculum.read": CapabilityRecord(
        code="curriculum.read",
        disposition=CapabilityDisposition.READY,
        reason="Versioned curriculum metadata reads are authorized when tenant scope matches.",
        scopes=frozenset({"curriculum:read"}),
    ),
    "exam.read": CapabilityRecord(
        code="exam.read",
        disposition=CapabilityDisposition.READY,
        reason="Exam metadata reads are authorized when tenant scope matches.",
        scopes=frozenset({"exam:read"}),
    ),
    "knowledge.search": CapabilityRecord(
        code="knowledge.search",
        disposition=CapabilityDisposition.NOT_READY,
        reason="Verified Day3/7 tenant corpus binding not evidenced in this candidate.",
        scopes=frozenset({"knowledge:read"}),
    ),
    "questions.generate": CapabilityRecord(
        code="questions.generate",
        disposition=CapabilityDisposition.NOT_READY,
        reason=(
            "Generation jobs require accepted orchestration readiness; fail closed until verified."
        ),
        scopes=frozenset({"generation:submit"}),
    ),
    "questions.validate": CapabilityRecord(
        code="questions.validate",
        disposition=CapabilityDisposition.NOT_READY,
        reason="Day6 authorized validation evidence not available at this boundary.",
        scopes=frozenset({"generation:validate"}),
    ),
    "tests.generate": CapabilityRecord(
        code="tests.generate",
        disposition=CapabilityDisposition.BLOCKED
        if ISSUANCE_DISABLED
        else CapabilityDisposition.NOT_READY,
        reason="Mock examination issuance blocked while Day14 containment is active.",
        scopes=frozenset({"generation:submit"}),
    ),
    "jobs.read": CapabilityRecord(
        code="jobs.read",
        disposition=CapabilityDisposition.READY,
        reason="Tenant-scoped job status reads are supported.",
        scopes=frozenset({"jobs:read"}),
    ),
    "jobs.submit": CapabilityRecord(
        code="jobs.submit",
        disposition=CapabilityDisposition.NOT_READY,
        reason="Async submission permitted only when upstream capability is ready.",
        scopes=frozenset({"jobs:submit"}),
    ),
    "learners.read": CapabilityRecord(
        code="learners.read",
        disposition=CapabilityDisposition.BLOCKED,
        reason="Day15 learner intelligence PR #57 ON_HOLD — no trusted learner reads.",
        scopes=frozenset({"learner:read"}),
    ),
    "learners.attempt": CapabilityRecord(
        code="learners.attempt",
        disposition=CapabilityDisposition.BLOCKED,
        reason="Day15 ON_HOLD blocks attempt ingestion and learner lookups.",
        scopes=frozenset({"learner:write"}),
    ),
    "remediation.recommend": CapabilityRecord(
        code="remediation.recommend",
        disposition=CapabilityDisposition.BLOCKED,
        reason="Day16 runtime learner remediation is unconditionally disabled.",
        scopes=frozenset({"diagnostic:read"}),
    ),
    "admin.sources": CapabilityRecord(
        code="admin.sources",
        disposition=CapabilityDisposition.SOURCE_PENDING,
        reason="Source registry admin without live intake activation (Day12 #35).",
        scopes=frozenset({"admin:sources"}),
    ),
    "mcp.tools": CapabilityRecord(
        code="mcp.tools",
        disposition=CapabilityDisposition.READY,
        reason="MCP tool discovery mirrors REST readiness; no synthetic override.",
        scopes=frozenset({"mcp:invoke"}),
    ),
}


def get_capability(code: str) -> CapabilityRecord | None:
    return _REGISTRY.get(code)


def list_capabilities() -> list[CapabilityRecord]:
    return sorted(_REGISTRY.values(), key=lambda item: item.code)


def assert_capability_ready(code: str) -> CapabilityRecord:
    record = get_capability(code)
    if record is None:
        msg = f"Unknown capability '{code}'"
        raise CapabilityNotReadyError(capability=code, reason=msg)
    if record.disposition not in {CapabilityDisposition.READY}:
        raise CapabilityNotReadyError(capability=code, reason=record.reason)
    return record


def assert_capability_operable(code: str) -> CapabilityRecord:
    """Allow READY and DIAGNOSTIC_ONLY capabilities (no BLOCKED/NOT_READY/SOURCE side effects)."""
    record = get_capability(code)
    if record is None:
        raise CapabilityNotReadyError(capability=code, reason=f"Unknown capability '{code}'")
    if record.disposition in {
        CapabilityDisposition.BLOCKED,
        CapabilityDisposition.NOT_READY,
        CapabilityDisposition.SOURCE_PENDING,
    }:
        raise CapabilityNotReadyError(capability=code, reason=record.reason)
    return record


def containment_snapshot() -> dict[str, bool]:
    return {
        "day14_academic_validation_disabled": ACADEMIC_VALIDATION_DISABLED,
        "day14_issuance_disabled": ISSUANCE_DISABLED,
        "day16_production_remediation_disabled": PRODUCTION_REMEDIATION_DISABLED,
        "day16_synthetic_diagnostic_only": SYNTHETIC_DIAGNOSTIC_ONLY,
        "day15_learner_hold": True,
        "day12_live_source_intake_disabled": True,
    }
