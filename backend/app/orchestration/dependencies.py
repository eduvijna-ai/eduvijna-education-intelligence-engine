from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.education_intelligence.service import EducationIntelligenceValidationService
from app.knowledge_intelligence.service import KnowledgeIntelligenceService
from app.orchestration.gateway.protocol import GenerationGateway


@dataclass(slots=True)
class OrchestrationDependencies:
    session: Session
    control_session: Session
    knowledge_service: KnowledgeIntelligenceService
    education_service: EducationIntelligenceValidationService
    gateway: GenerationGateway
