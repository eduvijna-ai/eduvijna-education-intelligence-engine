from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.curriculum import CurriculumNode
from app.models.enums import CurriculumNodeType
from app.orchestration.contracts import ResolvedScope


def _find_nodes(
    session: Session,
    *,
    curriculum_version_id: str,
    code: str,
    node_type: str,
) -> list[CurriculumNode]:
    return list(
        session.scalars(
            select(CurriculumNode).where(
                CurriculumNode.curriculum_version_id == curriculum_version_id,
                CurriculumNode.code == code,
                CurriculumNode.node_type == node_type,
            )
        )
    )


def _is_descendant_of(
    session: Session,
    node: CurriculumNode,
    ancestor_id: str,
) -> bool:
    current = node
    visited: set[str] = set()
    while current.parent_id is not None:
        if current.parent_id == ancestor_id:
            return True
        if current.parent_id in visited:
            return False
        visited.add(current.parent_id)
        parent = session.get(CurriculumNode, current.parent_id)
        if parent is None or parent.curriculum_version_id != node.curriculum_version_id:
            return False
        current = parent
    return False


def _unique_scoped_node(
    session: Session,
    nodes: list[CurriculumNode],
    *,
    ancestor_ids: list[str],
) -> CurriculumNode | None:
    scoped = nodes
    if ancestor_ids:
        scoped = [
            node
            for node in nodes
            if any(_is_descendant_of(session, node, ancestor_id) for ancestor_id in ancestor_ids)
        ]
    if len(scoped) != 1:
        return None
    return scoped[0]


def validate_curriculum_hierarchy(session: Session, scope: ResolvedScope) -> list[str]:
    errors: list[str] = []
    cv_id = scope.curriculum_version_id
    if not cv_id:
        return errors

    grade_node: CurriculumNode | None = None
    if scope.grade_year_code:
        grade_candidates = [
            node
            for node in _find_nodes(
                session,
                curriculum_version_id=cv_id,
                code=scope.grade_year_code,
                node_type=CurriculumNodeType.GRADE_YEAR.value,
            )
            if node.parent_id is None
        ]
        grade_node = grade_candidates[0] if len(grade_candidates) == 1 else None
        if grade_node is None:
            errors.append("invalid_grade_year_code")

    medium_node: CurriculumNode | None = None
    if scope.medium_code:
        if scope.grade_year_code and grade_node is None:
            return errors
        medium_candidates = _find_nodes(
            session,
            curriculum_version_id=cv_id,
            code=scope.medium_code,
            node_type=CurriculumNodeType.MEDIUM.value,
        )
        if grade_node is not None:
            medium_candidates = [
                node for node in medium_candidates if node.parent_id == grade_node.id
            ]
        medium_node = medium_candidates[0] if len(medium_candidates) == 1 else None
        if medium_node is None:
            errors.append("invalid_medium_code")

    subject_node: CurriculumNode | None = None
    if scope.subject_code:
        if scope.medium_code and medium_node is None:
            return errors
        subject_candidates = _find_nodes(
            session,
            curriculum_version_id=cv_id,
            code=scope.subject_code,
            node_type=CurriculumNodeType.SUBJECT.value,
        )
        if medium_node is not None:
            subject_candidates = [
                node for node in subject_candidates if node.parent_id == medium_node.id
            ]
            subject_node = (
                subject_candidates[0] if len(subject_candidates) == 1 else None
            )
        elif grade_node is not None:
            subject_node = _unique_scoped_node(
                session,
                subject_candidates,
                ancestor_ids=[grade_node.id],
            )
        else:
            subject_node = (
                subject_candidates[0] if len(subject_candidates) == 1 else None
            )
        if subject_node is None:
            errors.append("invalid_subject_code")

    deepest_anchor = subject_node or medium_node or grade_node
    selected_topics: list[CurriculumNode] = []
    for topic_code in scope.topic_codes:
        topic = _unique_scoped_node(
            session,
            _find_nodes(
                session,
                curriculum_version_id=cv_id,
                code=topic_code,
                node_type=CurriculumNodeType.TOPIC.value,
            ),
            ancestor_ids=[deepest_anchor.id] if deepest_anchor is not None else [],
        )
        if topic is None:
            errors.append(f"invalid_topic_code:{topic_code}")
        else:
            selected_topics.append(topic)

    concept_anchor_ids = (
        [node.id for node in selected_topics]
        if scope.topic_codes
        else ([deepest_anchor.id] if deepest_anchor is not None else [])
    )
    for concept_code in scope.concept_codes:
        concept = _unique_scoped_node(
            session,
            _find_nodes(
                session,
                curriculum_version_id=cv_id,
                code=concept_code,
                node_type=CurriculumNodeType.CONCEPT.value,
            ),
            ancestor_ids=concept_anchor_ids,
        )
        if concept is None:
            errors.append(f"invalid_concept_code:{concept_code}")

    return errors
