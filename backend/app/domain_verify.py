from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models import (
    Competency,
    ConceptPrerequisite,
    CurriculumNode,
    CurriculumPack,
    CurriculumVersion,
    DiagnosticTaxonomyEntry,
    EducationFramework,
    ExamBlueprintRule,
    ExamPack,
    ExamSection,
    ExamVersion,
    LearningOutcome,
    PolicyRule,
    Question,
    QuestionOption,
    Source,
    TestDefinition,
    TestQuestion,
)
from app.models.enums import (
    BlueprintRuleType,
    CurriculumNodeType,
    DiagnosticCategory,
    PolicyScopeType,
    QuestionOrigin,
    QuestionType,
    SourceType,
)


def build_verification_payload() -> dict[str, object]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        source = Source(
            source_type=SourceType.OFFICIAL_SYLLABUS.value,
            title="Synthetic official source",
        )
        framework = EducationFramework(
            code="verify-framework",
            name="Verify Framework",
            country="IN",
        )
        pack = CurriculumPack(
            code="verify-curriculum",
            name="Verify Curriculum",
            country="IN",
            framework=framework,
        )
        version = CurriculumVersion(
            curriculum_pack=pack,
            version_code="2026-27",
            status="active",
        )
        version.sources.append(source)
        subject = CurriculumNode(
            curriculum_version=version,
            node_type=CurriculumNodeType.SUBJECT.value,
            code="mathematics",
            title="Mathematics",
        )
        prereq = CurriculumNode(
            curriculum_version=version,
            parent=subject,
            node_type=CurriculumNodeType.CONCEPT.value,
            code="algebra-basics",
            title="Algebra basics",
        )
        concept = CurriculumNode(
            curriculum_version=version,
            parent=subject,
            node_type=CurriculumNodeType.CONCEPT.value,
            code="advanced-algebra",
            title="Advanced algebra",
        )
        outcome = LearningOutcome(
            curriculum_version=version,
            code="verify-lo",
            text="Apply algebraic reasoning.",
        )
        competency = Competency(code="problem_solving", name="Problem solving")
        concept.learning_outcomes.append(outcome)
        concept.competencies.append(competency)
        edge = ConceptPrerequisite(
            prerequisite_concept=prereq,
            target_concept=concept,
        )

        exam_pack = ExamPack(code="verify-exam", name="Verify Exam", country="IN")
        exam_version = ExamVersion(exam_pack=exam_pack, version_code="2026", status="active")
        section = ExamSection(
            exam_version=exam_version,
            code="math",
            title="Mathematics",
            sequence=1,
        )
        exact = ExamBlueprintRule(
            exam_version=exam_version,
            section=section,
            rule_type=BlueprintRuleType.QUESTION_COUNT.value,
            exact_count=10,
        )
        ranged = ExamBlueprintRule(
            exam_version=exam_version,
            section=section,
            rule_type=BlueprintRuleType.TOPIC_DISTRIBUTION.value,
            min_count=2,
            max_count=5,
        )

        diagnostic = DiagnosticTaxonomyEntry(
            code="FORMULA_SELECTION_ERROR",
            name="Formula selection error",
            category=DiagnosticCategory.FORMULA_KNOWLEDGE.value,
        )
        question = Question(
            origin_type=QuestionOrigin.GENERATED.value,
            curriculum_version=version,
            exam_version=exam_version,
            primary_curriculum_node=concept,
            question_type=QuestionType.SINGLE_CHOICE.value,
            stem_text="Synthetic verification question",
            answer_json={"option_key": "B"},
        )
        question.options.extend(
            [
                QuestionOption(
                    option_key="A",
                    text="Diagnostic distractor",
                    diagnostic_taxonomy_entry=diagnostic,
                    error_code="FORMULA_SELECTION_ERROR",
                ),
                QuestionOption(option_key="B", text="Correct answer", is_correct=True),
            ]
        )
        question.sources.append(source)

        test = TestDefinition(code="verify-test", title="Verification test")
        test.questions.append(TestQuestion(question=question, sequence=1))

        policy = PolicyRule(
            scope_type=PolicyScopeType.INSTITUTION.value,
            scope_code="verify-school",
            policy_key="question.difficulty.max",
            value_json={"value": 4},
            priority=300,
        )

        session.add_all(
            [
                framework,
                pack,
                version,
                subject,
                prereq,
                concept,
                outcome,
                competency,
                edge,
                exam_pack,
                exam_version,
                section,
                exact,
                ranged,
                diagnostic,
                question,
                test,
                policy,
            ]
        )
        session.commit()

        return {
            "curriculum": {
                "pack": pack.code,
                "version": version.version_code,
                "concept": concept.code,
                "prerequisite": prereq.code,
                "learning_outcome": outcome.code,
                "competency": competency.code,
            },
            "exam": {
                "pack": exam_pack.code,
                "version": exam_version.version_code,
                "exact_count": exact.exact_count,
                "range": [ranged.min_count, ranged.max_count],
            },
            "question": {
                "type": question.question_type,
                "diagnostic_error": question.options[0].error_code,
                "source": source.title,
            },
            "test": test.code,
            "policy": {
                "scope": policy.scope_type,
                "priority": policy.priority,
            },
        }
    finally:
        session.close()


def main() -> None:
    print(json.dumps(build_verification_payload(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
