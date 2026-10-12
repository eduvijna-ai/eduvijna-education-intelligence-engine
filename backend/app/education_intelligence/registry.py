from __future__ import annotations

from dataclasses import dataclass, field

from app.education_intelligence.validators.alignment import (
    LearningOutcomeValidator,
    SourceBackedCompetencyValidator,
)
from app.education_intelligence.validators.base import ItemValidator
from app.education_intelligence.validators.cognition import (
    CognitiveDemandEvidenceValidator,
    CognitiveProgressionValidator,
    TargetObservedCognitiveValidator,
)
from app.education_intelligence.validators.difficulty_age_quality import (
    AgeGradeAppropriatenessValidator,
    DifficultyValidator,
    EducationalQualityRulePackValidator,
    StructuralClarityValidator,
)
from app.education_intelligence.validators.rubric_policy_safety import (
    BiasFairnessSafetyValidator,
    InstitutionOverrideBoundaryValidator,
    PolicyPrecedenceValidator,
    RubricIntegrityValidator,
)
from app.education_intelligence.validators.taxonomy import (
    CognitiveTaxonomyValidator,
    CompetencyTaxonomyValidator,
)


@dataclass
class ValidatorRegistry:
    validators: dict[str, ItemValidator] = field(default_factory=dict)

    def register(self, validator: ItemValidator) -> None:
        self.validators[validator.validator_id] = validator

    def get(self, validator_id: str) -> ItemValidator | None:
        return self.validators.get(validator_id)

    def all_ids(self) -> list[str]:
        return sorted(self.validators.keys())


def build_default_registry() -> ValidatorRegistry:
    reg = ValidatorRegistry()
    for validator in (
        CognitiveTaxonomyValidator(),
        CompetencyTaxonomyValidator(),
        LearningOutcomeValidator(),
        SourceBackedCompetencyValidator(),
        CognitiveDemandEvidenceValidator(),
        TargetObservedCognitiveValidator(),
        CognitiveProgressionValidator(),
        DifficultyValidator(),
        AgeGradeAppropriatenessValidator(),
        StructuralClarityValidator(),
        EducationalQualityRulePackValidator(),
        RubricIntegrityValidator(),
        PolicyPrecedenceValidator(),
        InstitutionOverrideBoundaryValidator(),
        BiasFairnessSafetyValidator(),
    ):
        reg.register(validator)
    return reg
