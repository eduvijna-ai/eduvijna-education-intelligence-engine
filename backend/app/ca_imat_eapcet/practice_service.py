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
    IMAT_OPTIONS_PER_QUESTION,
    IMAT_PACK_CODE,
)
from app.ca_imat_eapcet.content_validation import validate_and_bind_question_ref
from app.ca_imat_eapcet.contracts import AllocateRequest, AllocateResult, QuestionRef
from app.ca_imat_eapcet.enums import (
    Day14ProfileKind,
    Day14SourceTrustMode,
    EapcetStream,
    IssueCode,
    PlanVerdict,
)
from app.ca_imat_eapcet.request_guards import (
    validate_organization_required,
    validate_profile_trust_matrix,
    validate_requested_count,
)
from app.ca_imat_eapcet.scope_guard import (
    validate_ca_pack,
    validate_ca_paper,
    validate_eapcet_pack,
    validate_imat_pack,
)
from app.ca_imat_eapcet.synthetic_fixtures import (
    build_ca_pools,
    build_eapcet_pool,
    build_imat_pool,
    filter_pool,
)
from app.ca_imat_eapcet.trust_guard import validate_trust_coherence
from app.ca_imat_eapcet.verdict_combine import combine_verdicts


def _options_required(exam_pack_code: str) -> int:
    if exam_pack_code == IMAT_PACK_CODE:
        return IMAT_OPTIONS_PER_QUESTION
    return 4


