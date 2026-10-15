from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.adapters.anythingllm.factory import build_anythingllm_adapter
from app.adapters.anythingllm.protocol import AnythingLLMAdapter
from app.core.config import Settings, get_settings
from app.orchestration.checkpoint import ManagedCheckpointer, build_managed_checkpointer
from app.orchestration.gateway.factory import build_generation_gateway
from app.orchestration.gateway.protocol import GenerationGateway
from app.orchestration.service import OrchestrationService


def build_orchestration_service(
    session: Session,
    settings: Settings | None = None,
    *,
    gateway: GenerationGateway | None = None,
    knowledge_adapter: AnythingLLMAdapter | None = None,
    checkpointer: ManagedCheckpointer | None = None,
    memory_checkpointer: bool = False,
    force_fake: bool | None = None,
) -> OrchestrationService:
    resolved = settings or get_settings()
    use_fake = force_fake
    if use_fake is None:
        env_flag = os.environ.get("EDUVIJNA_ORCHESTRATION_USE_FAKE", "").strip().lower()
        use_fake = env_flag in {"1", "true", "yes"}

    gen_gateway = gateway
    if gen_gateway is None:
        gen_gateway = build_generation_gateway(resolved, force_fake=use_fake)

    ki_adapter = knowledge_adapter
    if ki_adapter is None:
        ki_adapter = build_anythingllm_adapter(resolved, force_fake=use_fake)

    managed = checkpointer or build_managed_checkpointer(
        resolved, memory_only=memory_checkpointer
    )
    return OrchestrationService(
        session,
        gateway=gen_gateway,
        ki_adapter=ki_adapter,
        managed_checkpointer=managed,
        memory_checkpointer=memory_checkpointer,
    )
