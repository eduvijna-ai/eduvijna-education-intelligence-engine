from __future__ import annotations

import hashlib

from app.ca_imat_eapcet.authority import (
    resolve_ca_authority,
    resolve_eapcet_authority,
    resolve_imat_authority,
)
from app.ca_imat_eapcet.constants import (
    CA_FOUNDATION_PACK_CODE,
    CA_PAPER_KIND,
    EAPCET_PACK_CODE,
    IMAT_PACK_CODE,
)
from app.ca_imat_eapcet.contracts import AllocateRequest, AllocateResult, QuestionRef
from app.ca_imat_eapcet.enums import (
    Day14ProfileKind,
    Day14SourceTrustMode,
    EapcetStream,
    IssueCode,
    PlanVerdict,
)
from app.ca_imat_eapcet.scope_guard import (
    validate_ca_pack,
    validate_ca_paper,
    validate_eapcet_pack,
    validate_imat_pack,
)
from app.ca_imat_eapcet.synthetic_fixtures import build_ca_pools, build_eapcet_pool, build_imat_pool
from app.ca_imat_eapcet.trust_guard import validate_trust_coherence


class Day14PracticeService:
    """D14 exact-count allocation across CA / IMAT / EAPCET synthetic pools."""

    def allocate(self, request: AllocateRequest) -> AllocateResult:
        issues: list[IssueCode] = []
        issues.extend(validate_trust_coherence(
            profile_kind=request.profile_kind,
            trust_mode=request.trust_mode,
            exam_family=request.exam_pack_code,
        ))

        pool: tuple[QuestionRef, ...] = ()
        if request.exam_pack_code == CA_FOUNDATION_PACK_CODE:
            issues.extend(validate_ca_pack(request.exam_pack_code))
            issues.extend(validate_ca_paper(request.paper_or_section))
            auth = resolve_ca_authority(
                profile_kind=request.profile_kind,
                session_code=request.session_code,
            )
            if auth.verdict and request.profile_kind is not Day14ProfileKind.SYNTHETIC_DEMO:
                return AllocateResult(
                    verdict=auth.verdict,
                    requested_count=request.requested_count,
                    delivered_count=0,
                    questions=[],
                    issue_codes=list(auth.issue_codes),
                    checksum="",
                )
            kind = CA_PAPER_KIND.get(request.paper_or_section, "objective")
            if kind == "descriptive":
                return AllocateResult(
                    verdict=PlanVerdict.REVIEW_REQUIRED,
                    requested_count=request.requested_count,
                    delivered_count=0,
                    questions=[],
                    issue_codes=[IssueCode.CA_DESCRIPTIVE_ON_OBJECTIVE],
                    checksum="",
                    metadata_json={
                        "note": "descriptive allocation uses rubric contract, not MCQ pool",
                    },
                )
            pools = build_ca_pools(per_paper=50)
            pool = pools.objective_by_paper.get(request.paper_or_section, ())

        elif request.exam_pack_code == IMAT_PACK_CODE:
            issues.extend(validate_imat_pack(request.exam_pack_code))
            auth = resolve_imat_authority(
                profile_kind=request.profile_kind,
                academic_year=request.academic_year,
            )
            if auth.verdict and request.profile_kind is not Day14ProfileKind.SYNTHETIC_DEMO:
                return AllocateResult(
                    verdict=auth.verdict,
                    requested_count=request.requested_count,
                    delivered_count=0,
                    questions=[],
                    issue_codes=list(auth.issue_codes),
                    checksum="",
                )
            pool = build_imat_pool()

        elif request.exam_pack_code == EAPCET_PACK_CODE:
            issues.extend(validate_eapcet_pack(request.exam_pack_code))
            stream = request.stream or EapcetStream.ENGINEERING
            auth = resolve_eapcet_authority(
                profile_kind=request.profile_kind,
                stream=stream,
                exam_year=request.academic_year,
            )
            if auth.verdict and request.profile_kind is not Day14ProfileKind.SYNTHETIC_DEMO:
                return AllocateResult(
                    verdict=auth.verdict,
                    requested_count=request.requested_count,
                    delivered_count=0,
                    questions=[],
                    issue_codes=list(auth.issue_codes),
                    checksum="",
                )
            pool = build_eapcet_pool(stream=stream.value)

        benign = (IssueCode.IMAT_COUNT_MISMATCH, IssueCode.EAPCET_COUNT_MISMATCH)
        if issues and any(c not in benign for c in issues):
            return AllocateResult(
                verdict=PlanVerdict.FAIL,
                requested_count=request.requested_count,
                delivered_count=0,
                questions=[],
                issue_codes=issues,
                checksum="",
            )

        delivered = list(pool[: request.requested_count])
        fingerprints = {q.fingerprint for q in delivered}
        if len(fingerprints) != len(delivered):
            issues.append(IssueCode.DUPLICATE_QUESTION)

        if len(delivered) < request.requested_count:
            verdict = PlanVerdict.SHORTAGE
            issues.append(
                IssueCode.IMAT_COUNT_MISMATCH
                if request.exam_pack_code == IMAT_PACK_CODE
                else IssueCode.EAPCET_COUNT_MISMATCH
                if request.exam_pack_code == EAPCET_PACK_CODE
                else IssueCode.CA_ACCOUNTING_RECONCILE
            )
        else:
            verdict = PlanVerdict.PASS

        checksum = hashlib.sha256(
            "|".join(q.fingerprint for q in delivered).encode()
        ).hexdigest()[:32]

        return AllocateResult(
            verdict=verdict,
            requested_count=request.requested_count,
            delivered_count=len(delivered),
            questions=delivered,
            issue_codes=list(dict.fromkeys(issues)),
            checksum=checksum,
            metadata_json={
                "demonstration_only": request.trust_mode is Day14SourceTrustMode.SYNTHETIC_FIXTURE,
                "validated_persisted_synthetic": False,
            },
        )