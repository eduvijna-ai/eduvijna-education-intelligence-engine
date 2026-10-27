from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.education_intelligence.fixtures import positive_cbse_item, seed_cbse_fixture_curriculum
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.models.education_intelligence import PolicyRegistryEntry, ValidationAuditRun
from app.models.enums import SourceTrustTier, SourceType
from app.paper_distribution.contracts import (
    DistributionTarget,
    PaperDistributionRequest,
    PaperItemInput,
)
from app.paper_distribution.enums import PaperDistributionVerdict
from app.paper_distribution.evaluator import (
    evaluate_paper_distribution,
    evaluate_paper_distribution_with_session,
    reconcile_exact_counts,
)
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    PAPER_TARGET_REGISTRY_KEY,
    ensure_paper_target_policy_configured,
)
from app.paper_distribution.trusted_validation import (
    PaperDay6ItemBinding,
    PaperDay6TrustContext,
)
from app.prerequisite_intelligence.authority import (
    RevisionAuthorityRecord,
    revision_permits_official_authority,
)
from app.prerequisite_intelligence.contracts import (
    PrerequisiteGraphEdge,
    PrerequisiteGraphPath,
    PrerequisiteGraphScope,
    PrerequisiteGraphSnapshot,
)
from app.prerequisite_intelligence.enums import EdgeProvenanceClass, GraphLifecycleStatus
from app.root_cause_intelligence.contracts import RootCauseHypothesis
from app.root_cause_intelligence.ranking import project_hypothesis_authorized_paths


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'd10-r10.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _persist_day6_item(
    session: Session, ctx: dict, item_id: str
) -> tuple[str, dict]:
    item = positive_cbse_item(ctx)
    item = item.model_copy(update={"item_id": item_id})
    service = EducationIntelligenceValidationService(session)
    summary = service.validate_item(item, board_code="cbse", persist=True, actor_id="actor-1")
    session.flush()
    record = session.scalars(
        select(ValidationAuditRun).where(ValidationAuditRun.run_id == summary.run_id)
    ).first()
    assert record is not None
    validated = (record.metadata_json or {}).get("validated_items", [])[0]
    return str(record.id), validated


def _paper_item_from_validated(validated: dict) -> PaperItemInput:
    return PaperItemInput(
        item_id=str(validated["item_id"]),
        marks=1.0,
        cognitive_level=str(validated.get("declared_cognitive_level")),
        competency_codes=list(validated.get("competency_codes") or []),
        day6_validated=True,
        metadata_json={
            "day6_input_hash": validated.get("input_hash"),
            "curriculum_version_id": validated.get("curriculum_version_id"),
            "grade_year_code": validated.get("grade_year_code"),
            "medium_code": validated.get("medium_code"),
            "subject_code": validated.get("subject_code"),
            "learning_outcome_ids": list(validated.get("learning_outcome_ids") or []),
        },
    )


