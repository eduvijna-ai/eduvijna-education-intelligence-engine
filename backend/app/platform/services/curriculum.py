from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.curriculum import CurriculumPack
from app.models.examination import ExamPack
from app.platform.auth.principal import RequestPrincipal
from app.platform.auth.rbac import require_permission
from app.platform.capability_registry import assert_capability_operable
from app.platform.errors import NotFoundError
from app.platform.schemas.endpoints import CurriculumListItem, ExamListItem


def list_curricula(session: Session, *, principal: RequestPrincipal) -> list[CurriculumListItem]:
    assert_capability_operable("curriculum.read")
    require_permission(principal.scopes, "curriculum:read")
    rows = session.scalars(select(CurriculumPack).limit(50)).all()
    return [CurriculumListItem(id=UUID(row.id), code=row.code, title=row.name) for row in rows]


def get_curriculum(
    session: Session, *, principal: RequestPrincipal, curriculum_id: UUID
) -> CurriculumListItem:
    assert_capability_operable("curriculum.read")
    require_permission(principal.scopes, "curriculum:read")
    row = session.scalar(select(CurriculumPack).where(CurriculumPack.id == str(curriculum_id)))
    if row is None:
        raise NotFoundError("Curriculum not found")
    return CurriculumListItem(id=UUID(row.id), code=row.code, title=row.name)


def list_exams(session: Session, *, principal: RequestPrincipal) -> list[ExamListItem]:
    assert_capability_operable("exam.read")
    require_permission(principal.scopes, "exam:read")
    rows = session.scalars(select(ExamPack).limit(50)).all()
    return [ExamListItem(id=UUID(row.id), code=row.code, title=row.name) for row in rows]


def get_exam_pattern(
    session: Session, *, principal: RequestPrincipal, exam_id: UUID
) -> dict[str, object]:
    assert_capability_operable("exam.read")
    require_permission(principal.scopes, "exam:read")
    row = session.scalar(select(ExamPack).where(ExamPack.id == str(exam_id)))
    if row is None:
        raise NotFoundError("Exam not found")
    return {
        "exam_id": row.id,
        "code": row.code,
        "title": row.name,
        "pattern_available": False,
        "official_verified": False,
        "readiness": "metadata_only_not_version_verified",
    }
