from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.adapters.anythingllm.protocol import AnythingLLMAdapter
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.knowledge_intelligence.service import KnowledgeIntelligenceService
from app.orchestration.checkpoint import build_checkpointer
from app.orchestration.contracts import OrchestrationRequest, OrchestrationResult, utc_now
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.graph import build_orchestration_graph
from app.orchestration.idempotency import load_completed_result, store_completed_result
from app.orchestration.prompts.registry import prompt_versions_used
from app.orchestration.state import OrchestrationGraphState


class OrchestrationService:
    """High-level orchestration entrypoint (callable without FastAPI)."""

    def __init__(
        self,
        session: Session,
        *,
        gateway: FakeGenerationGateway | None = None,
        ki_adapter: AnythingLLMAdapter | None = None,
        memory_checkpointer: bool = False,
    ) -> None:
        retrieval_adapter = ki_adapter or FakeAnythingLLMAdapter()
        self._session = session
        self._deps = OrchestrationDependencies(
            session=session,
            knowledge_service=KnowledgeIntelligenceService(session, adapter=retrieval_adapter),
            education_service=EducationIntelligenceValidationService(session),
            gateway=gateway or FakeGenerationGateway(),
        )
        from app.core.config import get_settings

        self._checkpointer = build_checkpointer(
            get_settings(), memory_only=memory_checkpointer
        )
        self._graph: Any = build_orchestration_graph(self._deps, checkpointer=self._checkpointer)

    @property
    def dependencies(self) -> OrchestrationDependencies:
        return self._deps

    @property
    def compiled_graph(self) -> Any:
        return self._graph

    def run(
        self,
        request: OrchestrationRequest,
        *,
        resume: bool = False,
    ) -> OrchestrationResult:
        cached = load_completed_result(self._session, request)
        if cached is not None:
            return cached

        thread_id = request.run_id or request.idempotency_key
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        initial: OrchestrationGraphState = {
            "run_id": request.run_id or thread_id,
            "thread_id": thread_id,
            "request": request.model_dump(mode="json"),
            "request_hash": request.request_hash(),
            "status": OrchestrationRunStatus.PLANNING.value,
            "prompt_versions": prompt_versions_used(),
            "repair_count_by_item": {},
            "repair_instructions_by_item": {},
            "warnings": [],
            "errors": [],
            "created_at": utc_now().isoformat(),
            "updated_at": utc_now().isoformat(),
        }

        if resume:
            final_state = self._graph.invoke(None, config=config)
        else:
            final_state = self._graph.invoke(initial, config=config)

        if self._graph.get_state(config).next:
            # Paused at human-in-the-loop gate; synthesize interim result.
            result = OrchestrationResult(
                run_id=initial["run_id"],
                status=OrchestrationRunStatus.REVIEW_REQUIRED,
                requested_count=request.requested_count,
                approved_count=0,
                items=[],
                source_revision_ids=[],
                retrieval_profile_version=request.retrieval_profile_version,
                prompt_versions=final_state.get("prompt_versions") or {},
                repair_summary=final_state.get("repair_count_by_item") or {},
                warnings=list(final_state.get("warnings") or []),
                errors=list(final_state.get("errors") or []),
                audit_refs=[],
                request_hash=request.request_hash(),
                started_at=utc_now(),
                completed_at=None,
                gateway_usage=final_state.get("gateway_usage") or {},
                metadata_json={"interrupt_payload": final_state.get("interrupt_payload")},
            )
            self._session.commit()
            return result

        payload = final_state.get("final_result")
        if payload is None:
            result = OrchestrationResult(
                run_id=initial["run_id"],
                status=OrchestrationRunStatus.FAILED,
                requested_count=request.requested_count,
                approved_count=0,
                items=[],
                source_revision_ids=[],
                retrieval_profile_version=request.retrieval_profile_version,
                prompt_versions=final_state.get("prompt_versions") or {},
                repair_summary={},
                warnings=list(final_state.get("warnings") or []),
                errors=list(final_state.get("errors") or ["missing_final_result"]),
                audit_refs=[],
                request_hash=request.request_hash(),
                started_at=utc_now(),
                completed_at=utc_now(),
                gateway_usage=final_state.get("gateway_usage") or {},
            )
            self._session.commit()
            return result

        result = OrchestrationResult.model_validate(payload)
        if result.status == OrchestrationRunStatus.COMPLETED:
            store_completed_result(self._session, request, result)
        self._session.commit()
        return result
