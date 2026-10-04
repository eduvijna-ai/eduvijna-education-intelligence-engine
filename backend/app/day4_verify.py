from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.curriculum_intelligence.service import (
    CurriculumIntelligenceService,
    load_source_manifest,
)
from app.db.session import session_factory
from app.models.curriculum import CurriculumNode
from app.models.source import Source
from app.schemas.curriculum_intelligence import (
    AssessmentEvidenceInput,
    CompetencySpec,
    CurriculumAlignmentInput,
    CurriculumNodeSpec,
    LearningOutcomeSpec,
)
from app.schemas.source_intelligence import SourceProvenanceLinkInput

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANIFEST = REPO_ROOT / "content" / "curricula" / "day4_official_sources.json"
VERIFY_SLICE = REPO_ROOT / "content" / "curricula" / "cbse-2026-27-verification-slice.json"


def _load_slice() -> dict[str, Any]:
    payload = json.loads(VERIFY_SLICE.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Day-4 verification slice must be a JSON object")
    return payload


def seed_day4_verification(
    session: Session,
    *,
    fetch_official: bool = False,
    strict_official_fetch: bool = False,
    actor_id: str = "day4-verifier",
) -> dict[str, Any]:
    bundle = _load_slice()
    service = CurriculumIntelligenceService(session)
    revisions = service.ensure_manifest_sources(
        load_source_manifest(SOURCE_MANIFEST),
        actor_id=actor_id,
        fetch_content=fetch_official,
        fallback_on_fetch_error=not strict_official_fetch,
        request_id="day4-verification",
    )

    framework_data = bundle["framework"]
    framework_revision = revisions[framework_data["source_key"]]
    framework = service.ensure_framework(
        code=framework_data["code"],
        name=framework_data["name"],
        country="India",
        authority=framework_data["authority"],
        version_code=framework_data["version_code"],
        revision=framework_revision,
        source_locator=framework_data.get("source_locator"),
    )

    curriculum_data = bundle["curriculum"]
    curriculum_revision = revisions[curriculum_data["source_key"]]
    pack = service.ensure_pack(
        framework=framework,
        code=curriculum_data["code"],
        name=curriculum_data["name"],
        authority=curriculum_data["authority"],
        country="India",
        revision=curriculum_revision,
        source_locator=curriculum_data.get("source_locator"),
        metadata_json={"versioned": True},
    )
    version = service.ensure_version(
        pack=pack,
        version_code=curriculum_data["version_code"],
        academic_year=curriculum_data["academic_year"],
        revision=curriculum_revision,
        source_locator=curriculum_data.get("source_locator"),
        metadata_json={
            "scope": "Classes IX-XII",
            "verification_slice": True,
            "fixture_kind": bundle["fixture_kind"],
        },
    )

    # Preserve the complete set of exact SourceRevision evidence at version level.
    for revision in revisions.values():
        service.source_service.link_provenance(
            SourceProvenanceLinkInput(
                revision_id=revision.id,
                curriculum_version_id=version.id,
            ),
            actor_id=actor_id,
            request_id="day4-verification",
        )

    competencies: dict[str, Any] = {}
    for raw in bundle["competencies"]:
        source_key = raw["source_key"]
        spec = CompetencySpec.model_validate(
            {key: value for key, value in raw.items() if key != "source_key"}
        )
        result = service.upsert_competencies(
            framework=framework,
            specs=[spec],
            revision=revisions[source_key],
        )
        competencies.update(result)

    outcomes: dict[str, Any] = {}
    for raw in bundle["learning_outcomes"]:
        source_key = raw["source_key"]
        spec = LearningOutcomeSpec.model_validate(
            {key: value for key, value in raw.items() if key != "source_key"}
        )
        result = service.upsert_learning_outcomes(
            version=version,
            specs=[spec],
            revision=revisions[source_key],
        )
        outcomes.update(result)

    nodes: dict[str, CurriculumNode] = {}
    # One node at a time intentionally permits different exact SourceRevisions
    # while parent lookup remains within the canonical curriculum version.
    for raw in bundle["nodes"]:
        source_key = raw["source_key"]
        spec = CurriculumNodeSpec.model_validate(
            {key: value for key, value in raw.items() if key != "source_key"}
        )
        result = service.upsert_nodes(
            version=version,
            specs=[spec],
            revision=revisions[source_key],
        )
        nodes.update(result)

    alignments: list[Any] = []
    for raw in bundle["alignments"]:
        node = nodes[raw["node_code"]]
        kwargs: dict[str, Any] = {
            "curriculum_version_id": version.id,
            "curriculum_node_id": node.id,
            "relationship_type": raw["relationship_type"],
            "status": raw["status"],
            "confidence": raw.get("confidence"),
            "inferred": raw.get("inferred", False),
            "source_revision_id": revisions[raw["source_key"]].id,
            "source_locator": raw.get("source_locator"),
            "evidence_text": raw.get("evidence_text"),
            "metadata_json": {"verification_slice": True},
        }
        if raw["target_kind"] == "learning_outcome":
            kwargs["learning_outcome_id"] = outcomes[raw["target_code"]].id
        elif raw["target_kind"] == "competency":
            kwargs["competency_id"] = competencies[raw["target_code"]].id
        else:
            raise ValueError(f"unsupported alignment target: {raw['target_kind']}")
        alignments.append(service.align(CurriculumAlignmentInput.model_validate(kwargs)))

    assessment: list[Any] = []
    for raw in bundle["assessment_evidence"]:
        assessment.append(
            service.add_assessment_evidence(
                AssessmentEvidenceInput(
                    curriculum_version_id=version.id,
                    grade_node_id=nodes[raw["grade_code"]].id,
                    subject_node_id=nodes[raw["subject_code"]].id,
                    evidence_type=raw["evidence_type"],
                    source_revision_id=revisions[raw["source_key"]].id,
                    source_locator=raw.get("source_locator"),
                    evidence_json=raw.get("evidence_json", {}),
                    metadata_json=raw.get("metadata_json", {}),
                )
            )
        )

    session.commit()

    concept = nodes["grade-ix-math-classifying-real-numbers"]
    path = service.hierarchy_path(concept.id)
    coverage = service.coverage(version.id)
    counts = service.entity_counts(version.id)

    source_inventory: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for key, revision in revisions.items():
        source = session.get(Source, revision.source_id)
        assert source is not None
        item = {
            "key": key,
            "source_id": source.id,
            "source_revision_id": revision.id,
            "authority": source.authority,
            "url": source.url,
            "revision_status": revision.status,
            "checksum": revision.checksum,
            "ingestion_method": revision.ingestion_method,
            "registry_only": bool(
                revision.metadata_json.get("manual_metadata", {}).get("registry_only")
                if isinstance(revision.metadata_json.get("manual_metadata"), dict)
                else False
            ),
        }
        source_inventory.append(item)
        if source.metadata_json.get("ingestion_status") == "blocked_or_unavailable":
            blocked.append(
                {
                    "key": key,
                    "url": source.url,
                    "reason": source.metadata_json.get("ingestion_error"),
                }
            )

    assessment_row = assessment[0]
    subject = session.get(CurriculumNode, assessment_row.subject_node_id)
    assert subject is not None

    return {
        "day": 4,
        "status": "verification_passed",
        "mode": "official_fetch" if fetch_official else "deterministic_registry_fixture",
        "framework": {
            "id": framework.id,
            "code": framework.code,
            "version_code": framework.version_code,
            "provenance": service.provenance(
                entity_type="framework",
                entity_id=framework.id,
            ),
        },
        "curriculum": {
            "pack_id": pack.id,
            "version_id": version.id,
            "version_code": version.version_code,
            "academic_year": version.academic_year,
            "counts": counts,
            "coverage": coverage.model_dump(),
        },
        "founder_path": [
            {
                "id": node.id,
                "type": node.node_type,
                "code": node.code,
                "title": node.title,
                "source_revision_id": node.source_revision_id,
                "source_locator": node.source_locator,
            }
            for node in path
        ],
        "learning_outcome": {
            "id": outcomes["ncert-math-ix-real-numbers-logic"].id,
            "code": "ncert-math-ix-real-numbers-logic",
            "source_revision_id": outcomes[
                "ncert-math-ix-real-numbers-logic"
            ].source_revision_id,
        },
        "competency": {
            "id": competencies["math-logical-reasoning"].id,
            "code": "math-logical-reasoning",
            "source_revision_id": competencies["math-logical-reasoning"].source_revision_id,
        },
        "alignments": [
            {
                "id": row.id,
                "status": row.status,
                "inferred": row.inferred,
                "source_revision_id": row.source_revision_id,
            }
            for row in alignments
        ],
        "assessment_evidence": {
            "id": assessment_row.id,
            "subject": subject.title,
            "evidence_type": assessment_row.evidence_type,
            "source_revision_id": assessment_row.source_revision_id,
            "source_locator": assessment_row.source_locator,
            "curriculum_membership_effect": assessment_row.evidence_json.get(
                "curriculum_membership_effect"
            ),
        },
        "sources": source_inventory,
        "blocked_sources": blocked,
        "fixture_disclaimer": bundle["completeness"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Eduvijna Day-4 curriculum intelligence")
    parser.add_argument(
        "--fetch-official",
        action="store_true",
        help="retrieve official URLs through the Day-3 source lifecycle",
    )
    parser.add_argument(
        "--strict-official-fetch",
        action="store_true",
        help="fail instead of recording registry-only fallback when an official URL is blocked",
    )
    args = parser.parse_args()

    session = session_factory()()
    try:
        result = seed_day4_verification(
            session,
            fetch_official=args.fetch_official,
            strict_official_fetch=args.strict_official_fetch,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
    finally:
        session.close()


if __name__ == "__main__":
    main()