def test_two_item_paper_with_per_item_day6_bindings_passes(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ensure_paper_target_policy_configured(session)
    ctx = seed_cbse_fixture_curriculum(session)
    session.flush()
    run_a, validated_a = _persist_day6_item(session, ctx, f"item-{uuid4()}")
    run_b, validated_b = _persist_day6_item(session, ctx, f"item-{uuid4()}")
    session.commit()
    paper = PaperDistributionRequest(
        paper_id="two-item-paper",
        requested_count=2,
        items=[
            _paper_item_from_validated(validated_a),
            _paper_item_from_validated(validated_b),
        ],
    )
    trust = PaperDay6TrustContext.from_item_bindings(
        [
            PaperDay6ItemBinding(
                item_id=str(validated_a["item_id"]),
                validation_run_id=run_a,
            ),
            PaperDay6ItemBinding(
                item_id=str(validated_b["item_id"]),
                validation_run_id=run_b,
            ),
        ]
    )
    result = evaluate_paper_distribution_with_session(
        session,
        paper,
        day6_trust=trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(),
    )
    assert result.verdict == PaperDistributionVerdict.PASS


def test_reconcile_33_33_34_three_items_passes_percent_variance(tmp_path: Path) -> None:
    targets = [
        DistributionTarget(dimension="cognitive", key="remember", exact_percent=33.0),
        DistributionTarget(dimension="cognitive", key="understand", exact_percent=33.0),
        DistributionTarget(dimension="cognitive", key="apply", exact_percent=34.0),
    ]
    reconciled = reconcile_exact_counts(3, targets)
    assert reconciled == {"remember": 1, "understand": 1, "apply": 1}
    paper = PaperDistributionRequest(
        paper_id="thirds",
        requested_count=3,
        cognitive_targets=targets,
        items=[
            PaperItemInput(
                item_id="q1",
                marks=1.0,
                cognitive_level="remember",
                competency_codes=["knowledge"],
                day6_validated=True,
            ),
            PaperItemInput(
                item_id="q2",
                marks=1.0,
                cognitive_level="understand",
                competency_codes=["knowledge"],
                day6_validated=True,
            ),
            PaperItemInput(
                item_id="q3",
                marks=1.0,
                cognitive_level="apply",
                competency_codes=["knowledge"],
                day6_validated=True,
            ),
        ],
    )
    result = evaluate_paper_distribution(
        paper,
        day6_trust=PaperDay6TrustContext.synthetic_fixture_harness(),
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
    )
    assert PaperDistributionVerdict.PASS == result.verdict


def test_project_hypothesis_keeps_only_authorized_path() -> None:
    edge_a = PrerequisiteGraphEdge(
        edge_id="e-a",
        prerequisite_concept_id="c1",
        target_concept_id="c2",
        provenance_class=EdgeProvenanceClass.INFERRED,
        source_revision_id="rev-a",
    )
    edge_b = PrerequisiteGraphEdge(
        edge_id="e-b",
        prerequisite_concept_id="c0",
        target_concept_id="c2",
        provenance_class=EdgeProvenanceClass.INFERRED,
        source_revision_id="rev-b",
    )
    snapshot = PrerequisiteGraphSnapshot.model_construct(
        snapshot_id="snap",
        scope=PrerequisiteGraphScope(curriculum_version_id="cv-1"),
        checksum="abc",
        graph_version="v1",
        lifecycle_status=GraphLifecycleStatus.ACTIVE,
        assembled_at="2026-01-01T00:00:00Z",
        nodes=[],
        edges=[edge_a, edge_b],
    )
    hypothesis = RootCauseHypothesis(
        hypothesis_id="h1",
        rank=1,
        concept_id="c1",
        concept_code="concept-a",
        support_score=1.0,
        paths=[
            PrerequisiteGraphPath.model_construct(
                path_id="p-a",
                concept_ids=["c1", "c2"],
                edge_ids=["e-a"],
                depth=1,
                total_weight=1.0,
            ),
            PrerequisiteGraphPath.model_construct(
                path_id="p-b",
                concept_ids=["c0", "c2"],
                edge_ids=["e-b"],
                depth=1,
                total_weight=1.0,
            ),
        ],
        evidence_revision_ids=["rev-a", "rev-b"],
        alternatives=[],
    )
    projected = project_hypothesis_authorized_paths(
        snapshot,
        hypothesis,
        {"rev-a"},
        [],
    )
    assert projected is not None
    assert len(projected.paths) == 1
    assert projected.evidence_revision_ids == ["rev-a"]


def test_sample_paper_analytical_trust_tier_not_official() -> None:
    record = RevisionAuthorityRecord(
        revision_id="rev-1",
        status="active",
        source_id="src-1",
        source_status="active",
        source_type=SourceType.SAMPLE_PAPER.value,
        trust_tier=SourceTrustTier.ANALYTICAL.value,
        organization_id=None,
        institution_id=None,
        teacher_id=None,
        bound_curriculum_version_ids=set(),
        metadata_json={},
    )
    assert not revision_permits_official_authority(record)


def test_mandatory_range_overlays_weaker_request(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ensure_paper_target_policy_configured(session)
    row = session.scalar(
        select(PolicyRegistryEntry).where(
            PolicyRegistryEntry.registry_key == PAPER_TARGET_REGISTRY_KEY,
            PolicyRegistryEntry.version == PAPER_TARGET_POLICY_VERSION,
        )
    )
    assert row is not None
    row.payload_json = {
        **(row.payload_json or {}),
        "mandatory_cognitive_ranges": [
            {"key": "remember", "min_percent": 40.0, "max_percent": 60.0},
        ],
    }
    session.flush()
    request = PaperDistributionRequest(
        paper_id="range-overlay",
        cognitive_targets=[
            DistributionTarget(
                dimension="cognitive",
                key="remember",
                min_percent=10.0,
                max_percent=30.0,
            )
        ],
        items=[],
    )
    from app.paper_distribution.target_policy_registry import paper_targets_authorized

    ok, path = paper_targets_authorized(session, request, version=PAPER_TARGET_POLICY_VERSION)
    assert ok is False
    assert path is not None and "range" in path
