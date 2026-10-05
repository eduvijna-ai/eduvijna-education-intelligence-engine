"""Fail-closed Day 5 gate: reports describe evidence, never authorize it."""

from __future__ import annotations

import hashlib
from typing import Any

from app.curriculum_intelligence.scoped_catalogue import (
    STORAGE_KEY,
    CatalogueSnapshot,
    persisted_catalogue_coverage,
    validate_catalogue_row_evidence,
    validate_catalogue_row_locators,
    validate_catalogue_row_scope,
)
from app.curriculum_intelligence.scoped_curriculum import (
    SourceCurriculumScope,
    exact_scope,
    validate_correspondence_record,
    validate_entity_scope,
)
from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.curriculum_intelligence.source_domains import source_domain
from app.curriculum_intelligence.standards_evidence import (
    require_source_wording,
    source_text_at_locator,
)
from app.models.curriculum import Competency, CurriculumNode, CurriculumVersion, LearningOutcome
from app.models.enums import SourceRevisionStatus
from app.models.source import SourceRevision


def _revision(
    service: CurriculumIntelligenceService, revision_id: str | None, *, inventory: bool = False
) -> SourceRevision:
    if not revision_id:
        raise ValueError("Missing revision identity")
    revision = service.session.get(SourceRevision, revision_id)
    if revision is None:
        raise ValueError("Missing persisted revision")
    metadata = service._source_metadata(revision)
    if inventory and "inventory_scope" in metadata:
        if not service.has_source_content(revision) or not revision.storage_path:
            raise ValueError("Missing source bytes")
        content = service.source_service.storage.read(revision.storage_path)
        snapshot = revision.metadata_json.get("source_snapshot", {})
        if (
            revision.status != SourceRevisionStatus.ACTIVE.value
            or len(content) != revision.byte_size
            or hashlib.sha256(content).hexdigest() != revision.checksum
            or service.source_service._snapshot_checksum(snapshot)
            != revision.source_snapshot_checksum
            or not revision.approval_fingerprint
            or service.source_service._approval_fingerprint(revision)
            != revision.approval_fingerprint
        ):
            raise ValueError("Unverified inventory bytes or source review")
        scope = SourceCurriculumScope.model_validate(metadata["inventory_scope"])
    else:
        scope = exact_scope(service, revision)
    if (
        metadata.get("synthetic", False) is not False
        or revision.metadata_json.get("source_snapshot", {}).get("copyright_classification")
        == "synthetic_fixture"
        or service.is_registry_only(revision)
        or (
            scope.publication_status != "final"
            and not (
                inventory
                and "inventory_scope" in metadata
                and scope.publication_status == "draft"
                and metadata.get("document_type")
                in {"textbook_index", "publication_index", "syllabus_index", "curriculum_index"}
            )
        )
        or scope.applicability_status != "verified"
        or not _locator(service, revision, scope.applicability_locator)
    ):
        raise ValueError("Unverified official applicability")
    return revision


def _locator(
    service: CurriculumIntelligenceService, revision: SourceRevision, locator: Any
) -> bool:
    if not isinstance(locator, str) or not locator.strip():
        return False
    try:
        source_text_at_locator(service.source_service, revision, locator=locator)
    except (ValueError, OSError):
        return False
    return True


