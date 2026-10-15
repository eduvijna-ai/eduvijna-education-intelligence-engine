from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.adapters.anythingllm.protocol import AnythingLLMAdapter
from app.education_intelligence.fixtures import seed_cbse_fixture_curriculum
from app.knowledge_intelligence.fixtures import seed_knowledge_fixtures
from app.knowledge_intelligence.indexing import index_source_revision
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION
from app.models.curriculum import CurriculumVersion
from app.models.source import SourceRevision
from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.factory import build_orchestration_service
from app.orchestration.gateway.protocol import GenerationGateway
from app.orchestration.service import OrchestrationService


def seed_day8_fixtures(
    session: Session, *, adapter: AnythingLLMAdapter | None = None
) -> dict[str, str]:
    curriculum = seed_cbse_fixture_curriculum(session)
    knowledge = seed_knowledge_fixtures(session)
    session.flush()
    curriculum_version = session.get(CurriculumVersion, curriculum["curriculum_version_id"])
    official_revision = session.get(SourceRevision, knowledge.official_revision_id)
    if curriculum_version is not None and official_revision is not None:
        official_revision.curriculum_versions.append(curriculum_version)
        official_revision.metadata_json = {
            **official_revision.metadata_json,
            "grade_year_code": "grade-8",
            "medium_code": "english",
            "subject_code": "mathematics",
        }
    ki_adapter = adapter or FakeAnythingLLMAdapter()
    index_source_revision(
        session,
        ki_adapter,
        knowledge.official_revision_id,
        retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
    )
    session.commit()
    return {
        "curriculum_version_id": curriculum["curriculum_version_id"],
        "learning_outcome_id": curriculum["learning_outcome_id"],
        "organization_id": knowledge.organization_id,
        "institution_id": knowledge.institution_id,
        "official_revision_id": knowledge.official_revision_id,
    }


def build_diagnostic_orchestration_request(
    ctx: dict[str, str],
    *,
    scenario: str = "clean_pass",
    diagnostic_scenario: str = "diagnostic_clean_pass",
    idempotency_key: str = "day9-fixture-key-001",
    requested_count: int = 1,
    max_repairs: int = 2,
    diagnostic_blocked_tenant_revision_ids: list[str] | None = None,
    diagnostic_foreign_revision_id: str | None = None,
    diagnostic_taxonomy_version: str | None = None,
) -> OrchestrationRequest:
    request = build_orchestration_request(
        ctx,
        scenario=scenario,
        idempotency_key=idempotency_key,
        requested_count=requested_count,
        max_repairs=max_repairs,
    )
    metadata = {
        **request.metadata_json,
        "diagnostic_enrichment_enabled": True,
        "diagnostic_fixture_scenario": diagnostic_scenario,
    }
    if requested_count >= 2:
        metadata["diagnostic_fixture_by_slot"] = {
            "0": "diagnostic_clean_pass",
            "1": "diagnostic_repair_then_pass",
        }
    if diagnostic_blocked_tenant_revision_ids:
        metadata["diagnostic_blocked_tenant_revision_ids"] = list(
            diagnostic_blocked_tenant_revision_ids
        )
    if diagnostic_foreign_revision_id:
        metadata["diagnostic_foreign_revision_id"] = diagnostic_foreign_revision_id
    if diagnostic_taxonomy_version:
        metadata["diagnostic_taxonomy_version"] = diagnostic_taxonomy_version
    return request.model_copy(
        update={
            "requested_count": requested_count,
            "metadata_json": metadata,
        }
    )


def build_orchestration_request(
    ctx: dict[str, str],
    *,
    scenario: str = "clean_pass",
    idempotency_key: str = "day8-fixture-key-001",
    requested_count: int = 1,
    max_repairs: int = 2,
) -> OrchestrationRequest:
    return OrchestrationRequest(
        idempotency_key=idempotency_key,
        requested_count=requested_count,
        curriculum_version_id=ctx["curriculum_version_id"],
        grade_year_code="grade-8",
        medium_code="english",
        subject_code="mathematics",
        retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        retrieval_query="quadratic equations completing square",
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        marks=1.0,
        max_repairs=max_repairs,
        metadata_json={
            "fixture_scenario": scenario,
            "learning_outcome_ids": [ctx["learning_outcome_id"]],
        },
    )


def build_day8_test_service(
    session: Session,
    *,
    gateway: GenerationGateway | None = None,
    memory_checkpointer: bool = True,
    force_fake: bool = True,
) -> tuple[dict[str, str], OrchestrationService]:
    """Seed fixtures and return a service sharing the same in-memory KI adapter."""
    ki_adapter = FakeAnythingLLMAdapter()
    ctx = seed_day8_fixtures(session, adapter=ki_adapter)
    service = build_orchestration_service(
        session,
        gateway=gateway,
        knowledge_adapter=ki_adapter,
        memory_checkpointer=memory_checkpointer,
        force_fake=force_fake,
    )
    return ctx, service
