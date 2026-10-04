from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import func, select
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
from app.models.enums import (
    CurriculumNodeType,
    CurriculumStatus,
    SourceRevisionStatus,
)
from app.models.source import Source, SourceRevision
from app.schemas.curriculum_intelligence import (
    AssessmentEvidenceInput,
    CompetencySpec,
    CoverageSummary,
    CurriculumAlignmentInput,
    CurriculumNodeSpec,
    CurriculumPathResult,
    LearningOutcomeSpec,
    OfficialSourceManifestEntry,
)
from app.schemas.source_intelligence import (
    ManualSourceRevisionInput,
    SourceRegistrationInput,
)
from app.source_intelligence.extractors import SourceExtractionError
from app.source_intelligence.security import SourceFetchError
from app.source_intelligence.service import SourceIntelligenceService

DAY4_NAMESPACE = UUID("9d8e89be-1342-4cb7-8c2b-895399afca30")

_PARENT_TYPE: dict[str, str | None] = {
    CurriculumNodeType.GRADE_YEAR.value: None,
    CurriculumNodeType.MEDIUM.value: CurriculumNodeType.GRADE_YEAR.value,
    CurriculumNodeType.SUBJECT.value: CurriculumNodeType.MEDIUM.value,
    CurriculumNodeType.UNIT.value: CurriculumNodeType.SUBJECT.value,
    CurriculumNodeType.CHAPTER.value: CurriculumNodeType.UNIT.value,
    CurriculumNodeType.TOPIC.value: CurriculumNodeType.CHAPTER.value,
    CurriculumNodeType.CONCEPT.value: CurriculumNodeType.TOPIC.value,
}

_ALIGNMENT_STATUSES = {"direct", "partial", "unresolved", "review_required"}


class CurriculumIntelligenceError(ValueError):
    pass


def stable_uuid(*parts: object) -> str:
    key = "|".join(str(part).strip().lower() for part in parts)
    return str(uuid5(DAY4_NAMESPACE, key))


def load_source_manifest(path: Path) -> list[OfficialSourceManifestEntry]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise CurriculumIntelligenceError("source manifest must be a JSON list")
    return [OfficialSourceManifestEntry.model_validate(item) for item in raw]


