"""D17-32 MCP tools — same guards as REST."""

from __future__ import annotations

from typing import Any

from app.platform.auth.principal import RequestPrincipal
from app.platform.capability_registry import (
    CapabilityDisposition,
    containment_snapshot,
    get_capability,
    list_capabilities,
)
from app.platform.errors import AuthenticationError, CapabilityNotReadyError
from app.platform.services.blocked import block_learner_capability, block_remediation_capability


def mcp_get_capabilities() -> dict[str, Any]:
    return {
        "capabilities": [
            {
                "code": item.code,
                "disposition": item.disposition.value,
                "reason": item.reason,
                "scopes": sorted(item.scopes),
            }
            for item in list_capabilities()
        ],
        "containment": containment_snapshot(),
    }


FORBIDDEN_ARGUMENT_KEYS = frozenset(
    {
        "organization_id",
        "institution_id",
        "principal_id",
        "role",
        "scopes",
        "ready",
        "approved",
        "bypass",
    }
)


def _reject_spoofed_arguments(arguments: dict[str, Any]) -> None:
    for key in arguments:
        if key.strip().lower() in FORBIDDEN_ARGUMENT_KEYS:
            raise AuthenticationError(f"Untrusted MCP argument rejected: {key}")


def mcp_tool_router(
    name: str,
    arguments: dict[str, Any],
    *,
    principal: RequestPrincipal | None = None,
) -> dict[str, Any]:

    _reject_spoofed_arguments(arguments)
    if principal is None:
        raise AuthenticationError("MCP principal required")

    if name == "get_capabilities":
        return mcp_get_capabilities()
    if name == "search_knowledge":
        record = get_capability("knowledge.search")
        if record is None or record.disposition != CapabilityDisposition.READY:
            reason = record.reason if record else "Unknown"
            raise CapabilityNotReadyError(capability="knowledge.search", reason=reason)
        raise CapabilityNotReadyError(
            capability="knowledge.search",
            reason="Knowledge retrieval not ready without verified Day3/7 tenant corpus binding",
        )
    if name in {
        "analyze_attempt",
        "diagnose_answer",
        "get_learner_diagnostics",
        "get_prerequisite_gaps",
        "get_misconceptions",
    }:
        _ = principal
        block_learner_capability("learners.read")
    if name in {"recommend_remediation", "generate_diagnostic_assessment"}:
        _ = principal
        block_remediation_capability("remediation.recommend")
    if name in {
        "generate_questions",
        "validate_question",
        "generate_mock_exam",
        "get_job_status",
        "search_curriculum",
        "get_exam_pattern",
    }:
        cap_map = {
            "generate_questions": "questions.generate",
            "validate_question": "questions.validate",
            "generate_mock_exam": "tests.generate",
            "get_job_status": "jobs.read",
            "search_curriculum": "curriculum.read",
            "get_exam_pattern": "exam.read",
        }
        code = cap_map[name]
        record = get_capability(code)
        if record and record.disposition != CapabilityDisposition.READY:
            raise CapabilityNotReadyError(capability=code, reason=record.reason)
        return {"tool": name, "status": "NOT_READY", "blocked_side_effects": True}
    raise CapabilityNotReadyError(capability=name, reason=f"Unknown MCP tool {name}")