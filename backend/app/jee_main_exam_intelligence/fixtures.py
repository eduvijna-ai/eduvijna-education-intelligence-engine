from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.jee_main_exam_intelligence.constants import (
    DERIVED_TOPIC_ALGEBRA,
    JEE_MAIN_VERSION_2027,
)
from app.jee_main_exam_intelligence.contracts import PaperPlanRequest
from app.jee_main_exam_intelligence.enums import JeeMainSubjectCode, PaperPlanMode
from app.jee_main_exam_intelligence.exam_catalogue import ensure_jee_main_exam_catalogue
from app.jee_main_exam_intelligence.question_pool import seed_synthetic_question_pool
from app.jee_main_exam_intelligence.source_authority import (
    link_approved_revisions_to_exam_version,
    register_nta_2027_candidate_sources,
)
from app.knowledge_intelligence.fixtures import seed_knowledge_fixtures
from app.models.enums import SourceIngestionMethod
from app.models.examination import ExamVersion
from app.models.source import Source
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage


def seed_day11_fixture_context(session: Session) -> dict[str, Any]:
    knowledge = seed_knowledge_fixtures(session)
    register_nta_2027_candidate_sources(session)
    catalogue = ensure_jee_main_exam_catalogue(session)
    pool = seed_synthetic_question_pool(
        session,
        organization_id=knowledge.organization_id,
        institution_id=knowledge.institution_id,
    )
    session.flush()
    return {
        "organization_id": knowledge.organization_id,
        "institution_id": knowledge.institution_id,
        "exam_pack_id": catalogue["exam_pack_id"],
        "exam_version_2027_id": catalogue["versions"][JEE_MAIN_VERSION_2027],
        **pool,
    }


def build_practice_math_ten_request(ctx: dict[str, Any]) -> PaperPlanRequest:
    return PaperPlanRequest(
        plan_id="practice-math-10",
        exam_version_code=JEE_MAIN_VERSION_2027,
        mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        subject_code=JeeMainSubjectCode.MATHEMATICS,
        requested_count=10,
        idempotency_key="d11-practice-math-10",
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
    )


def build_practice_algebra_ten_request(ctx: dict[str, Any]) -> PaperPlanRequest:
    return PaperPlanRequest(
        plan_id="practice-algebra-10",
        exam_version_code=JEE_MAIN_VERSION_2027,
        mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        subject_code=JeeMainSubjectCode.MATHEMATICS,
        derived_topic_group=DERIVED_TOPIC_ALGEBRA,
        requested_count=10,
        idempotency_key="d11-practice-algebra-10",
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
    )


def synthetic_activate_nta_sources_for_harness(
    session: Session,
    *,
    exam_version_id: str,
    storage_root: Path | None = None,
) -> list[str]:
    """Synthetic-only: approve minimal JSON stand-ins; not a claim of independent NTA PDF review."""
    storage = LocalSourceStorage(storage_root or Path("/tmp/day11-nta-synthetic-store"))
    service = SourceIntelligenceService(session, storage=storage)
    revision_ids: list[str] = []
    source_ids = list(register_nta_2027_candidate_sources(session).values())
    for source_id in source_ids:
        source = session.get(Source, source_id)
        if source is None:
            continue
        meta = {
            "document_type": "nta_official_candidate_metadata",
            "locator": source.url or "synthetic",
            "synthetic_nta_harness": True,
            "disclaimer": "Synthetic activation for deterministic Day11 tests only.",
        }
        import json

        content = json.dumps(meta, sort_keys=True, separators=(",", ":")).encode()
        revision = service.ingest_upload(
            source.id,
            method=SourceIngestionMethod.JSON,
            content=content,
            filename="nta-candidate-metadata.json",
            actor_id="day11-synthetic-curator",
        )
        service.extract_revision(revision.id, actor_id="day11-synthetic-curator")
        service.create_diff(revision.id, actor_id="day11-synthetic-curator")
        result = service.validate_revision(revision.id, actor_id="day11-synthetic-curator")
        if not result.valid:
            raise AssertionError(f"NTA synthetic validation failed: {result.errors}")
        service.approve_revision(revision.id, actor_id="founder-day11-synthetic")
        service.activate_revision(revision.id, actor_id="founder-day11-synthetic")
        revision.metadata_json = {
            **(revision.metadata_json or {}),
            "synthetic_nta_harness": True,
        }
        session.flush()
        revision_ids.append(revision.id)
    exam_version = session.get(ExamVersion, exam_version_id)
    if exam_version is not None:
        link_approved_revisions_to_exam_version(
            session,
            exam_version=exam_version,
            revision_ids=revision_ids,
            synthetic_demonstration_only=True,
        )
    return revision_ids


def build_official_replica_request(ctx: dict[str, Any]) -> PaperPlanRequest:
    return PaperPlanRequest(
        plan_id="official-replica-75",
        exam_version_code=JEE_MAIN_VERSION_2027,
        mode=PaperPlanMode.OFFICIAL_PATTERN_REPLICA,
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        require_official_pattern_verified=True,
        idempotency_key="d11-official-replica-75",
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
    )
