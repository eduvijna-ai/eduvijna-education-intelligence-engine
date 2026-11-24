"""D17-32 MCP tools — same guards as REST."""

from __future__ import annotations

from typing import Any

from app.platform.capability_registry import (
    containment_snapshot,
    get_capability,
    list_capabilities,
)
from app.platform.errors import CapabilityNotReadyError
from app.platform.services.blocked import block_learner_capability, block_remediation_capability
from app.platform.services.knowledge import search_knowledge


def mcp_get_capabilities(_: dict[str, Any] | None = None) -> dict[str, Any]:
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


def mcp_search_knowledge(payload: dict[str, Any]) -> dict[str, Any]:
    from app.platform.auth.principal import RequestPrincipal

    principal = RequestPrincipal(
        principal_id=str(payload.get("principal_id", "mcp-local")),
        organization_id=str(payload["organization_id"]),
        institution_id=payload.get("institution_id"),
        role=str(payload.get("role", "teacher")),
        scopes=tuple(payload.get("scopes", ("knowledge:read",))),
        actor_kind="mcp",
        actor_ref="mcp",
        auth_method="mcp",
    )
    response = search_knowledge(
        principal=principal,
        query=str(payload["query"]),
        limit=int(payload.get("limit", 5)),
    )
    return response.model_dump()


def mcp_blocked_tool(capability_code: str) -> dict[str, Any]:
    record = get_capability(capability_code)
    reason = record.reason if record else "unknown capability"
    raise CapabilityNotReadyError(capability=capability_code, reason=reason)


def mcp_tool_router(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "get_capabilities":
        return mcp_get_capabilities(arguments)
    if name == "search_knowledge":
        return mcp_search_knowledge(arguments)
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
        if record and record.disposition.value != "ready":
            raise CapabilityNotReadyError(capability=code, reason=record.reason)
        return {"tool": name, "status": "contract_only", "blocked_side_effects": True}
    raise CapabilityNotReadyError(capability=name, reason=f"Unknown MCP tool {name}")
