from __future__ import annotations

from typing import cast

from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.core.config import get_settings
from app.jee_main_exam_intelligence.contracts import PaperPlanRequest
from app.orchestration.exceptions import OrchestrationConfigurationError
from app.orchestration.gateway.factory import build_generation_gateway
from app.orchestration.gateway.protocol import GenerationGateway

INJECT_GATEWAY_KEY = "eduvijna_pgc_test_inject_gateway"


def resolve_live_generation_gateway(
    session: Session,
    request: PaperPlanRequest,
    gateway: GenerationGateway | None,
) -> GenerationGateway | None:
    """Explicit gateway, test session inject, or configured production factory."""
    if gateway is not None:
        return gateway
    inject = session.info.get(INJECT_GATEWAY_KEY)
    if inject is not None:
        return cast(GenerationGateway, inject)
    if request.execution_mode != TrustExecutionMode.PRODUCTION:
        return None
    try:
        return build_generation_gateway(get_settings(), force_fake=False)
    except OrchestrationConfigurationError:
        return None
