"""D17-32 MCP tools — same guards as REST (internal; catalogue transport disabled)."""

from __future__ import annotations

from typing import Any

from app.platform.auth.principal import RequestPrincipal
from app.platform.auth.rbac import require_permission
from app.platform.capability_registry import (
    CapabilityDisposition,
    assert_capability_ready,
    containment_snapshot,
    get_capability,
    list_capabilities,
)
from app.platform.errors import AuthenticationError, CapabilityNotReadyError
from app.platform.services.blocked import block_learner_capability, block_remediation_capability


def mcp_get_capabilities(*, principal: RequestPrincipal) -> dict[str, Any]:
    require_permission(principal.scopes, "capabilities:read")
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
        "mcp_credential",
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
    session: Any | None = None,
) -> dict[str, Any]:
    _reject_spoofed_arguments(arguments)
    if principal is None:
        raise AuthenticationError("MCP principal required")
    require_permission(principal.scopes, "mcp:invoke")

    if name == "get_capabilities":
        return mcp_get_capabilities(principal=principal)
    if name == "search_knowledge":
        assert_capability_ready("knowledge.search")
        raise CapabilityNotReadyError(
            capability="knowledge.search",
            reason="Knowledge retrieval not ready without verified Day3/7 tenant corpus binding",
        )
    if name in {"search_curriculum", "list_curricula"}:
        assert_capability_ready("curriculum.read")
    if name == "get_exam_pattern":
        assert_capability_ready("exam.read")
        raise CapabilityNotReadyError(
            capability="exam.read",
            reason="Exam pattern reads blocked pending tenant/version evidence",
        )
    if name in {
        "analyze_attempt",
        "diagnose_answer",
        "get_learner_diagnostics",
        "get_prerequisite_gaps",
        "get_misconceptions",
    }:
        block_learner_capability("learners.read")
    if name in {"recommend_remediation", "generate_diagnostic_assessment"}:
        block_remediation_capability("remediation.recommend")
    if name in {"generate_questions", "generate_mock_exam"}:
        assert_capability_ready("questions.generate")
    if name == "validate_question":
        assert_capability_ready("questions.validate")
        raise CapabilityNotReadyError(
            capability="questions.validate",
            reason="Validation not evidenced",
        )
    if name == "get_job_status":
        assert_capability_ready("jobs.read")
        raise CapabilityNotReadyError(
            capability="jobs.read",
            reason="MCP job status parity uses REST until transport accepted",
        )
    record = get_capability(name.replace("_", "."))
    if record and record.disposition != CapabilityDisposition.READY:
        raise CapabilityNotReadyError(capability=record.code, reason=record.reason)
    raise CapabilityNotReadyError(capability=name, reason=f"Unknown or blocked MCP tool {name}")