"""Production paper tenant scope validation (institution/board/org)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.tenancy import Institution
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_resolver import (
    mandatory_policy_context_errors,
    resolve_institution_board_code,
)


def production_execution_context_errors(
    session: Session,
    execution_context: PaperExecutionContext | None,
) -> list[str]:
    if execution_context is None:
        return ["execution_context"]
    institution_id = str(execution_context.institution_id or "").strip()
    if not institution_id:
        return ["execution_context.institution_id"]
    institution = session.get(Institution, institution_id)
    if institution is None or not institution.active:
        return ["execution_context.institution_id"]
    organization_id = str(execution_context.organization_id or "").strip()
    if not organization_id:
        organization_id = str(institution.organization_id)
    board_code = execution_context.board_code or resolve_institution_board_code(
        session, institution_id
    )
    normalized = PaperExecutionContext(
        institution_id=institution_id,
        organization_id=organization_id,
        board_code=board_code,
        teacher_id=execution_context.teacher_id,
        actor_id=execution_context.actor_id,
    )
    return mandatory_policy_context_errors(session, normalized)


def normalize_production_execution_context(
    session: Session,
    execution_context: PaperExecutionContext | None,
) -> tuple[PaperExecutionContext | None, list[str]]:
    errors = production_execution_context_errors(session, execution_context)
    if errors or execution_context is None:
        return execution_context, errors
    institution = session.get(Institution, execution_context.institution_id)
    assert institution is not None
    organization_id = execution_context.organization_id or str(institution.organization_id)
    board_code = execution_context.board_code or resolve_institution_board_code(
        session, str(execution_context.institution_id)
    )
    return (
        PaperExecutionContext(
            institution_id=str(execution_context.institution_id),
            organization_id=str(organization_id),
            board_code=board_code,
            teacher_id=execution_context.teacher_id,
            actor_id=execution_context.actor_id,
        ),
        [],
    )
