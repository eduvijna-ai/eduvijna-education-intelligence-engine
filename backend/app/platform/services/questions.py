from __future__ import annotations

from typing import NoReturn

from sqlalchemy.orm import Session

from app.platform.auth.principal import RequestPrincipal
from app.platform.auth.rbac import require_permission
from app.platform.errors import CapabilityNotReadyError
from app.platform.schemas.endpoints import ValidateQuestionResponse


def submit_question_generation(
    session: Session,
    *,
    principal: RequestPrincipal,
    topic_code: str,
    count: int,
    idempotency_key: str,
) -> NoReturn:
    _ = session
    _ = topic_code
    _ = count
    _ = idempotency_key
    require_permission(principal.scopes, "generation:submit")
    from app.platform.capability_registry import get_capability

    cap = get_capability("questions.generate")
    if cap is None:
        raise CapabilityNotReadyError(capability="questions.generate", reason="Unknown")
    raise CapabilityNotReadyError(capability="questions.generate", reason=cap.reason)


def validate_question(
    session: Session,
    *,
    principal: RequestPrincipal,
    question_text: str,
) -> ValidateQuestionResponse:
    _ = session
    _ = question_text
    require_permission(principal.scopes, "generation:validate")
    from app.platform.capability_registry import get_capability

    cap = get_capability("questions.validate")
    if cap is None:
        raise CapabilityNotReadyError(capability="questions.validate", reason="Unknown")
    raise CapabilityNotReadyError(capability="questions.validate", reason=cap.reason)


def submit_mock_exam_generation(
    session: Session,
    *,
    principal: RequestPrincipal,
    exam_version_id: str,
    question_count: int,
    idempotency_key: str,
) -> NoReturn:
    _ = exam_version_id
    _ = question_count
    _ = idempotency_key
    require_permission(principal.scopes, "generation:submit")
    from app.platform.capability_registry import get_capability

    cap = get_capability("tests.generate")
    if cap is None:
        raise CapabilityNotReadyError(capability="tests.generate", reason="Unknown")
    raise CapabilityNotReadyError(capability="tests.generate", reason=cap.reason)