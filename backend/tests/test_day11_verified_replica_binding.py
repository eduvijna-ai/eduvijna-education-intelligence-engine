from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.jee_main_exam_intelligence.blueprint_snapshot import VerifiedBlueprintSnapshot
from app.jee_main_exam_intelligence.contracts import OfficialSourceRegistrationRef
from app.jee_main_exam_intelligence.enums import (
    OfficialPatternAuthorityStatus,
    PaperPlanIssueCode,
    PaperPlanVerdict,
)
from app.jee_main_exam_intelligence.fixtures import (
    build_official_replica_request,
    seed_day11_fixture_context,
)
from app.jee_main_exam_intelligence.planner import _plan_official_replica


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _verified_source_refs(*, syllabus_verified: bool = True) -> list[OfficialSourceRegistrationRef]:
    return [
        OfficialSourceRegistrationRef(
            source_code="nta-2027-bulletin",
            revision_id="curated-bulletin-rev",
            candidate_url="https://jeemain.nta.nic.in/documents/",
            revision_status="active",
            checksum_sha256=None,
            verified_for_official_pattern=True,
        ),
        OfficialSourceRegistrationRef(
            source_code="nta-2027-syllabus",
            revision_id="curated-syllabus-rev",
            candidate_url="https://jeemain.nta.nic.in/documents/",
            revision_status="active",
            checksum_sha256=None,
            verified_for_official_pattern=syllabus_verified,
        ),
    ]


def _source_pinned_snapshot() -> VerifiedBlueprintSnapshot:
    # Synthetic test-only rules for checking planner wiring. These are not an
    # NTA 2027 approval or a statement that the real paper uses 78 questions.
    return VerifiedBlueprintSnapshot(
        total_questions=78,
        total_marks=312.0,
        duration_minutes=180,
        marks_correct=4.0,
        marks_incorrect=-1.0,
        marks_unattempted=0.0,
        per_subject_exact=26,
        section_a_mcq=20,
        section_b_numerical=6,
        blueprint_rule_ids=("fixture-rule-1",),
        source_revision_ids=("curated-bulletin-rev", "curated-syllabus-rev"),
    )


def test_official_replica_pool_requires_authoritative_pinned_sources() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        request = build_official_replica_request(ctx).model_copy(
            update={
                "execution_mode": TrustExecutionMode.PRODUCTION,
                "allowed_source_revision_ids": [],
            }
        )
        with (
            patch(
                "app.jee_main_exam_intelligence.planner.load_production_blueprint_snapshot",
                return_value=_source_pinned_snapshot(),
            ),
            patch(
                "app.jee_main_exam_intelligence.planner.load_validated_questions",
                return_value=([], []),
            ) as fake_pool,
        ):
            result = _plan_official_replica(
                session,
                request,
                ctx["exam_version_2027_id"],
                OfficialPatternAuthorityStatus.VERIFIED,
                _verified_source_refs(),
                [],
            )
        assert result.verdict == PaperPlanVerdict.FAIL
        assert PaperPlanIssueCode.INSUFFICIENT_VALIDATED_POOL in result.issue_codes
        assert result.requested_count == 78  # Source-backed, not candidate 75.
        assert fake_pool.call_count == 6  # Three subjects x two question types.
        for call in fake_pool.call_args_list:
            assert call.kwargs["allowed_source_revision_ids"] == [
                "curated-bulletin-rev",
                "curated-syllabus-rev",
            ]


def test_official_replica_rejects_incomplete_curator_source_claims() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        request = build_official_replica_request(ctx).model_copy(
            update={"execution_mode": TrustExecutionMode.PRODUCTION}
        )
        with (
            patch(
                "app.jee_main_exam_intelligence.planner.load_production_blueprint_snapshot",
                return_value=_source_pinned_snapshot(),
            ),
            patch(
                "app.jee_main_exam_intelligence.planner.load_validated_questions",
                return_value=([], []),
            ) as fake_pool,
        ):
            result = _plan_official_replica(
                session,
                request,
                ctx["exam_version_2027_id"],
                OfficialPatternAuthorityStatus.VERIFIED,
                _verified_source_refs(syllabus_verified=False),
                [],
            )
        assert result.verdict == PaperPlanVerdict.FAIL
        assert PaperPlanIssueCode.OFFICIAL_SOURCE_NOT_VERIFIED in result.issue_codes
        fake_pool.assert_not_called()
