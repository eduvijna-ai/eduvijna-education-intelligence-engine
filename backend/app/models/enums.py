from enum import StrEnum


class SourceType(StrEnum):
    OFFICIAL_AUTHORITY = "official_authority"
    OFFICIAL_SYLLABUS = "official_syllabus"
    OFFICIAL_EXAM_BULLETIN = "official_exam_bulletin"
    OFFICIAL_PAPER = "official_paper"
    ANSWER_KEY = "answer_key"
    MARKING_SCHEME = "marking_scheme"
    SAMPLE_PAPER = "sample_paper"
    COMPETITIVE_ANALYSIS = "competitive_analysis"
    INSTITUTION_CONTENT = "institution_content"
    TEACHER_CONTENT = "teacher_content"


class SourceStatus(StrEnum):
    STAGED = "staged"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INACTIVE = "inactive"


class SourceTrustTier(StrEnum):
    OFFICIAL_PRIMARY = "official_primary"
    OFFICIAL_SUPPORTING = "official_supporting"
    ANALYTICAL = "analytical"
    INSTITUTION = "institution"
    TEACHER = "teacher"


class CurriculumStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class CurriculumNodeType(StrEnum):
    GRADE_YEAR = "grade_year"
    MEDIUM = "medium"
    SUBJECT = "subject"
    UNIT = "unit"
    CHAPTER = "chapter"
    TOPIC = "topic"
    CONCEPT = "concept"


class ExamStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class BlueprintRuleType(StrEnum):
    QUESTION_COUNT = "question_count"
    QUESTION_TYPE = "question_type"
    TOPIC_DISTRIBUTION = "topic_distribution"
    DIFFICULTY_DISTRIBUTION = "difficulty_distribution"
    COGNITIVE_DISTRIBUTION = "cognitive_distribution"
    SCORING = "scoring"


class DiagnosticCategory(StrEnum):
    CONCEPT_MASTERY = "concept_mastery"
    FORMULA_KNOWLEDGE = "formula_knowledge"
    CALCULATION = "calculation"
    MISCONCEPTION = "misconception"
    APPLICATION_GAP = "application_gap"
    REASONING_GAP = "reasoning_gap"
    PREREQUISITE_GAP = "prerequisite_gap"


class QuestionOrigin(StrEnum):
    GENERATED = "generated"
    IMPORTED = "imported"
    TEACHER = "teacher"
    INSTITUTION = "institution"


class QuestionType(StrEnum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    NUMERICAL = "numerical"
    DESCRIPTIVE = "descriptive"
    PASSAGE_BASED = "passage_based"
    MULTI_PART = "multi_part"


class QuestionStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETIRED = "retired"


class QuestionAssetType(StrEnum):
    IMAGE = "image"
    SVG = "svg"
    GRAPH = "graph"
    TABLE = "table"
    DIAGRAM = "diagram"
    PASSAGE = "passage"


class CognitiveLevel(StrEnum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"


class TestStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class PolicyScopeType(StrEnum):
    COUNTRY = "country"
    BOARD = "board"
    EXAM = "exam"
    INSTITUTION = "institution"
    TEACHER = "teacher"