class CurriculumIntelligenceService:
    def __init__(
        self,
        session: Session,
        *,
        source_service: SourceIntelligenceService | None = None,
    ) -> None:
        self.session = session
        self.source_service = source_service or SourceIntelligenceService(session)

    @staticmethod
    def _require_revision(revision: SourceRevision) -> None:
        if revision.status != SourceRevisionStatus.ACTIVE.value:
            raise CurriculumIntelligenceError(
                "new curriculum writes require an active SourceRevision; history is read-only"
            )

    @staticmethod
    def _source_metadata(revision: SourceRevision) -> dict[str, Any]:
        snapshot = revision.metadata_json.get("source_snapshot", {})
        metadata = snapshot.get("metadata_json", {}) if isinstance(snapshot, dict) else {}
        return dict(metadata) if isinstance(metadata, dict) else {}

    @classmethod
    def _is_assessment_source(cls, revision: SourceRevision) -> bool:
        metadata = cls._source_metadata(revision)
        snapshot = revision.metadata_json.get("source_snapshot", {})
        return metadata.get("document_type") in {
            "assessment_evidence",
            "sample_paper_index",
            "sample_question_paper",
            "marking_scheme",
        } or snapshot.get("source_type") in {
            "sample_paper",
            "marking_scheme",
            "official_paper",
            "answer_key",
        }

    @classmethod
    def _require_curriculum_revision(cls, revision: SourceRevision) -> None:
        """One domain policy for every curriculum semantic creation/update."""
        cls._require_revision(revision)
        if cls._is_assessment_source(revision):
            raise CurriculumIntelligenceError(
                "assessment sources cannot establish syllabus membership "
                "or curriculum alignment/semantics"
            )

    @staticmethod
    def _assert_source_binding(
        entity: Any,
        revision: SourceRevision,
        *,
        allow_source_rebind: bool = False,
    ) -> None:
        current = getattr(entity, "source_revision_id", None)
        if current is None or current == revision.id:
            return
        if not allow_source_rebind:
            raise CurriculumIntelligenceError(
                "active curriculum evidence cannot silently rebind to a different "
                "SourceRevision; create a new version or perform an explicit reviewed rebind"
            )

    @staticmethod
    def is_registry_only(revision: SourceRevision) -> bool:
        metadata = revision.metadata_json.get("manual_metadata", {})
        return isinstance(metadata, dict) and bool(metadata.get("registry_only"))

    @staticmethod
    def has_source_content(revision: SourceRevision) -> bool:
        return (
            revision.ingestion_method != "manual"
            and revision.extraction_status == "succeeded"
            and revision.extracted_checksum == revision.checksum
            and bool(revision.extracted_text)
        )

    def ensure_manifest_sources(
        self,
        entries: Iterable[OfficialSourceManifestEntry],
        *,
        actor_id: str,
        fetch_content: bool = False,
        fallback_on_fetch_error: bool = True,
        request_id: str | None = None,
    ) -> dict[str, SourceRevision]:
        """Register official sources and return exact active revisions.

        fetch_content=True uses the Day-3 URL ingestion path. When False, a
        metadata-only manual revision is used for deterministic development and
        tests. The metadata revision is explicitly marked registry_only and must
        never be treated as extracted curriculum text.
        """

        resolved: dict[str, SourceRevision] = {}
        for entry in entries:
            source = self.session.scalar(
                select(Source).where(
                    Source.url == entry.url,
                    Source.source_type == entry.source_type.value,
                )
            )
            if source is None:
                source = self.source_service.register_source(
                    SourceRegistrationInput(
                        source_type=entry.source_type,
                        title=entry.title,
                        url=entry.url,
                        authority=entry.authority,
                        country=entry.country,
                        board_or_exam=entry.board_or_exam,
                        academic_year=entry.academic_year,
                        copyright_classification=entry.copyright_classification,
                        trust_tier=entry.trust_tier,
                        metadata_json={
                            **entry.metadata_json,
                            "manifest_key": entry.key,
                            "document_type": entry.document_type,
                            "version_applicability": entry.version_applicability,
                        },
                    ),
                    actor_id=actor_id,
                    request_id=request_id,
                )

            active = self.session.scalar(
                select(SourceRevision)
                .where(
                    SourceRevision.source_id == source.id,
                    SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
                )
                .order_by(SourceRevision.revision_number.desc())
                .execution_options(populate_existing=True)
            )
            if active is not None and not fetch_content:
                resolved[entry.key] = active
                continue

            if fetch_content:
                # Retrieval diagnostics must not linger after a successful retry or
                # poison the next snapshot identity with a stale blocked status.
                if source.metadata_json.get("ingestion_status") == "blocked_or_unavailable":
                    source.metadata_json = {
                        key: value
                        for key, value in source.metadata_json.items()
                        if key not in {"ingestion_status", "ingestion_error", "fallback"}
                    }
                    self.session.commit()
                try:
                    revision = self.source_service.ingest_url(
                        source.id,
                        actor_id=actor_id,
                        request_id=request_id,
                    )
                    if revision.status == SourceRevisionStatus.STAGED.value:
                        revision = self.source_service.extract_revision(
                            revision.id,
                            actor_id=actor_id,
                            request_id=request_id,
                        )
                except (SourceFetchError, SourceExtractionError, OSError) as exc:
                    if not fallback_on_fetch_error:
                        raise
                    source.metadata_json = {
                        **dict(source.metadata_json or {}),
                        "ingestion_status": "blocked_or_unavailable",
                        "ingestion_error": str(exc)[:500],
                        "fallback": "manual_registry_only",
                    }
                    self.session.commit()
                    if active is not None:
                        resolved[entry.key] = active
                        continue
                    revision = self.source_service.ingest_manual(
                        source.id,
                        ManualSourceRevisionInput(
                            metadata={
                                "manifest_key": entry.key,
                                "registry_only": True,
                                "official_url": entry.url,
                                "document_type": entry.document_type,
                                "version_applicability": entry.version_applicability,
                                "blocked_reason": str(exc)[:500],
                            },
                            note=(
                                "Official retrieval blocked/unavailable; registry-only "
                                "fallback, not curriculum text"
                            ),
                        ),
                        actor_id=actor_id,
                        request_id=request_id,
                    )
            else:
                revision = self.source_service.ingest_manual(
                    source.id,
                    ManualSourceRevisionInput(
                        metadata={
                            "manifest_key": entry.key,
                            "registry_only": True,
                            "official_url": entry.url,
                            "document_type": entry.document_type,
                            "version_applicability": entry.version_applicability,
                        },
                        note="Day-4 registry-only fixture; not curriculum text",
                    ),
                    actor_id=actor_id,
                    request_id=request_id,
                )

            if revision.status == SourceRevisionStatus.ACTIVE.value:
                resolved[entry.key] = revision
                continue
            if revision.status == SourceRevisionStatus.SUPERSEDED.value:
                current = self.session.scalar(
                    select(SourceRevision).where(
                        SourceRevision.source_id == source.id,
                        SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
                    )
                )
                if current is None:
                    raise CurriculumIntelligenceError(f"source {entry.key} has no active revision")
                resolved[entry.key] = current
                continue

            if revision.status == SourceRevisionStatus.STAGED.value:
                revision = self.source_service.extract_revision(
                    revision.id,
                    actor_id=actor_id,
                    request_id=request_id,
                )

            if revision.status == SourceRevisionStatus.EXTRACTED.value:
                self.source_service.create_diff(
                    revision.id,
                    actor_id=actor_id,
                    request_id=request_id,
                )
                # A changed content revision must go through explicit human review.
                # Registry metadata is not a previously approved content version.
                if active is not None and not self.is_registry_only(active):
                    raise CurriculumIntelligenceError(
                        f"source {entry.key} changed; candidate {revision.id} requires "
                        "explicit review; the prior active revision is preserved"
                    )
                validation = self.source_service.validate_revision(
                    revision.id,
                    actor_id=actor_id,
                    request_id=request_id,
                )
                if not validation.valid:
                    raise CurriculumIntelligenceError(
                        f"source validation failed for {entry.key}: " + "; ".join(validation.errors)
                    )
                self.source_service.approve_revision(
                    revision.id,
                    actor_id=actor_id,
                    request_id=request_id,
                )
                revision = self.source_service.activate_revision(
                    revision.id,
                    actor_id=actor_id,
                    request_id=request_id,
                )
            self._require_revision(revision)
            resolved[entry.key] = revision
        return resolved

    def ensure_framework(
        self,
        *,
        code: str,
        name: str,
        country: str,
        authority: str,
        version_code: str,
        revision: SourceRevision,
        source_locator: str | None = None,
        description: str | None = None,
    ) -> EducationFramework:
        self._require_curriculum_revision(revision)
        framework = self.session.scalar(
            select(EducationFramework).where(EducationFramework.code == code)
        )
        if framework is None:
            framework = EducationFramework(
                id=stable_uuid("framework", code),
                code=code,
                name=name,
                country=country,
            )
            self.session.add(framework)
        self._assert_source_binding(framework, revision)
        framework.name = name
        framework.country = country
        framework.authority = authority
        framework.version_code = version_code
        framework.description = description
        framework.source_revision_id = revision.id
        framework.source_locator = source_locator
        framework.active = True
        self.session.flush()
        return framework

    def ensure_pack(
        self,
        *,
        framework: EducationFramework,
        code: str,
        name: str,
        authority: str,
        country: str,
        revision: SourceRevision,
        source_locator: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> CurriculumPack:
        self._require_curriculum_revision(revision)
        pack = self.session.scalar(select(CurriculumPack).where(CurriculumPack.code == code))
        if pack is None:
            pack = CurriculumPack(
                id=stable_uuid("curriculum-pack", code),
                code=code,
                name=name,
                country=country,
            )
            self.session.add(pack)
        self._assert_source_binding(pack, revision)
        pack.framework_id = framework.id
        pack.name = name
        pack.authority = authority
        pack.country = country
        pack.source_revision_id = revision.id
        pack.source_locator = source_locator
        pack.active = True
        pack.metadata_json = dict(metadata_json or {})
        self.session.flush()
        return pack

    def ensure_version(
        self,
        *,
        pack: CurriculumPack,
        version_code: str,
        academic_year: str | None,
        revision: SourceRevision,
        source_locator: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        active: bool = True,
    ) -> CurriculumVersion:
        self._require_curriculum_revision(revision)
        version = self.session.scalar(
            select(CurriculumVersion).where(
                CurriculumVersion.curriculum_pack_id == pack.id,
                CurriculumVersion.version_code == version_code,
            )
        )
        if version is None:
            version = CurriculumVersion(
                id=stable_uuid("curriculum-version", pack.code, version_code),
                curriculum_pack_id=pack.id,
                version_code=version_code,
            )
            self.session.add(version)
        self._assert_source_binding(version, revision)
        version.academic_year = academic_year
        version.source_revision_id = revision.id
        version.source_locator = source_locator
        version.metadata_json = dict(metadata_json or {})
        version.status = CurriculumStatus.ACTIVE.value if active else CurriculumStatus.DRAFT.value
        self.session.flush()
        return version

    def supersede_version(
        self,
        version: CurriculumVersion,
        *,
        replacement: CurriculumVersion | None = None,
    ) -> None:
        version.status = CurriculumStatus.SUPERSEDED.value
        metadata = dict(version.metadata_json or {})
        if replacement is not None:
            metadata["superseded_by"] = replacement.id
        version.metadata_json = metadata
        self.session.flush()

    def upsert_nodes(
        self,
        *,
        version: CurriculumVersion,
        specs: Iterable[CurriculumNodeSpec],
        revision: SourceRevision,
    ) -> dict[str, CurriculumNode]:
        self._require_curriculum_revision(revision)
        if self._is_assessment_source(revision):
            raise CurriculumIntelligenceError(
                "assessment sources cannot establish syllabus membership"
            )
        specs_list = list(specs)
        codes = [item.code for item in specs_list]
        if len(codes) != len(set(codes)):
            raise CurriculumIntelligenceError(
                "Day-4 normalized bundles require unique node codes within a version"
            )

        by_code: dict[str, CurriculumNode] = {}
        unresolved = {spec.code: spec for spec in specs_list}
        while unresolved:
            progressed = False
            for code, spec in list(unresolved.items()):
                parent = by_code.get(spec.parent_code) if spec.parent_code else None
                if spec.parent_code is not None and parent is None:
                    parent = self.session.scalar(
                        select(CurriculumNode).where(
                            CurriculumNode.curriculum_version_id == version.id,
                            CurriculumNode.code == spec.parent_code,
                        )
                    )
                    if parent is None:
                        continue
                expected_parent_type = _PARENT_TYPE[spec.node_type.value]
                if expected_parent_type is None and parent is not None:
                    raise CurriculumIntelligenceError(f"{spec.node_type.value} nodes must be roots")
                if expected_parent_type is not None:
                    if parent is None:
                        raise CurriculumIntelligenceError(
                            f"{spec.node_type.value} requires parent type {expected_parent_type}"
                        )
                    if parent.node_type != expected_parent_type:
                        raise CurriculumIntelligenceError(
                            f"invalid hierarchy: {spec.node_type.value} cannot be under "
                            f"{parent.node_type}"
                        )

                parent_key = parent.id if parent is not None else "root"
                node_id = stable_uuid(
                    "curriculum-node",
                    version.id,
                    parent_key,
                    spec.node_type.value,
                    spec.code,
                )
                node = self.session.get(CurriculumNode, node_id)
                if node is None:
                    node = CurriculumNode(
                        id=node_id,
                        curriculum_version_id=version.id,
                        node_type=spec.node_type.value,
                        code=spec.code,
                        title=spec.title,
                    )
                    self.session.add(node)
                self._assert_source_binding(node, revision)
                node.parent_id = parent.id if parent is not None else None
                node.parent_version_id = version.id if parent is not None else None
                node.node_type = spec.node_type.value
                node.code = spec.code
                node.title = spec.title
                node.sequence = spec.sequence
                node.official_text = spec.official_text
                node.source_revision_id = revision.id
                node.source_locator = spec.source_locator
                node.metadata_json = dict(spec.metadata_json)
                self.session.flush()
                by_code[spec.code] = node
                del unresolved[code]
                progressed = True
            if not progressed:
                raise CurriculumIntelligenceError(
                    "curriculum hierarchy contains missing parents or a cycle: "
                    + ", ".join(sorted(unresolved))
                )
        return by_code

    def upsert_competencies(
        self,
        *,
        framework: EducationFramework,
        specs: Iterable[CompetencySpec],
        revision: SourceRevision,
    ) -> dict[str, Competency]:
        self._require_curriculum_revision(revision)
        result: dict[str, Competency] = {}
        for spec in specs:
            competency = self.session.scalar(select(Competency).where(Competency.code == spec.code))
            if competency is None:
                competency = Competency(
                    id=stable_uuid("competency", framework.code, spec.code),
                    code=spec.code,
                    name=spec.name,
                )
                self.session.add(competency)
            if competency.framework_id is not None and competency.framework_id != framework.id:
                raise CurriculumIntelligenceError("competency cannot move between frameworks")
            self._assert_source_binding(competency, revision)
            competency.framework_id = framework.id
            competency.name = spec.name
            competency.description = spec.description
            competency.official_text = spec.official_text
            competency.source_revision_id = revision.id
            competency.source_locator = spec.source_locator
            competency.metadata_json = dict(spec.metadata_json)
            competency.active = True
            self.session.flush()
            result[spec.code] = competency
        return result

    def upsert_learning_outcomes(
        self,
        *,
        version: CurriculumVersion,
        specs: Iterable[LearningOutcomeSpec],
        revision: SourceRevision,
    ) -> dict[str, LearningOutcome]:
        self._require_curriculum_revision(revision)
        result: dict[str, LearningOutcome] = {}
        for spec in specs:
            outcome = self.session.scalar(
                select(LearningOutcome).where(
                    LearningOutcome.curriculum_version_id == version.id,
                    LearningOutcome.code == spec.code,
                )
            )
            if outcome is None:
                outcome = LearningOutcome(
                    id=stable_uuid("learning-outcome", version.id, spec.code),
                    curriculum_version_id=version.id,
                    code=spec.code,
                    text=spec.text,
                )
                self.session.add(outcome)
            self._assert_source_binding(outcome, revision)
            outcome.text = spec.text
            outcome.normalized_text = spec.normalized_text
            outcome.source_revision_id = revision.id
            outcome.source_locator = spec.source_locator
            outcome.metadata_json = dict(spec.metadata_json)
            outcome.active = True
            self.session.flush()
            result[spec.code] = outcome
        return result

    def align(self, payload: CurriculumAlignmentInput) -> CurriculumAlignment:
        revision = self.session.get(SourceRevision, str(payload.source_revision_id))
        if revision is None:
            raise LookupError("alignment source revision not found")
        self._require_curriculum_revision(revision)
        if self._is_assessment_source(revision):
            raise CurriculumIntelligenceError(
                "assessment sources cannot establish curriculum alignment"
            )
        version = self.session.get(CurriculumVersion, str(payload.curriculum_version_id))
        node = self.session.get(CurriculumNode, str(payload.curriculum_node_id))
        if version is None or node is None:
            raise LookupError("alignment curriculum version/node not found")
        if node.curriculum_version_id != version.id:
            raise CurriculumIntelligenceError(
                "alignment node must belong to the supplied curriculum version"
            )
        if payload.status not in _ALIGNMENT_STATUSES:
            raise CurriculumIntelligenceError("invalid alignment status")
        if payload.learning_outcome_id is not None:
            target_kind = "learning_outcome"
            target_id = str(payload.learning_outcome_id)
            outcome = self.session.get(LearningOutcome, target_id)
            if outcome is None:
                raise LookupError("alignment learning outcome not found")
            if outcome.curriculum_version_id != version.id:
                raise CurriculumIntelligenceError(
                    "alignment outcome must belong to the supplied version"
                )
        else:
            target_kind = "competency"
            target_id = str(payload.competency_id)
            target_competency = self.session.get(Competency, target_id)
            if target_competency is None:
                raise LookupError("alignment competency not found")
            if target_competency.framework_id != version.curriculum_pack.framework_id:
                raise CurriculumIntelligenceError(
                    "alignment competency must belong to the curriculum framework"
                )

        if payload.status == "direct" and (
            not self.has_source_content(revision)
            or not payload.source_locator
            or not payload.evidence_text
        ):
            raise CurriculumIntelligenceError(
                "direct alignment requires retrieved source content, locator and evidence"
            )

        alignment_id = stable_uuid(
            "alignment",
            version.id,
            node.id,
            target_kind,
            target_id,
            payload.relationship_type,
            revision.id,
        )
        alignment = self.session.get(CurriculumAlignment, alignment_id)
        if alignment is None:
            alignment = CurriculumAlignment(
                id=alignment_id,
                curriculum_version_id=version.id,
                curriculum_node_id=node.id,
                relationship_type=payload.relationship_type,
                status=payload.status,
                source_revision_id=revision.id,
            )
            self.session.add(alignment)
        alignment.learning_outcome_id = (
            str(payload.learning_outcome_id) if payload.learning_outcome_id is not None else None
        )
        alignment.competency_id = (
            str(payload.competency_id) if payload.competency_id is not None else None
        )
        alignment.status = payload.status
        alignment.confidence = payload.confidence
        alignment.inferred = payload.inferred
        alignment.source_locator = payload.source_locator
        alignment.evidence_text = payload.evidence_text
        alignment.metadata_json = dict(payload.metadata_json)
        self.session.flush()
        return alignment

    def add_assessment_evidence(self, payload: AssessmentEvidenceInput) -> AssessmentEvidence:
        revision = self.session.get(SourceRevision, str(payload.source_revision_id))
        if revision is None:
            raise LookupError("assessment source revision not found")
        self._require_revision(revision)
        if not self._is_assessment_source(revision):
            raise CurriculumIntelligenceError("assessment evidence requires an assessment source")
        version = self.session.get(CurriculumVersion, str(payload.curriculum_version_id))
        if version is None:
            raise LookupError("assessment curriculum version not found")

        marking_scheme_id = (
            str(payload.marking_scheme_revision_id) if payload.marking_scheme_revision_id else None
        )
        evidence_revisions = [revision]
        if marking_scheme_id is not None:
            marking_scheme = self.session.get(SourceRevision, marking_scheme_id)
            if marking_scheme is None:
                raise LookupError("marking scheme source revision not found")
            self._require_revision(marking_scheme)
            scheme_type = marking_scheme.metadata_json.get("source_snapshot", {}).get("source_type")
            if scheme_type != "marking_scheme":
                raise CurriculumIntelligenceError(
                    "marking scheme binding requires a marking-scheme source"
                )
            evidence_revisions.append(marking_scheme)
        for evidence_revision in evidence_revisions:
            source_year = evidence_revision.metadata_json.get("source_snapshot", {}).get(
                "academic_year"
            )
            if source_year and source_year != version.academic_year:
                raise CurriculumIntelligenceError(
                    "assessment source academic year must match curriculum version"
                )
        grade_id = str(payload.grade_node_id) if payload.grade_node_id is not None else None
        subject_id = str(payload.subject_node_id) if payload.subject_node_id is not None else None
        if self._source_metadata(revision).get("document_type") != "sample_paper_index" and (
            grade_id is None or subject_id is None
        ):
            raise CurriculumIntelligenceError(
                "specific assessment documents require grade and subject"
            )
        for node_id, expected_type in (
            (grade_id, CurriculumNodeType.GRADE_YEAR.value),
            (subject_id, CurriculumNodeType.SUBJECT.value),
        ):
            if node_id is None:
                continue
            node = self.session.get(CurriculumNode, node_id)
            if node is None or node.curriculum_version_id != version.id:
                raise CurriculumIntelligenceError(
                    "assessment evidence node must belong to the supplied version"
                )
            if node.node_type != expected_type:
                raise CurriculumIntelligenceError(
                    f"assessment evidence expected {expected_type} node"
                )

        if grade_id is not None and subject_id is not None:
            path = self.hierarchy_path(subject_id)
            if not path or path[0].id != grade_id:
                raise CurriculumIntelligenceError(
                    "assessment subject must belong to the supplied grade"
                )

        for applicable_revision in evidence_revisions:
            applicability = self._source_metadata(applicable_revision)
            if grade_id is not None:
                grade = self.session.get(CurriculumNode, grade_id)
                assert grade is not None
                allowed_grades = applicability.get("grade_codes", [])
                grade_code = grade.metadata_json.get("grade_code") or grade.title.removeprefix(
                    "Class "
                )
                if not allowed_grades or grade_code not in allowed_grades:
                    raise CurriculumIntelligenceError(
                        "assessment source does not apply to supplied grade"
                    )
            if subject_id is not None:
                subject = self.session.get(CurriculumNode, subject_id)
                assert subject is not None
                allowed_subjects = applicability.get("subject_codes", [])
                declared_subject = applicability.get("subject")
                if (
                    allowed_subjects
                    and subject.metadata_json.get("subject_code") not in allowed_subjects
                ):
                    raise CurriculumIntelligenceError(
                        "assessment source does not apply to supplied subject"
                    )
                if (
                    declared_subject
                    and subject.title.casefold() != str(declared_subject).casefold()
                ):
                    raise CurriculumIntelligenceError(
                        "assessment source does not apply to supplied subject"
                    )
                if (
                    not allowed_subjects
                    and not declared_subject
                    and applicability.get("subject_scope") != "index"
                ):
                    raise CurriculumIntelligenceError(
                        "assessment source subject applicability is undeclared"
                    )

                if subject_id is not None and applicability.get("subject_scope") == "index":
                    if self.has_source_content(applicable_revision):

                        def normalize(value: str) -> str:
                            return " ".join(re.findall(r"\w+", value.casefold()))

                        from app.curriculum_intelligence.catalogue import extract_stored_index

                        inventory = extract_stored_index(
                            self, applicable_revision, kind="assessment"
                        )
                        claimed_subject = str(payload.evidence_json.get("subject") or subject.title)
                        subject_names = {
                            normalize(item["subject_label"]) for item in inventory["subjects"]
                        }
                        if normalize(claimed_subject) not in subject_names or not (
                            normalize(claimed_subject) == normalize(subject.title)
                            or normalize(claimed_subject).startswith(normalize(subject.title) + " ")
                        ):
                            raise CurriculumIntelligenceError(
                                "assessment index does not list supplied subject or variant"
                            )
                    elif subject.metadata_json.get("subject_code") not in applicability.get(
                        "registry_fixture_subject_codes", []
                    ):
                        raise CurriculumIntelligenceError(
                            "registry fixture has no evidence for supplied subject"
                        )
        identity_parts = [
            "assessment-evidence",
            version.id,
            revision.id,
            grade_id or "",
            subject_id or "",
            payload.evidence_type,
            payload.source_locator or "",
        ]
        if marking_scheme_id is not None:
            identity_parts.extend(["marking_scheme", marking_scheme_id])
        evidence_id = stable_uuid(*identity_parts)
        evidence = self.session.scalar(
            select(AssessmentEvidence).where(
                AssessmentEvidence.curriculum_version_id == version.id,
                AssessmentEvidence.source_revision_id == revision.id,
                AssessmentEvidence.marking_scheme_revision_id == marking_scheme_id,
                AssessmentEvidence.grade_node_id == grade_id,
                AssessmentEvidence.subject_node_id == subject_id,
                AssessmentEvidence.evidence_type == payload.evidence_type,
                AssessmentEvidence.source_locator == payload.source_locator,
            )
        )
        metadata = {
            key: value
            for key, value in payload.metadata_json.items()
            if key != "marking_scheme_revision_id"
        }
        if evidence is not None:
            prior_metadata = {
                key: value
                for key, value in evidence.metadata_json.items()
                if key != "marking_scheme_revision_id"
            }
            if evidence.evidence_json != payload.evidence_json or prior_metadata != metadata:
                raise CurriculumIntelligenceError(
                    "assessment evidence is immutable; use a new revision or evidence locator"
                )
            return evidence
        evidence = AssessmentEvidence(
            id=evidence_id,
            curriculum_version_id=version.id,
            evidence_type=payload.evidence_type,
            source_revision_id=revision.id,
            marking_scheme_revision_id=marking_scheme_id,
        )
        self.session.add(evidence)
        evidence.grade_node_id = grade_id
        evidence.subject_node_id = subject_id
        evidence.source_locator = payload.source_locator
        evidence.evidence_json = dict(payload.evidence_json)
        evidence.metadata_json = metadata
        self.session.flush()
        return evidence

    def coverage(self, version_id: str) -> CoverageSummary:
        relevant_types = {
            CurriculumNodeType.SUBJECT.value,
            CurriculumNodeType.UNIT.value,
            CurriculumNodeType.CHAPTER.value,
            CurriculumNodeType.TOPIC.value,
            CurriculumNodeType.CONCEPT.value,
        }
        node_ids = list(
            self.session.scalars(
                select(CurriculumNode.id).where(
                    CurriculumNode.curriculum_version_id == version_id,
                    CurriculumNode.node_type.in_(relevant_types),
                )
            )
        )
        if not node_ids:
            return CoverageSummary(
                total_nodes=0,
                mapped_nodes=0,
                partial_nodes=0,
                unresolved_nodes=0,
                unmapped_nodes=0,
            )

        rows = self.session.execute(
            select(CurriculumAlignment.curriculum_node_id, CurriculumAlignment.status).where(
                CurriculumAlignment.curriculum_node_id.in_(node_ids)
            )
        ).all()
        status_by_node: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
        for node_id, status in rows:
            status_by_node[str(node_id)].add(str(status))

        mapped = sum("direct" in statuses for statuses in status_by_node.values())
        partial = sum(
            "direct" not in statuses and "partial" in statuses
            for statuses in status_by_node.values()
        )
        unresolved = sum(
            bool(statuses & {"unresolved", "review_required"})
            and not bool(statuses & {"direct", "partial"})
            for statuses in status_by_node.values()
        )
        unmapped = sum(not statuses for statuses in status_by_node.values())
        return CoverageSummary(
            total_nodes=len(node_ids),
            mapped_nodes=mapped,
            partial_nodes=partial,
            unresolved_nodes=unresolved,
            unmapped_nodes=unmapped,
        )

    def provenance(
        self,
        *,
        entity_type: str,
        entity_id: str,
    ) -> dict[str, Any]:
        model_map: dict[str, Any] = {
            "framework": EducationFramework,
            "curriculum_pack": CurriculumPack,
            "curriculum_version": CurriculumVersion,
            "curriculum_node": CurriculumNode,
            "learning_outcome": LearningOutcome,
            "competency": Competency,
            "alignment": CurriculumAlignment,
            "assessment_evidence": AssessmentEvidence,
        }
        model = model_map.get(entity_type)
        if model is None:
            raise CurriculumIntelligenceError("unsupported provenance entity type")
        entity = self.session.get(model, entity_id)
        if entity is None:
            raise LookupError(f"{entity_type} not found")
        revision_id = getattr(entity, "source_revision_id", None)
        if revision_id is None:
            raise CurriculumIntelligenceError(
                f"{entity_type} does not have exact SourceRevision provenance"
            )
        revision = self.session.get(SourceRevision, revision_id)
        if revision is None:
            raise CurriculumIntelligenceError("provenance SourceRevision is missing")
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "source_revision_id": revision.id,
            "source_id": revision.source_id,
            "source_url": revision.metadata_json.get("source_snapshot", {}).get("url"),
            "authority": revision.metadata_json.get("source_snapshot", {}).get("authority"),
            "revision_status": revision.status,
            "source_locator": getattr(entity, "source_locator", None),
            "checksum": revision.checksum,
            "provenance_classification": (
                "synthetic_registry_fixture"
                if self.is_registry_only(revision)
                else "source_content_reference"
                if self.has_source_content(revision)
                else "manual_metadata_reference"
            ),
            "source_content_verified": self.has_source_content(revision),
            "mapping_verified": False,
            "marking_scheme_revision_id": getattr(entity, "marking_scheme_revision_id", None),
            "marking_scheme_source_locator": (
                getattr(entity, "metadata_json", {}).get("marking_scheme_source_locator")
                if entity_type == "assessment_evidence"
                else None
            ),
        }

    def hierarchy_path(self, node_id: str) -> list[CurriculumNode]:
        node = self.session.get(CurriculumNode, node_id)
        if node is None:
            raise LookupError("curriculum node not found")
        path: list[CurriculumNode] = []
        seen: set[str] = set()
        current: CurriculumNode | None = node
        while current is not None:
            if current.id in seen:
                raise CurriculumIntelligenceError("curriculum hierarchy cycle detected")
            seen.add(current.id)
            path.append(current)
            current = current.parent
        path.reverse()
        return path

    def curriculum_path(self, node_id: str) -> CurriculumPathResult:
        """Resolve a canonical path and its evidenced outcome/competency links."""
        path = self.hierarchy_path(node_id)
        version = path[-1].curriculum_version
        pack = version.curriculum_pack
        if pack.framework_id is None:
            raise CurriculumIntelligenceError("curriculum pack has no framework")
        path_ids = [node.id for node in path]
        alignments = list(
            self.session.scalars(
                select(CurriculumAlignment)
                .where(
                    CurriculumAlignment.curriculum_version_id == version.id,
                    CurriculumAlignment.curriculum_node_id.in_(path_ids),
                )
                .order_by(CurriculumAlignment.id)
            )
        )
        return CurriculumPathResult(
            framework_id=UUID(pack.framework_id),
            curriculum_pack_id=UUID(pack.id),
            curriculum_version_id=UUID(version.id),
            node_ids=[UUID(node_id) for node_id in path_ids],
            learning_outcome_ids=sorted(
                {UUID(row.learning_outcome_id) for row in alignments if row.learning_outcome_id}
            ),
            competency_ids=sorted(
                {UUID(row.competency_id) for row in alignments if row.competency_id}
            ),
            alignment_ids=[UUID(row.id) for row in alignments],
            source_revision_ids=sorted(
                {
                    UUID(revision_id)
                    for revision_id in (
                        [node.source_revision_id for node in path]
                        + [row.source_revision_id for row in alignments]
                        + [version.source_revision_id, pack.source_revision_id]
                        + (
                            [pack.framework.source_revision_id]
                            if pack.framework is not None
                            else []
                        )
                    )
                    if revision_id
                }
            ),
        )

    def entity_counts(self, version_id: str) -> dict[str, int]:
        return {
            "nodes": int(
                self.session.scalar(
                    select(func.count(CurriculumNode.id)).where(
                        CurriculumNode.curriculum_version_id == version_id
                    )
                )
                or 0
            ),
            "learning_outcomes": int(
                self.session.scalar(
                    select(func.count(LearningOutcome.id)).where(
                        LearningOutcome.curriculum_version_id == version_id
                    )
                )
                or 0
            ),
            "alignments": int(
                self.session.scalar(
                    select(func.count(CurriculumAlignment.id)).where(
                        CurriculumAlignment.curriculum_version_id == version_id
                    )
                )
                or 0
            ),
            "assessment_evidence": int(
                self.session.scalar(
                    select(func.count(AssessmentEvidence.id)).where(
                        AssessmentEvidence.curriculum_version_id == version_id
                    )
                )
                or 0
            ),
        }
