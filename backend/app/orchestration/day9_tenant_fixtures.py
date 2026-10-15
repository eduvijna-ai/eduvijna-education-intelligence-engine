"""Cross-tenant revision fixtures for Day 9 isolation proofs."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.knowledge_intelligence.fixtures import _OFFICIAL_TEXT, _active_revision
from app.models import Institution, Organization, Teacher
from app.models.enums import SourceStatus, SourceTrustTier, SourceType
from app.models.source import Source


@dataclass(frozen=True, slots=True)
class Day9ForeignTenantContext:
    foreign_organization_revision_id: str
    foreign_institution_revision_id: str
    foreign_teacher_revision_id: str


def seed_day9_foreign_tenant_revisions(
    session: Session, tenant_a_ctx: dict[str, str]
) -> Day9ForeignTenantContext:
    """Seed real revisions for org / institution / teacher isolation proofs."""
    org_b = Organization(code="day9-org-b", name="Day9 Org B")
    session.add(org_b)
    session.flush()
    inst_b = Institution(organization_id=org_b.id, code="day9-inst-b", name="Day9 Inst B")
    session.add(inst_b)
    session.flush()

    inst_a_other = Institution(
        organization_id=tenant_a_ctx["organization_id"],
        code="day9-inst-a-other",
        name="Day9 Inst A Other",
    )
    session.add(inst_a_other)
    session.flush()

    foreign_org_source = Source(
        organization_id=org_b.id,
        institution_id=inst_b.id,
        source_type=SourceType.INSTITUTION_CONTENT.value,
        title="Day9 foreign organization source",
        trust_tier=SourceTrustTier.INSTITUTION.value,
        status=SourceStatus.ACTIVE.value,
        metadata_json={"synthetic_fixture": True, "fixture_role": "day9_foreign_org"},
    )
    foreign_inst_source = Source(
        organization_id=tenant_a_ctx["organization_id"],
        institution_id=inst_a_other.id,
        source_type=SourceType.INSTITUTION_CONTENT.value,
        title="Day9 foreign institution source",
        trust_tier=SourceTrustTier.INSTITUTION.value,
        status=SourceStatus.ACTIVE.value,
        metadata_json={"synthetic_fixture": True, "fixture_role": "day9_foreign_inst"},
    )
    foreign_teacher = Teacher(
        institution_id=tenant_a_ctx["institution_id"],
        external_code="day9-foreign-teacher",
        display_name="Day9 Foreign Teacher",
    )
    session.add(foreign_teacher)
    session.flush()
    foreign_teacher_source = Source(
        organization_id=tenant_a_ctx["organization_id"],
        institution_id=tenant_a_ctx["institution_id"],
        teacher_id=foreign_teacher.id,
        source_type=SourceType.TEACHER_CONTENT.value,
        title="Day9 foreign teacher source",
        trust_tier=SourceTrustTier.TEACHER.value,
        status=SourceStatus.ACTIVE.value,
        metadata_json={"synthetic_fixture": True, "fixture_role": "day9_foreign_teacher"},
    )
    session.add_all([foreign_org_source, foreign_inst_source, foreign_teacher_source])
    session.flush()

    org_revision = _active_revision(
        foreign_org_source.id,
        _OFFICIAL_TEXT + " DAY9-ORG-B",
        revision_number=1,
        checksum_suffix="d9o",
    )
    inst_revision = _active_revision(
        foreign_inst_source.id,
        _OFFICIAL_TEXT + " DAY9-INST-B",
        revision_number=1,
        checksum_suffix="d9i",
    )
    teacher_revision = _active_revision(
        foreign_teacher_source.id,
        _OFFICIAL_TEXT + " DAY9-TEACHER-B",
        revision_number=1,
        checksum_suffix="d9t",
    )
    session.add_all([org_revision, inst_revision, teacher_revision])
    session.flush()
    session.commit()
    return Day9ForeignTenantContext(
        foreign_organization_revision_id=org_revision.id,
        foreign_institution_revision_id=inst_revision.id,
        foreign_teacher_revision_id=teacher_revision.id,
    )