def _verify_slice(
    service: CurriculumIntelligenceService, required: dict[str, Any], item: dict[str, Any]
) -> bool:
    relationship_key = required.get("key") == "scert-viii-science-telugu-correspondence"
    expected_type = (
        "cross_medium_correspondence"
        if relationship_key
        else (
            "learning_outcomes"
            if required.get("key") == "scert-learning-outcomes"
            else "academic_standards"
            if required.get("key") == "scert-academic-standards"
            else "detailed_path"
        )
    )
    if required.get("materialization_type", expected_type) != expected_type:
        return False
    if item.get("materialization_type", expected_type) != expected_type:
        return False
    if relationship_key:
        return _verify_correspondence(service, required, item)
    # All expected values come from the frozen scope, never observed report fields.
    fields = (
        "chapter",
        "academic_version",
        "source_checksum",
        "source_locator",
        "pack_code",
        "grade",
        "medium",
        "subject",
        "course_family",
        "course_group",
        "subject_language",
        "language_role",
        "book_part",
        "bilingual",
    )
    if not all(required.get(field) and required[field] != "unknown" for field in fields):
        return False
    frozen_revision = required.get("source_revision")
    if not frozen_revision and not (
        required.get("source_url") and required.get("source_snapshot_checksum")
    ):
        return False
    revision = _revision(service, item.get("source_revision_id"))
    if frozen_revision and revision.id != frozen_revision:
        return False
    if required.get("source_url") and (
        revision.metadata_json.get("source_snapshot", {}).get("url") != required["source_url"]
    ):
        return False
    if required.get("source_snapshot_checksum") and (
        revision.source_snapshot_checksum != required["source_snapshot_checksum"]
    ):
        return False
    entity_domain = {
        "scert-learning-outcomes": "learning_outcome",
        "scert-academic-standards": "academic_standard",
    }.get(str(required.get("key")))
    if (
        revision.checksum != required["source_checksum"]
        or item.get("source_revision_id") != revision.id
        or item.get("source_checksum") != revision.checksum
        or item.get("academic_version") != required["academic_version"]
        or item.get("synthetic") is not False
        or source_domain(revision.metadata_json["source_snapshot"]) != (entity_domain or "syllabus")
    ):
        return False
    if entity_domain:
        ids = item.get("persisted_entity_ids", [])
        if not ids or len(ids) != len(set(ids)):
            return False
        for entity_id in ids:
            entity: Any = service.session.get(
                LearningOutcome if entity_domain == "learning_outcome" else Competency, entity_id
            )
            if entity is None:
                return False
            version_id = (
                entity.curriculum_version_id
                if entity_domain == "learning_outcome"
                else entity.metadata_json.get("curriculum_version_id")
            )
            version = service.session.get(CurriculumVersion, version_id)
            wording = entity.text if entity_domain == "learning_outcome" else entity.official_text
            if (
                version is None
                or version.version_code != required["academic_version"]
                or version.curriculum_pack.code != required["pack_code"]
                or entity.source_revision_id != revision.id
                or entity.source_locator != required["source_locator"]
                or not wording
                or not version.metadata_json.get("scope_enforced")
            ):
                return False
            require_source_wording(
                service.source_service,
                revision,
                locator=entity.source_locator,
                official_text=wording,
                official_code=entity.metadata_json.get("official_code"),
            )
            validate_entity_scope(service, version, revision, entity.metadata_json)
            if any(
                entity.metadata_json.get("identity", {}).get(field) != required[field]
                for field in (
                    "grade",
                    "medium",
                    "subject",
                    "course_family",
                    "course_group",
                    "subject_language",
                    "language_role",
                    "book_part",
                    "bilingual",
                )
            ):
                return False
        return True
    ids = item.get("path", {}).get("node_ids", [])
    if len(ids) != 7 or len(set(ids)) != 7:
        return False
    nodes = service.hierarchy_path(ids[-1])
    if [node.id for node in nodes] != ids or [node.node_type for node in nodes] != [
        "grade_year",
        "medium",
        "subject",
        "unit",
        "chapter",
        "topic",
        "concept",
    ]:
        return False
    version = nodes[-1].curriculum_version
    if (
        version.version_code != required["academic_version"]
        or version.curriculum_pack.code != required["pack_code"]
        or not version.metadata_json.get("scope_enforced")
        or nodes[4].title != required["chapter"]
        or nodes[4].source_locator != required["source_locator"]
    ):
        return False
    path_locators = required.get("path_locators", {})
    for node in nodes:
        # Recheck persisted ancestors independently of the writer's validation.
        if any(
            node.metadata_json.get("identity", {}).get(field) != required[field]
            for field in (
                "grade",
                "medium",
                "subject",
                "course_family",
                "course_group",
                "subject_language",
                "language_role",
                "book_part",
                "bilingual",
            )
        ):
            return False
        if path_locators and node.source_locator != path_locators.get(node.node_type):
            return False
        if (
            node.curriculum_version_id != version.id
            or node.source_revision_id != revision.id
            or not _locator(service, revision, node.source_locator)
        ):
            return False
        if (
            node.node_type in {"topic", "concept"}
            and required.get("topic_locator")
            and (node.source_locator != required["topic_locator"])
        ):
            return False
        if node.node_type in {"chapter", "topic"} and not node.official_text:
            return False
        if (
            node.node_type == "concept"
            and not node.official_text
            and (node.metadata_json.get("label_status") != "derived")
        ):
            return False
        if node.official_text is not None or node.metadata_json.get("official_code") is not None:
            require_source_wording(
                service.source_service,
                revision,
                locator=node.source_locator,
                official_text=node.official_text,
                official_code=node.metadata_json.get("official_code"),
            )
        validate_entity_scope(
            service,
            version,
            revision,
            node.metadata_json,
            node_type=node.node_type,
            parent_metadata=node.parent.metadata_json if node.parent else None,
        )
    identity = nodes[-1].metadata_json.get("identity", {})
    return all(
        identity.get(field) == required[field]
        for field in (
            "grade",
            "medium",
            "subject",
            "course_family",
            "course_group",
            "subject_language",
            "language_role",
            "book_part",
            "bilingual",
        )
    )


