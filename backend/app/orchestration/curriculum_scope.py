from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.curriculum import CurriculumNode
from app.models.enums import CurriculumNodeType
from app.orchestration.contracts import ResolvedScope


def _find_node(
    session: Session,
    *,
    curriculum_version_id: str,
    code: str,
    node_type: str,
    parent_id: str | None,
) -> CurriculumNode | None:
    stmt = select(CurriculumNode).where(
        CurriculumNode.curriculum_version_id == curriculum_version_id,
        CurriculumNode.code == code,
        CurriculumNode.node_type == node_type,
    )
    if parent_id is None:
        stmt = stmt.where(CurriculumNode.parent_id.is_(None))
    else:
        stmt = stmt.where(CurriculumNode.parent_id == parent_id)
    return session.scalar(stmt)


def validate_curriculum_hierarchy(session: Session, scope: ResolvedScope) -> list[str]:
    errors: list[str] = []
    cv_id = scope.curriculum_version_id
    if not cv_id:
        return errors

    grade_node: CurriculumNode | None = None
    if scope.grade_year_code:
        grade_node = _find_node(
            session,
            curriculum_version_id=cv_id,
            code=scope.grade_year_code,
            node_type=CurriculumNodeType.GRADE_YEAR.value,
            parent_id=None,
        )
        if grade_node is None:
            errors.append("invalid_grade_year_code")

    medium_node: CurriculumNode | None = None
    if scope.medium_code:
        parent = grade_node.id if grade_node is not None else None
        if grade_node is None and scope.grade_year_code:
            return errors
        medium_node = _find_node(
            session,
            curriculum_version_id=cv_id,
            code=scope.medium_code,
            node_type=CurriculumNodeType.MEDIUM.value,
            parent_id=parent,
        )
        if medium_node is None:
            errors.append("invalid_medium_code")

    subject_node: CurriculumNode | None = None
    if scope.subject_code:
        parent = medium_node.id if medium_node is not None else None
        if scope.medium_code and medium_node is None:
            return errors
        subject_node = _find_node(
            session,
            curriculum_version_id=cv_id,
            code=scope.subject_code,
            node_type=CurriculumNodeType.SUBJECT.value,
            parent_id=parent,
        )
        if subject_node is None:
            errors.append("invalid_subject_code")

    for topic_code in scope.topic_codes:
        node = _find_node(
            session,
            curriculum_version_id=cv_id,
            code=topic_code,
            node_type=CurriculumNodeType.TOPIC.value,
            parent_id=None,
        )
        if node is None:
            errors.append(f"invalid_topic_code:{topic_code}")

    for concept_code in scope.concept_codes:
        node = _find_node(
            session,
            curriculum_version_id=cv_id,
            code=concept_code,
            node_type=CurriculumNodeType.CONCEPT.value,
            parent_id=None,
        )
        if node is None:
            errors.append(f"invalid_concept_code:{concept_code}")

    return errors
