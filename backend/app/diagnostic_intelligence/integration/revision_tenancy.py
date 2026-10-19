from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.source import Source, SourceRevision

_UUID_LIKE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class RevisionTenantRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: str | None = None
    institution_id: str | None = None
    teacher_id: str | None = None


def normalize_revision_ref(ref: str) -> str:
    return ref[4:] if ref.startswith("rev:") else ref


def looks_like_revision_id(ref: str) -> bool:
    return bool(_UUID_LIKE.match(normalize_revision_ref(ref)))


def load_revision_tenant_records(
    session: Session, revision_ids: Iterable[str]
) -> dict[str, RevisionTenantRecord]:
    ids = {normalize_revision_ref(value) for value in revision_ids if value}
    if not ids:
        return {}
    rows = session.execute(
        select(SourceRevision.id, Source.organization_id, Source.institution_id, Source.teacher_id)
        .join(Source, Source.id == SourceRevision.source_id)
        .where(SourceRevision.id.in_(ids))
    ).all()
    return {
        str(revision_id): RevisionTenantRecord(
            organization_id=str(organization_id) if organization_id else None,
            institution_id=str(institution_id) if institution_id else None,
            teacher_id=str(teacher_id) if teacher_id else None,
        )
        for revision_id, organization_id, institution_id, teacher_id in rows
    }


def tenant_scope_mismatch(
    *,
    organization_id: str | None,
    institution_id: str | None,
    teacher_id: str | None,
    record: RevisionTenantRecord,
) -> bool:
    if organization_id and record.organization_id and organization_id != record.organization_id:
        return True
    if institution_id and record.institution_id and institution_id != record.institution_id:
        return True
    if record.teacher_id and (not teacher_id or teacher_id != record.teacher_id):
        return True
    return False
