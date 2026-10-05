"""Framework hierarchy and explicit LO/competency evidence services.

Framework records are separate from curriculum chapter membership. Each framework
row identifies a version; a source change must create a newly reviewed framework
version instead of overwriting historical structure. Reads retain historical rows.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.curriculum_intelligence.source_domains import require_domain, source_domain
from app.curriculum_intelligence.standards_evidence import (
    StandardsEvidenceError,
    contains_complete_identifier,
    require_source_wording,
    require_standards_evidence,
)
from app.models.curriculum import (
    Competency,
    CurriculumPack,
    CurriculumVersion,
    EducationFramework,
    LearningOutcome,
)
from app.models.enums import SourceRevisionStatus
from app.models.framework_structure import FrameworkStructureNode, LearningOutcomeCompetencyLink
from app.models.source import SourceRevision
from app.schemas.framework_structure import (
    FrameworkLevel,
    FrameworkNodeResult,
    FrameworkNodeSpec,
    FrameworkPathResult,
    LearningOutcomeCompetencyInput,
    LearningOutcomeCompetencyResult,
)
from app.source_intelligence.service import SourceIntelligenceService

_NAMESPACE = UUID("94593223-c334-4acb-b880-0ace97ed4567")
_PARENT_LEVEL: dict[str, str | None] = {
    "stage": None,
    "curricular_area": "stage",
    "goal": "curricular_area",
    "competency": "goal",
}


class FrameworkStructureError(ValueError):
    pass


def _identity(*parts: str) -> str:
    return str(uuid5(_NAMESPACE, json.dumps(parts, ensure_ascii=True)))


class FrameworkStructureService:
    def __init__(
        self, session: Session, *, source_service: SourceIntelligenceService | None = None
    ) -> None:
        self.session = session
        self.source_service = source_service or SourceIntelligenceService(session)

    def _active_revision(
        self, revision_id: str, purpose: str = "framework_structure"
    ) -> SourceRevision:
        revision = self.session.get(SourceRevision, revision_id, populate_existing=True)
        if revision is None:
            raise LookupError("framework evidence SourceRevision not found")
        if revision.status != SourceRevisionStatus.ACTIVE.value:
            raise FrameworkStructureError(
                "framework evidence writes require an active SourceRevision"
            )
        if CurriculumIntelligenceService._is_assessment_source(revision):
            raise FrameworkStructureError(
                "assessment sources cannot establish framework structure or learning-outcome links"
            )
        try:
            require_domain(revision.metadata_json.get("source_snapshot", {}), purpose)
        except ValueError as exc:
            raise FrameworkStructureError(str(exc)) from exc
        return revision

    def _standard_content(self, revision: SourceRevision, specs: list[FrameworkNodeSpec]) -> None:
        for spec in specs:
            try:
                require_standards_evidence(
                    self.source_service,
                    revision,
                    locator=spec.source_locator,
                    official_text=spec.official_text,
                    official_code=spec.official_code,
                )
            except StandardsEvidenceError as exc:
                raise FrameworkStructureError(str(exc)) from exc

    def _framework(self, framework_id: str) -> EducationFramework:
        framework = self.session.get(EducationFramework, framework_id)
        if framework is None:
            raise LookupError("education framework not found")
        if not framework.version_code:
            raise FrameworkStructureError("framework structure requires a versioned framework")
        return framework

    @staticmethod
    def _assert_unchanged(entity: Any, values: dict[str, Any]) -> None:
        if entity.source_revision_id != values["source_revision_id"]:
            raise FrameworkStructureError(
                "framework evidence cannot silently rebind to a different SourceRevision; "
                "create a new reviewed framework version"
            )
        if any(getattr(entity, key) != value for key, value in values.items()):
            raise FrameworkStructureError(
                "existing framework evidence is immutable; changed content requires review "
                "and a new version or evidence identity"
            )

    def upsert_nodes(
        self,
        *,
        framework: EducationFramework,
        revision: SourceRevision,
        specs: Iterable[FrameworkNodeSpec],
    ) -> dict[str, FrameworkStructureNode]:
        """Create a typed framework tree, or return identical existing evidence.

        ``code`` is a normalized identity unique within this framework version.
        Use qualified codes when local official labels recur in different areas,
        and retain the original label in ``official_code``. Validate the whole
        bundle before writing, so invalid/missing/cyclic parents leave no rows.
        """
        revision = self._active_revision(revision.id)
        framework = self._framework(framework.id)
        specs_list = list(specs)
        if (
            specs_list
            and revision.approval_fingerprint
            and self.source_service._snapshot_checksum(
                revision.metadata_json.get("source_snapshot", {})
            )
            != revision.source_snapshot_checksum
        ):
            raise FrameworkStructureError("Immutable source metadata checksum mismatch")
        if len({spec.code for spec in specs_list}) != len(specs_list):
            raise FrameworkStructureError("duplicate framework node codes in bundle")
        existing = {
            node.code: node
            for node in self.session.scalars(
                select(FrameworkStructureNode).where(
                    FrameworkStructureNode.framework_id == framework.id
                )
            )
        }
        if source_domain(revision.metadata_json.get("source_snapshot", {})) == "academic_standard":
            for spec in specs_list:
                if (
                    spec.level != "competency"
                    or not spec.parent_code
                    or spec.parent_code not in existing
                ):
                    raise FrameworkStructureError(
                        "academic standards may only add competencies "
                        "beneath existing framework goals"
                    )
                evidenced_parent = existing[spec.parent_code]
                parent_revision = self.session.get(
                    SourceRevision, evidenced_parent.source_revision_id
                )
                if parent_revision is None or source_domain(
                    parent_revision.metadata_json.get("source_snapshot", {})
                ) not in {"framework", "syllabus"}:
                    raise FrameworkStructureError(
                        "Competency parent lacks governing framework evidence"
                    )
            if specs_list:
                self._standard_content(revision, specs_list)
        resolved = dict(existing)
        result: dict[str, FrameworkStructureNode] = {}
        pending = {spec.code: spec for spec in specs_list}
        planned: list[FrameworkStructureNode] = []
        used_competencies = {
            node.competency_id: node.code for node in existing.values() if node.competency_id
        }
        while pending:
            progressed = False
            for code, spec in list(pending.items()):
                parent = resolved.get(spec.parent_code) if spec.parent_code else None
                # Validate parents supplied in this bundle before their children.
                if spec.parent_code in pending:
                    continue
                expected_parent = _PARENT_LEVEL[spec.level]
                if expected_parent is None:
                    if spec.parent_code is not None:
                        raise FrameworkStructureError("stage nodes must be roots")
                elif parent is None:
                    raise FrameworkStructureError(
                        "framework hierarchy contains missing or cross-framework parent"
                    )
                elif parent.level != expected_parent:
                    raise FrameworkStructureError(
                        f"invalid parent level: {spec.level} requires {expected_parent}"
                    )
                competency_id = str(spec.competency_id) if spec.competency_id else None
                if competency_id:
                    competency = self.session.get(Competency, competency_id)
                    if competency is None:
                        raise LookupError("framework competency not found")
                    if competency.framework_id != framework.id:
                        raise FrameworkStructureError("cross-framework competency target")
                    if competency.source_revision_id != revision.id:
                        raise FrameworkStructureError(
                            "Attached competency must retain the same exact source revision"
                        )
                    if (
                        source_domain(revision.metadata_json.get("source_snapshot", {}))
                        == "academic_standard"
                    ):
                        attached_code = competency.metadata_json.get("official_code")
                        try:
                            require_standards_evidence(
                                self.source_service,
                                revision,
                                locator=competency.source_locator,
                                official_text=competency.official_text,
                                official_code=attached_code,
                            )
                        except StandardsEvidenceError as exc:
                            raise FrameworkStructureError(str(exc)) from exc
                        same_code = bool(attached_code and spec.official_code == attached_code)
                        same_text = bool(
                            competency.official_text
                            and spec.official_text == competency.official_text
                        )
                        if (
                            not (same_code or same_text)
                            or (
                                spec.official_code is not None
                                and spec.official_code != attached_code
                            )
                            or (
                                spec.official_text is not None
                                and spec.official_text != competency.official_text
                            )
                        ):
                            raise FrameworkStructureError(
                                "Node and attached competency official identity differ"
                            )
                    if (
                        competency_id in used_competencies
                        and used_competencies[competency_id] != code
                    ):
                        raise FrameworkStructureError("duplicate competency in framework structure")
                    used_competencies[competency_id] = code
                values: dict[str, Any] = {
                    "framework_id": framework.id,
                    "level": spec.level,
                    "code": spec.code,
                    "official_code": spec.official_code,
                    "title": spec.title,
                    "official_text": spec.official_text,
                    "parent_id": parent.id if parent else None,
                    "parent_level": parent.level if parent else None,
                    "competency_id": competency_id,
                    "sequence": spec.sequence,
                    "source_revision_id": revision.id,
                    "source_locator": spec.source_locator,
                    "publication_status": spec.publication_status,
                    "review_status": spec.review_status,
                    "inferred": spec.inferred,
                }
                node = existing.get(code)
                if node is not None:
                    self._assert_unchanged(node, values)
                else:
                    node = FrameworkStructureNode(
                        id=_identity("framework-node", framework.id, code), **values
                    )
                    planned.append(node)
                resolved[code] = node
                result[code] = node
                del pending[code]
                progressed = True
            if not progressed:
                raise FrameworkStructureError("framework hierarchy contains a cycle or self-link")
        # The caller owns commit/rollback. In particular, do not start a savepoint
        # before the first write: SQLite legacy mode can release it as a commit.
        for node in planned:
            self.session.add(node)
            self.session.flush()
        return result

    def _version_framework(self, version_id: str) -> str:
        version = self.session.get(CurriculumVersion, version_id)
        if version is None:
            raise LookupError("curriculum version not found")
        pack = self.session.get(CurriculumPack, version.curriculum_pack_id)
        if pack is None or pack.framework_id is None:
            raise FrameworkStructureError("curriculum version requires a framework-bound pack")
        return pack.framework_id

    def link_learning_outcome(
        self, payload: LearningOutcomeCompetencyInput
    ) -> LearningOutcomeCompetencyLink:
        """Add reviewed or explicitly inferred evidence; never infer official mapping."""
        revision = self._active_revision(str(payload.source_revision_id), "alignment")
        if payload.status == "direct" and (
            revision.ingestion_method == "manual"
            or revision.extraction_status != "succeeded"
            or revision.extracted_checksum != revision.checksum
            or not revision.extracted_text
        ):
            raise FrameworkStructureError("direct links require retrieved source content")
        framework_id = self._version_framework(str(payload.curriculum_version_id))
        outcome = self.session.get(LearningOutcome, str(payload.learning_outcome_id))
        if outcome is None:
            raise LookupError("learning outcome not found")
        if outcome.curriculum_version_id != str(payload.curriculum_version_id):
            raise FrameworkStructureError(
                "learning outcome belongs to a different curriculum version"
            )
        node = self.session.get(FrameworkStructureNode, str(payload.competency_node_id))
        if node is None:
            raise LookupError("framework competency node not found")
        if node.level != "competency" or node.competency_id is None:
            raise FrameworkStructureError("learning outcome target must be a competency-level node")
        competency = self.session.get(Competency, node.competency_id)
        if (
            node.framework_id != framework_id
            or competency is None
            or competency.framework_id != framework_id
        ):
            raise FrameworkStructureError(
                "learning outcome cannot link to a cross-framework target"
            )
        if payload.status == "direct":
            # A mapping publication may legitimately reference separately sourced
            # outcomes and standards. Revalidate each target's own exact evidence;
            # only a node and its attached competency must share their source.
            if node.source_revision_id != competency.source_revision_id:
                raise FrameworkStructureError(
                    "Node and attached competency evidence revisions differ"
                )
            if outcome.source_revision_id is None:
                raise FrameworkStructureError("Direct mapping outcome has no source revision")
            outcome_revision = self._active_revision(outcome.source_revision_id, "outcome")
            node_revision = self._active_revision(node.source_revision_id, "framework_structure")
            competency_revision = self._active_revision(competency.source_revision_id, "competency")
            competency_code = competency.metadata_json.get("official_code")
            if not (
                competency_code
                and competency_code == node.official_code
                or competency.official_text
                and competency.official_text == node.official_text
            ):
                raise FrameworkStructureError("Direct mapping target official identities differ")
            try:
                require_source_wording(
                    self.source_service,
                    revision,
                    locator=payload.source_locator,
                    official_text=payload.evidence_text,
                )
                require_source_wording(
                    self.source_service,
                    outcome_revision,
                    locator=outcome.source_locator,
                    official_text=outcome.text,
                )
                require_source_wording(
                    self.source_service,
                    node_revision,
                    locator=node.source_locator,
                    official_text=node.official_text,
                    official_code=node.official_code,
                )
                require_source_wording(
                    self.source_service,
                    competency_revision,
                    locator=competency.source_locator,
                    official_text=competency.official_text,
                    official_code=competency_code,
                )
            except StandardsEvidenceError as exc:
                raise FrameworkStructureError(str(exc)) from exc
            quote = payload.evidence_text or ""
            if (
                outcome.text not in quote
                or (
                    node.official_code
                    and not contains_complete_identifier(quote, node.official_code)
                )
                or (
                    not node.official_code
                    and (not node.official_text or node.official_text not in quote)
                )
            ):
                raise FrameworkStructureError(
                    "Direct quote must identify both the outcome and competency"
                )
        values: dict[str, Any] = {
            "curriculum_version_id": str(payload.curriculum_version_id),
            "learning_outcome_id": outcome.id,
            "framework_id": framework_id,
            "competency_node_id": node.id,
            "competency_node_level": "competency",
            "relationship_type": payload.relationship_type,
            "status": payload.status,
            "inferred": payload.inferred,
            "publication_status": payload.publication_status,
            "review_status": payload.review_status,
            "source_revision_id": revision.id,
            "source_locator": payload.source_locator,
            "evidence_text": payload.evidence_text,
        }
        link_id = _identity(
            "lo-competency", outcome.id, node.id, payload.relationship_type, revision.id
        )
        existing = self.session.get(LearningOutcomeCompetencyLink, link_id)
        if existing:
            self._assert_unchanged(existing, values)
            return existing
        link = LearningOutcomeCompetencyLink(id=link_id, **values)
        self.session.add(link)
        self.session.flush()
        return link

    def list_nodes(
        self, framework_id: str, *, level: FrameworkLevel | None = None
    ) -> list[FrameworkNodeResult]:
        self._framework(framework_id)
        if level is not None and level not in _PARENT_LEVEL:
            raise FrameworkStructureError("unknown framework level")
        query = select(FrameworkStructureNode).where(
            FrameworkStructureNode.framework_id == framework_id
        )
        if level is not None:
            query = query.where(FrameworkStructureNode.level == level)
        return [
            FrameworkNodeResult.model_validate(node)
            for node in self.session.scalars(
                query.order_by(FrameworkStructureNode.sequence, FrameworkStructureNode.code)
            )
        ]

    def path_for_competency(
        self, node_id: str, *, curriculum_version_id: str | None = None
    ) -> FrameworkPathResult:
        """Read exact evidence, including historical/superseded source revisions."""
        node = self.session.get(FrameworkStructureNode, node_id)
        if node is None:
            raise LookupError("framework competency node not found")
        if node.level != "competency":
            raise FrameworkStructureError("framework path must end at a competency")
        framework = self._framework(node.framework_id)
        if (
            curriculum_version_id is not None
            and self._version_framework(curriculum_version_id) != framework.id
        ):
            raise FrameworkStructureError(
                "query curriculum version belongs to a different framework"
            )
        nodes = [node]
        while node.parent_id is not None:
            parent = self.session.get(FrameworkStructureNode, node.parent_id)
            if parent is None or parent.id in {item.id for item in nodes}:
                raise FrameworkStructureError("invalid stored framework hierarchy")
            nodes.append(parent)
            node = parent
        links_query = select(LearningOutcomeCompetencyLink).where(
            LearningOutcomeCompetencyLink.competency_node_id == node_id
        )
        if curriculum_version_id is not None:
            links_query = links_query.where(
                LearningOutcomeCompetencyLink.curriculum_version_id == curriculum_version_id
            )
        return FrameworkPathResult(
            framework_id=UUID(framework.id),
            framework_version_code=framework.version_code or "",
            nodes=[FrameworkNodeResult.model_validate(item) for item in reversed(nodes)],
            learning_outcome_links=[
                LearningOutcomeCompetencyResult.model_validate(link)
                for link in self.session.scalars(
                    links_query.order_by(LearningOutcomeCompetencyLink.id)
                )
            ],
        )
