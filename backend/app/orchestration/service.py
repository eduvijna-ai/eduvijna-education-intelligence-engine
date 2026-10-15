from __future__ import annotations

from typing import Any

from langgraph.types import Command
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.adapters.anythingllm.protocol import AnythingLLMAdapter
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.knowledge_intelligence.service import KnowledgeIntelligenceService
from app.orchestration.checkpoint import ManagedCheckpointer, build_managed_checkpointer
from app.orchestration.contracts import OrchestrationRequest, OrchestrationResult, utc_now
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.gateway.protocol import GenerationGateway
from app.orchestration.graph import build_orchestration_graph
from app.orchestration.human_decision import HumanResumeDecision
from app.orchestration.idempotency import (
    claim_idempotency,
    store_completed_result,
    store_terminal_result,
)
from app.orchestration.prompts.registry import prompt_versions_used
from app.orchestration.state import OrchestrationGraphState


def _interrupt_payload_from_snapshot(snapshot: Any) -> dict[str, Any] | None:
    interrupts = getattr(snapshot, "interrupts", None)
    if interrupts:
        first = interrupts[0]
        value = getattr(first, "value", first)
        if isinstance(value, dict):
            return value
    tasks = getattr(snapshot, "tasks", None) or ()
    for task in tasks:
        task_interrupts = getattr(task, "interrupts", None) or ()
        if task_interrupts:
            value = getattr(task_interrupts[0], "value", task_interrupts[0])
            if isinstance(value, dict):
                return value
    return None