class Day14PracticeService:
    """D14 exact-count allocation with validated content only."""

    def allocate(self, request: AllocateRequest) -> AllocateResult:
        issues: list[IssueCode] = []
        issues.extend(validate_requested_count(request.requested_count))
        issues.extend(
            validate_profile_trust_matrix(
                exam_pack_code=request.exam_pack_code,
                profile_kind=request.profile_kind,
                trust_mode=request.trust_mode,
            )
        )
        issues.extend(
            validate_organization_required(
                profile_kind=request.profile_kind,
                organization_id=request.organization_id,
            )
        )
        issues.extend(
            validate_trust_coherence(
                profile_kind=request.profile_kind,
                trust_mode=request.trust_mode,
                exam_family=request.exam_pack_code,
            )
        )
        if issues:
            return AllocateResult(
                verdict=PlanVerdict.FAIL,
                requested_count=request.requested_count,
                delivered_count=0,
                questions=[],
                issue_codes=list(dict.fromkeys(issues)),
                checksum="",
            )

        pool: tuple[QuestionRef, ...] = ()

        if request.exam_pack_code == CA_FOUNDATION_PACK_CODE:
            issues.extend(validate_ca_pack(request.exam_pack_code))
            issues.extend(validate_ca_paper(request.paper_or_section))
            auth = resolve_ca_authority(
                profile_kind=request.profile_kind,
                session_code=request.session_code,
            )
            if request.profile_kind is not Day14ProfileKind.SYNTHETIC_DEMO:
                if auth.verdict:
                    return AllocateResult(
                        verdict=auth.verdict,
                        requested_count=request.requested_count,
                        delivered_count=0,
                        questions=[],
                        issue_codes=list(auth.issue_codes),
                        checksum="",
                        metadata_json={"official_path_blocked": True},
                    )
                return AllocateResult(
                    verdict=PlanVerdict.NOT_READY,
                    requested_count=request.requested_count,
                    delivered_count=0,
                    questions=[],
                    issue_codes=list(auth.issue_codes),
                    checksum="",
                )
            kind = CA_PAPER_KIND.get(request.paper_or_section)
            if kind is None:
                issues.append(IssueCode.WRONG_PAPER)
            elif kind == "descriptive":
                return AllocateResult(
                    verdict=PlanVerdict.REVIEW_REQUIRED,
                    requested_count=request.requested_count,
                    delivered_count=0,
                    questions=[],
                    issue_codes=[IssueCode.CA_DESCRIPTIVE_ON_OBJECTIVE],
                    checksum="",
                    metadata_json={"descriptive_practice_via_contract": True},
                )
            pools = build_ca_pools(per_paper=50)
            pool = pools.objective_by_paper.get(request.paper_or_section, ())

        elif request.exam_pack_code == IMAT_PACK_CODE:
            issues.extend(validate_imat_pack(request.exam_pack_code))
            auth = resolve_imat_authority(
                profile_kind=request.profile_kind,
                academic_year=request.academic_year,
            )
            if request.profile_kind is not Day14ProfileKind.SYNTHETIC_DEMO:
                if auth.verdict:
                    return AllocateResult(
                        verdict=auth.verdict,
                        requested_count=request.requested_count,
                        delivered_count=0,
                        questions=[],
                        issue_codes=list(auth.issue_codes),
                        checksum="",
                    )
                return AllocateResult(
                    verdict=PlanVerdict.NOT_READY,
                    requested_count=0,
                    delivered_count=0,
                    questions=[],
                    issue_codes=list(auth.issue_codes),
                    checksum="",
                )
            pool = filter_pool(
                build_imat_pool(),
                paper_or_section=request.paper_or_section,
                topic_code=request.topic_code,
            )

        elif request.exam_pack_code == EAPCET_PACK_CODE:
            issues.extend(validate_eapcet_pack(request.exam_pack_code))
            stream = request.stream or EapcetStream.ENGINEERING
            auth = resolve_eapcet_authority(
                profile_kind=request.profile_kind,
                stream=stream,
                exam_year=request.academic_year,
            )
            if request.profile_kind is not Day14ProfileKind.SYNTHETIC_DEMO:
                if auth.verdict:
                    return AllocateResult(
                        verdict=auth.verdict,
                        requested_count=request.requested_count,
                        delivered_count=0,
                        questions=[],
                        issue_codes=list(auth.issue_codes),
                        checksum="",
                    )
                return AllocateResult(
                    verdict=PlanVerdict.NOT_READY,
                    requested_count=request.requested_count,
                    delivered_count=0,
                    questions=[],
                    issue_codes=list(auth.issue_codes),
                    checksum="",
                )
            pool = filter_pool(
                build_eapcet_pool(stream=stream.value),
                paper_or_section=request.paper_or_section,
                topic_code=request.topic_code,
            )
        else:
            issues.append(IssueCode.WRONG_EXAM_PACK)

        if issues and any(
            c
            not in (
                IssueCode.IMAT_COUNT_MISMATCH,
                IssueCode.EAPCET_COUNT_MISMATCH,
                IssueCode.MISSING_TOPIC_SCOPE,
            )
            for c in issues
        ):
            return AllocateResult(
                verdict=PlanVerdict.FAIL,
                requested_count=request.requested_count,
                delivered_count=0,
                questions=[],
                issue_codes=list(dict.fromkeys(issues)),
                checksum="",
            )

        topic = request.metadata_json.get("topic_code") if request.metadata_json else None
        if isinstance(topic, str) and topic and not pool:
            issues.append(IssueCode.MISSING_TOPIC_SCOPE)

        raw = list(pool[: request.requested_count])
        validated: list[QuestionRef] = []
        item_verdicts: list[PlanVerdict] = []
        seen_fp: set[str] = set()
        opt_n = _options_required(request.exam_pack_code)
        for q in raw:
            bound, v, v_issues = validate_and_bind_question_ref(q, options_required=opt_n)
            issues.extend(v_issues)
            item_verdicts.append(v)
            if v is PlanVerdict.PASS:
                if bound.fingerprint in seen_fp:
                    issues.append(IssueCode.DUPLICATE_QUESTION)
                else:
                    seen_fp.add(bound.fingerprint)
                    validated.append(bound)

        validated_count = len(validated)
        if len(raw) < request.requested_count:
            issues.append(
                IssueCode.EAPCET_COUNT_MISMATCH
                if request.exam_pack_code == EAPCET_PACK_CODE
                else IssueCode.IMAT_COUNT_MISMATCH
                if request.exam_pack_code == IMAT_PACK_CODE
                else IssueCode.CA_ACCOUNTING_RECONCILE
            )
            shortage_verdict = PlanVerdict.SHORTAGE
        else:
            shortage_verdict = None

        if validated_count == request.requested_count:
            content_verdict = PlanVerdict.PASS
        elif validated_count == 0:
            content_verdict = (
                combine_verdicts(*item_verdicts) if item_verdicts else PlanVerdict.FAIL
            )
        else:
            content_verdict = PlanVerdict.REVIEW_REQUIRED

        verdict = combine_verdicts(
            shortage_verdict or PlanVerdict.PASS,
            content_verdict,
        )

        checksum = hashlib.sha256(
            "|".join(q.fingerprint for q in validated).encode()
        ).hexdigest()[:32]

        return AllocateResult(
            verdict=verdict,
            requested_count=request.requested_count,
            delivered_count=validated_count,
            questions=validated,
            issue_codes=list(dict.fromkeys(issues)),
            checksum=checksum,
            metadata_json={
                "demonstration_only": request.trust_mode is Day14SourceTrustMode.SYNTHETIC_FIXTURE,
                "structural_candidates_considered": len(raw),
                "independently_validated_count": validated_count,
                "structural_demonstration_only": validated_count < request.requested_count,
            },
        )