def _verify_correspondence(
    service: CurriculumIntelligenceService, required: dict[str, Any], item: dict[str, Any]
) -> bool:
    """A paired requirement is one verified relationship, never a lone medium path."""
    if (
        required.get("materialization_type") != "cross_medium_correspondence"
        or item.get("materialization_type") != "cross_medium_correspondence"
        or item.get("synthetic") is not False
    ):
        return False
    left_expected, right_expected = required.get("left", {}), required.get("right", {})
    binding = required.get("correspondence", {})
    if not left_expected or not right_expected or not binding:
        return False
    if (
        left_expected.get("medium") != "English"
        or right_expected.get("medium") != "Telugu"
        or left_expected.get("pack_code") != "ts-scert"
        or left_expected.get("grade") != "VIII"
    ):
        return False
    for field in ("pack_code", "academic_version", "grade", "subject"):
        if not left_expected.get(field) or left_expected[field] != right_expected.get(field):
            return False
    version = service.session.get(CurriculumVersion, item.get("version_id"))
    relation_id = item.get("relationship_id")
    if version is None or not isinstance(relation_id, str) or not relation_id:
        return False
    records = version.metadata_json.get("cross_medium_correspondences", {})
    record = records.get(relation_id)
    if (
        not isinstance(record, dict)
        or validate_correspondence_record(service, version, record) != relation_id
    ):
        return False
    if binding.get("relationship_id") and binding["relationship_id"] != relation_id:
        return False
    revision = _revision(service, record.get("source_revision_id"))
    snapshot = revision.metadata_json.get("source_snapshot", {})
    if (
        not binding.get("source_checksum")
        or binding["source_checksum"] != revision.checksum
        or record.get("source_checksum") != revision.checksum
        or (binding.get("source_revision") and binding["source_revision"] != revision.id)
        or not (
            binding.get("source_revision")
            or (binding.get("source_url") and binding.get("source_snapshot_checksum"))
        )
        or (binding.get("source_url") and binding["source_url"] != snapshot.get("url"))
        or (
            binding.get("source_snapshot_checksum")
            and binding["source_snapshot_checksum"] != revision.source_snapshot_checksum
        )
        or source_domain(snapshot)
        not in {"syllabus", "framework", "learning_outcome", "academic_standard"}
    ):
        return False
    declaration = {
        field: record.get(field)
        for field in ("left_code", "right_code", "locator", "evidence_text")
    }
    if not all(
        binding.get(field) and binding[field] == declaration[field] for field in declaration
    ) or declaration not in service._source_metadata(revision).get("correspondences", []):
        return False
    require_source_wording(
        service.source_service,
        revision,
        locator=record.get("locator"),
        official_text=record.get("evidence_text"),
    )
    if binding.get("node_type") not in {"chapter", "topic", "concept"} or record.get(
        "left_id"
    ) == record.get("right_id"):
        return False
    for side, expected in (("left", left_expected), ("right", right_expected)):
        node = service.session.get(CurriculumNode, record.get(side + "_id"))
        if (
            node is None
            or node.curriculum_version_id != version.id
            or node.code != binding[side + "_code"]
            or node.node_type != binding["node_type"]
        ):
            return False
        # Source scope for the relationship itself must cover each exact participant.
        validate_entity_scope(
            service, version, revision, node.metadata_json, node_type=node.node_type
        )
        observed = item.get(side, {})
        path_ids = observed.get("path", {}).get("node_ids", [])
        if not path_ids or node.id not in path_ids:
            return False
        side_contract = dict(expected) | {"key": side + "-correspondence-path"}
        if not _verify_slice(service, side_contract, observed):
            return False
        leaf = service.session.get(CurriculumNode, path_ids[-1])
        if leaf is None or leaf.curriculum_version_id != version.id:
            return False
    return True


