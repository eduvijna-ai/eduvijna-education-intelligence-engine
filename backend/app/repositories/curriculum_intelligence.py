from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.curriculum import (
    Competency,
    CurriculumNode,
    CurriculumPack,
    CurriculumVersion,
    EducationFramework,
    LearningOutcome,
)
from app.models.curriculum_intelligence import AssessmentEvidence, CurriculumAlignment


class CurriculumIntelligenceRepository:
    """Read/query boundary for Day-4 curriculum intelligence."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def framework_by_code(self, code: str) -> EducationFramework | None:
        return self.session.scalar(
            select(EducationFramework).where(EducationFramework.code == code)
        )

    def pack_by_code(self, code: str) -> CurriculumPack | None:
        return self.session.scalar(select(CurriculumPack).where(CurriculumPack.code == code))

    def version(self, pack_id: str, version_code: str) -> CurriculumVersion | None:
        return self.session.scalar(
            select(CurriculumVersion).where(
                CurriculumVersion.curriculum_pack_id == pack_id,
                CurriculumVersion.version_code == version_code,
            )
        )

    def node_by_code(self, version_id: str, code: str) -> CurriculumNode | None:
        return self.session.scalar(
            select(CurriculumNode).where(
                CurriculumNode.curriculum_version_id == version_id,
                CurriculumNode.code == code,
            )
        )

    def children(self, node_id: str) -> list[CurriculumNode]:
        return list(
            self.session.scalars(
                select(CurriculumNode)
                .where(CurriculumNode.parent_id == node_id)
                .order_by(CurriculumNode.sequence, CurriculumNode.code)
            )
        )

    def learning_outcome(
        self, version_id: str, code: str
    ) -> LearningOutcome | None:
        return self.session.scalar(
            select(LearningOutcome).where(
                LearningOutcome.curriculum_version_id == version_id,
                LearningOutcome.code == code,
            )
        )

    def competency(self, code: str) -> Competency | None:
        return self.session.scalar(select(Competency).where(Competency.code == code))

    def alignments_for_node(self, node_id: str) -> list[CurriculumAlignment]:
        return list(
            self.session.scalars(
                select(CurriculumAlignment).where(
                    CurriculumAlignment.curriculum_node_id == node_id
                )
            )
        )

    def assessment_evidence_for_subject(
        self, version_id: str, subject_node_id: str
    ) -> list[AssessmentEvidence]:
        return list(
            self.session.scalars(
                select(AssessmentEvidence).where(
                    AssessmentEvidence.curriculum_version_id == version_id,
                    AssessmentEvidence.subject_node_id == subject_node_id,
                )
            )
        )