class OrchestrationService:
    """High-level orchestration entrypoint (callable without FastAPI)."""

    def __init__(
        self,
        session: Session,
        *,
        gateway: GenerationGateway,
        ki_adapter: AnythingLLMAdapter,
        managed_checkpointer: ManagedCheckpointer | None = None,
        memory_checkpointer: bool = False,
    ) -> None:
        from app.core.config import get_settings

        self._session = session
        self._managed = managed_checkpointer or build_managed_checkpointer(
            get_settings(), memory_only=memory_checkpointer
        )
        self._deps = OrchestrationDependencies(
            session=session,
            knowledge_service=KnowledgeIntelligenceService(session, adapter=ki_adapter),
            education_service=EducationIntelligenceValidationService(session),
            gateway=gateway,
        )
        self._graph: Any = build_orchestration_graph(
            self._deps, checkpointer=self._managed.saver
        )

    @property
    def dependencies(self) -> OrchestrationDependencies:
        return self._deps

    @property
    def compiled_graph(self) -> Any:
        return self._graph

    @property
    def managed_checkpointer(self) -> ManagedCheckpointer:
        return self._managed

    def close(self) -> None:
        self._managed.close()

    def run(
        self,
        request: OrchestrationRequest,
        *,
        resume: HumanResumeDecision | None = None,
    ) -> OrchestrationResult:
        terminal, canonical_run_id, record_status = claim_idempotency(self._session, request)
        self._session.commit()
        if terminal is not None:
            return terminal

        canonical_request = request.model_copy(update={"run_id": canonical_run_id})
        thread_id = canonical_run_id
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        snapshot = self._graph.get_state(config)

        if resume is not None:
            try:
                resume_payload = resume.model_dump(mode="json")
                final_state = self._graph.invoke(Command(resume=resume_payload), config=config)
            except ValidationError as exc:
                return self._failed_result(
                    canonical_request,
                    thread_id,
                    errors=["invalid_human_resume"],
                    metadata={"validation_errors": str(exc)},
                )
        elif snapshot.next and snapshot.values:
            if snapshot.next == ("human_gate",):
                interrupt_payload = _interrupt_payload_from_snapshot(snapshot)
                return self._paused_result(
                    canonical_request, thread_id, snapshot.values, interrupt_payload
                )
            final_state = self._graph.invoke(None, config=config)
        elif snapshot.values and record_status == "in_progress":
            final_state = self._graph.invoke(None, config=config)
        else:
            initial: OrchestrationGraphState = {
                "run_id": canonical_run_id,
                "thread_id": thread_id,
                "request": canonical_request.model_dump(mode="json"),
                "request_hash": canonical_request.request_hash(),
                "status": OrchestrationRunStatus.PLANNING.value,
                "prompt_versions": prompt_versions_used(),
                "repair_count_by_item": {},
                "repair_instructions_by_item": {},
                "repair_item_ids": [],
                "generation_call_cache": {},
                "warnings": [],
                "errors": [],
                "audit_refs": [],
                "pipeline_halt": False,
                "human_revalidate": False,
                "human_approved": False,
                "created_at": utc_now().isoformat(),
                "updated_at": utc_now().isoformat(),
            }
            final_state = self._graph.invoke(initial, config=config)

        post_snapshot = self._graph.get_state(config)
        if post_snapshot.next:
            interrupt_payload = _interrupt_payload_from_snapshot(post_snapshot)
            return self._paused_result(
                canonical_request, thread_id, final_state, interrupt_payload
            )

        payload = final_state.get("final_result")
        if payload is None:
            result = self._failed_result(
                canonical_request,
                thread_id,
                errors=list(final_state.get("errors") or ["missing_final_result"]),
                warnings=list(final_state.get("warnings") or []),
                audit_refs=list(final_state.get("audit_refs") or []),
                gateway_usage=final_state.get("gateway_usage") or {},
                prompt_versions=final_state.get("prompt_versions") or {},
            )
            store_terminal_result(self._session, canonical_request, result, status="failed")
            self._session.commit()
            return result

        result = OrchestrationResult.model_validate(payload)
        if result.status == OrchestrationRunStatus.COMPLETED:
            store_completed_result(self._session, canonical_request, result)
        elif result.status == OrchestrationRunStatus.FAILED:
            store_terminal_result(self._session, canonical_request, result, status="failed")
        self._session.commit()
        return result

    def _paused_result(
        self,
        request: OrchestrationRequest,
        thread_id: str,
        state_values: dict[str, Any],
        interrupt_payload: dict[str, Any] | None,
    ) -> OrchestrationResult:
        result = OrchestrationResult(
            run_id=thread_id,
            status=OrchestrationRunStatus.REVIEW_REQUIRED,
            requested_count=request.requested_count,
            approved_count=0,
            items=[],
            source_revision_ids=[],
            retrieval_profile_version=request.retrieval_profile_version,
            prompt_versions=state_values.get("prompt_versions") or {},
            repair_summary=state_values.get("repair_count_by_item") or {},
            warnings=list(state_values.get("warnings") or []),
            errors=list(state_values.get("errors") or []),
            audit_refs=list(state_values.get("audit_refs") or []),
            request_hash=request.request_hash(),
            started_at=utc_now(),
            completed_at=None,
            gateway_usage=state_values.get("gateway_usage") or {},
            metadata_json={"interrupt_payload": interrupt_payload},
        )
        self._session.commit()
        return result

    def _failed_result(
        self,
        request: OrchestrationRequest,
        thread_id: str,
        *,
        errors: list[str],
        warnings: list[str] | None = None,
        audit_refs: list[str] | None = None,
        gateway_usage: dict[str, Any] | None = None,
        prompt_versions: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> OrchestrationResult:
        return OrchestrationResult(
            run_id=thread_id,
            status=OrchestrationRunStatus.FAILED,
            requested_count=request.requested_count,
            approved_count=0,
            items=[],
            source_revision_ids=[],
            retrieval_profile_version=request.retrieval_profile_version,
            prompt_versions=prompt_versions or {},
            repair_summary={},
            warnings=warnings or [],
            errors=errors,
            audit_refs=audit_refs or [],
            request_hash=request.request_hash(),
            started_at=utc_now(),
            completed_at=utc_now(),
            gateway_usage=gateway_usage or {},
            metadata_json=metadata or {},
        )
