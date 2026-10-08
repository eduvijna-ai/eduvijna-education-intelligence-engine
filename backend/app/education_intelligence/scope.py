from __future__ import annotations

from dataclasses import dataclass, field

from app.models.curriculum import Competency, CurriculumNode, LearningOutcome
from app.models.enums import CurriculumNodeType


@dataclass(frozen=True)
class NodeScope:
    grade_year_code: str | None
    medium_code: str | None
    subject_code: str | None


@dataclass
class CurriculumScopeIndex:
    learning_outcomes: dict[str, LearningOutcome] = field(default_factory=dict)
    competencies_by_id: dict[str, Competency] = field(default_factory=dict)
    nodes_by_id: dict[str, CurriculumNode] = field(default_factory=dict)
    nodes_by_code: dict[str, CurriculumNode] = field(default_factory=dict)
    lo_scopes: dict[str, list[NodeScope]] = field(default_factory=dict)
    competency_scopes: dict[str, list[NodeScope]] = field(default_factory=dict)
    curriculum_version_id: str = ""
    framework_id: str | None = None
    grade_authoritative_age: dict[str, tuple[int, int]] = field(default_factory=dict)

    def scope_for_node(self, node: CurriculumNode) -> NodeScope:
        grade: str | None = None
        medium: str | None = None
        subject: str | None = None
        current: CurriculumNode | None = node
        while current is not None:
            if current.node_type == CurriculumNodeType.GRADE_YEAR.value:
                grade = current.code
            elif current.node_type == CurriculumNodeType.MEDIUM.value:
                medium = current.code
            elif current.node_type == CurriculumNodeType.SUBJECT.value:
                subject = current.code
            if current.parent_id is None:
                break
            current = self.nodes_by_id.get(current.parent_id)
        return NodeScope(grade_year_code=grade, medium_code=medium, subject_code=subject)

    def lo_matches_claim(
        self,
        lo_id: str,
        *,
        grade_year_code: str | None,
        medium_code: str | None,
        subject_code: str | None,
    ) -> tuple[bool, str | None]:
        scopes = self.lo_scopes.get(lo_id, [])
        if not scopes:
            return False, "no_linked_scope_nodes"
        for scope in scopes:
            if subject_code and scope.subject_code and scope.subject_code != subject_code:
                continue
            if (
                grade_year_code
                and scope.grade_year_code
                and scope.grade_year_code != grade_year_code
            ):
                continue
            if medium_code and scope.medium_code and scope.medium_code != medium_code:
                continue
            if subject_code and scope.subject_code is None:
                continue
            if grade_year_code and scope.grade_year_code is None:
                continue
            return True, None
        if subject_code:
            return False, "wrong_subject"
        if grade_year_code:
            return False, "wrong_grade"
        if medium_code:
            return False, "wrong_medium"
        return False, "scope_mismatch"

    def competency_in_scope(
        self,
        competency_id: str,
        *,
        framework_id: str | None,
        curriculum_version_id: str,
    ) -> bool:
        comp = self.competencies_by_id.get(competency_id)
        if comp is None:
            return False
        if framework_id and comp.framework_id and comp.framework_id != framework_id:
            return False
        scopes = self.competency_scopes.get(competency_id, [])
        if not scopes:
            return comp.framework_id == framework_id
        return any(
            s.subject_code is not None or s.grade_year_code is not None for s in scopes
        ) and curriculum_version_id == self.curriculum_version_id