def _verify_catalogue(
    service: CurriculumIntelligenceService, item: dict[str, Any], expected: dict[str, Any]
) -> bool:
    if item.get("inventory_kind") != "official_catalogue" or item.get("synthetic") is not False:
        return False
    version = service.session.get(CurriculumVersion, item.get("version_id"))
    if version is None or version.curriculum_pack.code != item.get("pack_code"):
        return False
    revision = _revision(service, item.get("source_revision_id"), inventory=True)
    frozen_source = revision.metadata_json.get("source_snapshot", {})
    if (
        version.version_code != expected.get("academic_version")
        or version.academic_year != expected.get("academic_year")
        or expected.get("source_url") != frozen_source.get("url")
        or expected.get("source_checksum") != revision.checksum
        or expected.get("source_snapshot_checksum") != revision.source_snapshot_checksum
        or (expected.get("source_revision") and expected["source_revision"] != revision.id)
    ):
        return False
    metadata = service._source_metadata(revision)
    if metadata.get("document_type") not in {
        "textbook_index",
        "publication_index",
        "syllabus_index",
        "curriculum_index",
    }:
        return False
    scope = SourceCurriculumScope.model_validate(
        metadata.get("inventory_scope", metadata.get("curriculum_scope"))
    )
    if (
        scope.pack_code != version.curriculum_pack.code
        or version.version_code not in scope.version_codes
    ):
        return False
    governing_scope: SourceCurriculumScope | None = None
    if scope.publication_status == "draft":
        # Draft metadata can be accounted for; it cannot govern the curriculum.
        if version.source_revision_id == revision.id:
            return False
        governing = _revision(service, version.source_revision_id)
        governing_scope = exact_scope(service, governing)
        frozen = metadata.get("governing_source", {})
        governing_snapshot = governing.metadata_json.get("source_snapshot", {})
        if (
            source_domain(governing_snapshot) != "syllabus"
            or governing_scope.pack_code != version.curriculum_pack.code
            or version.version_code not in governing_scope.version_codes
            or governing_snapshot.get("academic_year") != version.academic_year
            or frozen.get("source_url") != governing_snapshot.get("url")
            or not frozen.get("source_url")
            or frozen.get("source_checksum") != governing.checksum
            or frozen.get("source_snapshot_checksum") != governing.source_snapshot_checksum
            or frozen.get("academic_year") != version.academic_year
            or frozen.get("version_code") != version.version_code
        ):
            return False
    record = version.metadata_json.get(STORAGE_KEY, {}).get(revision.id)
    if not record:
        return False
    snapshot = CatalogueSnapshot.model_validate(record["snapshot"])
    if (
        expected.get("inventory_digest") != snapshot.inventory_digest
        or not snapshot.inventory_observations
        or snapshot.source_checksum != revision.checksum
        or item.get("source_checksum") != revision.checksum
        or item.get("snapshot_id") != snapshot.identity
        or snapshot.inventory_digest
        not in service._source_metadata(revision).get("official_catalogue_review_digests", [])
    ):
        return False
    for row in snapshot.rows:
        validate_catalogue_row_scope(version, row, scope)
        validate_catalogue_row_locators(service, revision, row)
        validate_catalogue_row_evidence(service, revision, row, version=version)
        if governing_scope is not None:
            validate_catalogue_row_scope(version, row, governing_scope)
    coverage = persisted_catalogue_coverage(version, revision.id)
    return bool(
        coverage.status == "complete"
        and coverage.snapshot_row_count > 0
        and all(
            _locator(service, revision, row.source_locator)
            and row.grade in scope.grades
            and row.instructional_medium in scope.media
            and row.academic_year == version.academic_year
            for row in snapshot.rows
        )
        and item.get("coverage", {}).get("snapshot_row_count") == coverage.snapshot_row_count
        and item.get("coverage", {}).get("materialized_metadata_count")
        == coverage.materialized_metadata_count
    )


