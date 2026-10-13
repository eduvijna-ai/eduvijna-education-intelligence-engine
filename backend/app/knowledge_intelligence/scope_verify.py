from __future__ import annotations

from sqlalchemy.orm import Session

from app.knowledge_intelligence.contracts import KnowledgeRetrievalRequest
from app.models.source import Source, SourceRevision


def verified_entity_refs(session: Session, revision: SourceRevision) -> dict[str, str]:
    session.refresh(revision, attribute_names=["curriculum_versions", "exam_versions"])
    refs: dict[str, str] = {}
    if revision.curriculum_versions:
        refs["curriculum_version_id"] = revision.curriculum_versions[0].id
    if revision.exam_versions:
        refs["exam_version_id"] = revision.exam_versions[0].id
    return refs


def revision_matches_curriculum_filter(
    session: Session, revision: SourceRevision, curriculum_version_id: str
) -> bool:
    session.refresh(revision, attribute_names=["curriculum_versions"])
    return any(cv.id == curriculum_version_id for cv in revision.curriculum_versions)


def revision_matches_exam_filter(
    session: Session, revision: SourceRevision, exam_version_id: str
) -> bool:
    session.refresh(revision, attribute_names=["exam_versions"])
    return any(ev.id == exam_version_id for ev in revision.exam_versions)


def _metadata_value(source: Source, revision: SourceRevision, key: str) -> str | list[str] | None:
    for container in (revision.metadata_json, source.metadata_json):
        if key in container:
            return container[key]
    return None


def local_scope_passes(
    session: Session,
    source: Source,
    revision: SourceRevision,
    request: KnowledgeRetrievalRequest,
) -> tuple[bool, dict[str, str], list[str]]:
    """Authoritative local verification of scope filters (D7-R05 / D7-R07)."""
    warnings: list[str] = []
    entity_refs = verified_entity_refs(session, revision)

    if request.curriculum_version_id:
        if not revision_matches_curriculum_filter(
            session, revision, request.curriculum_version_id
        ):
            return False, {}, ["dropped_unverified_curriculum"]
        entity_refs = {
            **entity_refs,
            "curriculum_version_id": request.curriculum_version_id,
        }

    if request.exam_version_id:
        if not revision_matches_exam_filter(session, revision, request.exam_version_id):
            return False, {}, ["dropped_unverified_exam"]
        entity_refs = {**entity_refs, "exam_version_id": request.exam_version_id}

    for scalar_key in ("grade_year_code", "medium_code", "subject_code"):
        requested = getattr(request, scalar_key)
        if not requested:
            continue
        actual = _metadata_value(source, revision, scalar_key)
        if actual is None:
            warnings.append(f"filter_unverifiable:{scalar_key}")
            return False, entity_refs, warnings
        if str(actual) != requested:
            return False, entity_refs, [f"dropped_scope_mismatch:{scalar_key}"]

    for list_key in ("topic_codes", "concept_codes"):
        requested = getattr(request, list_key)
        if not requested:
            continue
        actual = _metadata_value(source, revision, list_key)
        if actual is None:
            warnings.append(f"filter_unverifiable:{list_key}")
            return False, entity_refs, warnings
        actual_set = {str(item) for item in actual} if isinstance(actual, list) else {str(actual)}
        if not set(requested).issubset(actual_set):
            return False, entity_refs, [f"dropped_scope_mismatch:{list_key}"]

    return True, entity_refs, warnings