def evaluate_day5_acceptance(
    report: dict[str, Any],
    scope: dict[str, Any],
    *,
    verification_slice: dict[str, Any] | None = None,
    service: CurriculumIntelligenceService | None = None,
) -> dict[str, Any]:
    requirements = scope.get("required_detailed_slices", [])
    evidence = report.get("materialized_slices", [])
    keys = [item.get("key") for item in requirements]
    observed_keys = [item.get("key") for item in evidence]
    failed: list[str] = []
    valid_shape = bool(
        keys
        and all(keys)
        and len(keys) == len(set(keys))
        and len(observed_keys) == len(set(observed_keys))
        and set(observed_keys) == set(keys)
    )
    if not valid_shape:
        failed.append("invalid_required_scope_or_duplicate_evidence")
    if service is None:
        failed.append("persisted_evidence_service_required")
    observations = {item.get("key"): item for item in evidence}
    blocked = set((verification_slice or {}).get("blocked_slice_keys", []))
    verified_count = 0
    verified_by_type: dict[str, int] = {}
    for required in requirements:
        key = required.get("key")
        verified = False
        if (
            service is not None
            and valid_shape
            and required.get("status") != "blocked"
            and key not in blocked
        ):
            try:
                verified = _verify_slice(service, required, observations.get(key, {}))
            except (ValueError, LookupError, TypeError, KeyError, OSError):
                verified = False
        if verified:
            verified_count += 1
            kind = (
                "cross_medium_correspondence"
                if key == "scert-viii-science-telugu-correspondence"
                else (
                    "learning_outcomes"
                    if key == "scert-learning-outcomes"
                    else "academic_standards"
                    if key == "scert-academic-standards"
                    else "detailed_path"
                )
            )
            verified_by_type[kind] = verified_by_type.get(kind, 0) + 1
        else:
            failed.append(str(key))
    inventories = report.get("catalogue_inventories", [])
    official = [item for item in inventories if item.get("inventory_kind") == "official_catalogue"]
    identities = [(item.get("version_id"), item.get("source_revision_id")) for item in inventories]
    if {item.get("pack_code") for item in official} != {"ts-scert", "tgbie"} or len(
        identities
    ) != len(set(identities)):
        failed.append("required_catalogue_inventories")
    packs = scope.get("packs", [])
    pack_keys = [(pack.get("code"), pack.get("academic_version")) for pack in packs]
    frozen_inventories = []
    if (
        not packs
        or {pack.get("code") for pack in packs} != {"ts-scert", "tgbie"}
        or len(pack_keys) != len(set(pack_keys))
    ):
        failed.append("invalid_frozen_catalogue_scope")
    for pack in packs:
        if (
            not pack.get("academic_version")
            or not pack.get("academic_year")
            or not pack.get("inventories")
        ):
            failed.append("invalid_frozen_catalogue_scope")
        for inventory in pack.get("inventories", []):
            expected = dict(inventory) | {
                "pack_code": pack.get("code"),
                "academic_version": pack.get("academic_version"),
                "academic_year": pack.get("academic_year"),
            }
            if not all(
                expected.get(field)
                for field in (
                    "source_url",
                    "source_checksum",
                    "source_snapshot_checksum",
                    "inventory_digest",
                )
            ):
                failed.append("invalid_frozen_catalogue_scope")
            frozen_inventories.append(expected)
    expected_keys = [
        (item.get("pack_code"), item.get("academic_version"), item.get("source_url"))
        for item in frozen_inventories
    ]
    if len(expected_keys) != len(set(expected_keys)) or len(official) != len(frozen_inventories):
        failed.append("invalid_frozen_catalogue_scope")
    matched: set[int] = set()
    for item in official:
        verified = False
        if service is not None:
            for index, expected in enumerate(frozen_inventories):
                if expected.get("pack_code") != item.get("pack_code"):
                    continue
                try:
                    if _verify_catalogue(service, item, expected):
                        if index not in matched:
                            matched.add(index)
                            verified = True
                        break
                except (ValueError, LookupError, TypeError, KeyError, OSError):
                    pass
        if not verified:
            failed.append(str(item.get("pack_code")) + "_catalogue")
    if len(matched) != len(frozen_inventories):
        failed.append("missing_required_catalogue_inventory")
    # Frozen pack boundaries cannot disappear behind a smaller complete snapshot.
    for pack in scope.get("packs", []):
        expected_grades = set(pack.get("grades", pack.get("years", [])))
        observed_grades: set[str] = set()
        if service is not None:
            for inventory in official:
                if inventory.get("pack_code") != pack.get("code"):
                    continue
                version = service.session.get(CurriculumVersion, inventory.get("version_id"))
                if version is None or version.version_code != pack.get("academic_version"):
                    continue
                record = version.metadata_json.get(STORAGE_KEY, {}).get(
                    inventory.get("source_revision_id"), {}
                )
                observed_grades.update(
                    row.get("grade") for row in record.get("rows", []) if row.get("grade")
                )
        if not expected_grades or not expected_grades <= observed_grades:
            failed.append(str(pack.get("code")) + "_catalogue_scope")
    for field in (
        "blocked_sources",
        "fetch_blockers",
        "materialization_blockers",
        "unresolved_applicability",
        "catalogue_gaps",
        "unresolved_materialization",
    ):
        if report.get(field) or scope.get(field):
            failed.append(
                "required_official_sources_blocked" if field == "blocked_sources" else field
            )
    return {
        "passed": not failed,
        "incomplete_components": list(dict.fromkeys(failed)),
        "verified_detailed_slice_count": verified_count,
        "verified_materialization_counts": verified_by_type,
        "scope": "Reviewed bounded Day 5 scope; not all curriculum content",
    }
