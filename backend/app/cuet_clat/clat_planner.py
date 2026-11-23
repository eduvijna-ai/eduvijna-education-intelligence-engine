from __future__ import annotations

import hashlib
import json
import threading

from app.cuet_clat.authority import resolve_clat_authority
from app.cuet_clat.constants import (
    CLAT_SECTION_RANGES,
    CLAT_TOTAL_MINUTES,
    CLAT_TOTAL_QUESTIONS,
)
from app.cuet_clat.contracts import (
    ClatPaperPlanRequest,
    ClatPaperPlanResult,
    ClatSectionAllocation,
    PassageCluster,
    PracticeQuestionRef,
    resolve_academic_year_string,
    validate_academic_year_explicit,
)
from app.cuet_clat.enums import CuetClatSourceTrustMode, IssueCode, PlanVerdict
from app.cuet_clat.passage_clusters import build_passage_clusters
from app.cuet_clat.replay_store import ReplayAcquireStatus, ReplayStore
from app.cuet_clat.scope_guard import validate_clat_pack, validate_tenant
from app.cuet_clat.section_allocator import allocate_clat_sections
from app.cuet_clat.synthetic_fixtures import build_clat_question
from app.cuet_clat.trust_guard import validate_trust_coherence


def build_clat_replay_fingerprint(
    request: ClatPaperPlanRequest,
    section_allocations: dict[str, int],
) -> str:
    """Immutable binding for in-process synthetic replay only."""

    overrides = request.section_overrides
    payload = {
        "exam_pack_code": request.exam_pack_code,
        "organization_id": request.organization_id or "",
        "institution_id": request.metadata_json.get("institution_id", ""),
        "academic_year": request.academic_year,
        "profile_kind": request.profile_kind.value,
        "trust_mode": request.trust_mode.value,
        "section_allocations": dict(sorted(section_allocations.items())),
        "section_overrides": dict(sorted(overrides.items())) if overrides else None,
        "tenant_scoped": bool(request.metadata_json.get("tenant_scoped")),
    }
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:40]


class ClatPaperPlanner:
    """D13-15..24: CLAT 120-question paper with section ranges and passage clusters."""

    def __init__(self, *, replay_store: ReplayStore | None = None) -> None:
        self._replay = replay_store or ReplayStore()
        self.synthetic_generation_count = 0

    def plan(self, request: ClatPaperPlanRequest) -> ClatPaperPlanResult:
        year_issues = validate_academic_year_explicit(request)
        if year_issues:
            return self._fail(request, _dedupe(year_issues), PlanVerdict.FAIL)

        academic_year = resolve_academic_year_string(request)

        issues = list(validate_clat_pack(request.exam_pack_code))
        issues.extend(
            validate_trust_coherence(
                profile_kind=request.profile_kind,
                trust_mode=request.trust_mode,
                academic_year=academic_year,
                exam_family="clat",
            )
        )
        if request.metadata_json.get("tenant_scoped"):
            issues.extend(validate_tenant(request.organization_id, required=True))

        if request.metadata_json.get("forged_citation"):
            issues.append(IssueCode.FORGED_CITATION)
        if request.metadata_json.get("stale_current_affairs"):
            issues.append(IssueCode.STALE_CURRENT_AFFAIRS)
        if request.metadata_json.get("passage_answer_mismatch"):
            issues.append(IssueCode.PASSAGE_ANSWER_MISMATCH)

        authority = resolve_clat_authority(
            profile_kind=request.profile_kind,
            academic_year=academic_year,
        )

        forced_count = request.metadata_json.get("forced_total_questions")
        if isinstance(forced_count, int) and forced_count != CLAT_TOTAL_QUESTIONS:
            issues.append(IssueCode.CLAT_COUNT_MISMATCH)

        if request.trust_mode is not CuetClatSourceTrustMode.SYNTHETIC_FIXTURE:
            if authority.verdict is not None:
                return self._fail(
                    request, _dedupe([*issues, *authority.issue_codes]), authority.verdict
                )
            return self._fail(
                request,
                _dedupe([*issues, IssueCode.UNAPPROVED_SOURCE]),
                PlanVerdict.SOURCE_PENDING,
            )

        if authority.verdict is not None:
            return self._fail(
                request,
                _dedupe([*issues, *authority.issue_codes]),
                authority.verdict,
            )

        if issues:
            return self._fail(request, _dedupe(issues), PlanVerdict.FAIL)

        alloc = allocate_clat_sections(section_overrides=request.section_overrides)
        if alloc.verdict is not PlanVerdict.PASS:
            return self._fail(request, _dedupe([*issues, *alloc.issue_codes]), alloc.verdict)

        fingerprint = build_clat_replay_fingerprint(request, alloc.allocations)
        replay_key = request.replay_idempotency_key
        raw_wait = request.metadata_json.get("replay_wait_timeout", 30.0)
        replay_wait = float(raw_wait) if isinstance(raw_wait, (int, float, str)) else 30.0
        generation_token: str | None = None
        generation_owned = False

        try:
            if replay_key:
                acquired = self._replay.acquire(replay_key, fingerprint, wait_timeout=replay_wait)
                if acquired.status is ReplayAcquireStatus.WAIT_TIMEOUT:
                    return self._fail(
                        request,
                        [IssueCode.REPLAY_WAIT_TIMEOUT],
                        PlanVerdict.REVIEW_REQUIRED,
                    )
                if acquired.status is ReplayAcquireStatus.STALE_REPLAY:
                    return self._fail(request, [IssueCode.STALE_REPLAY], PlanVerdict.FAIL)
                if acquired.status is ReplayAcquireStatus.CACHE_HIT and acquired.result_payload:
                    return self._hydrate_cached(acquired.result_payload)
                if acquired.status is ReplayAcquireStatus.GENERATE:
                    generation_owned = True
                    generation_token = acquired.generation_token

                started = request.metadata_json.get("owner_started_event")
                if generation_owned and isinstance(started, threading.Event):
                    started.set()
                pause = request.metadata_json.get("owner_pause_event")
                if generation_owned and isinstance(pause, threading.Event):
                    raw_pause = request.metadata_json.get("owner_pause_timeout", 5.0)
                    pause_timeout = (
                        float(raw_pause) if isinstance(raw_pause, (int, float, str)) else 5.0
                    )
                    pause.wait(timeout=pause_timeout)

            all_questions, all_clusters, section_rows = self._assemble(
                alloc.allocations,
                simulate_failure=bool(request.metadata_json.get("simulate_generation_failure")),
                simulate_value_error=bool(request.metadata_json.get("simulate_value_error")),
            )

            if request.metadata_json.get("simulate_post_assembly_failure"):
                msg = "simulated_post_assembly_failure"
                raise OSError(msg)

            self.synthetic_generation_count += 1

            ids = [q.question_id for q in all_questions]
            if len(set(ids)) != len(ids):
                return self._fail(request, [IssueCode.DUPLICATE_QUESTION], PlanVerdict.FAIL)

            result = ClatPaperPlanResult(
                verdict=PlanVerdict.PASS,
                total_questions=len(all_questions),
                duration_minutes=CLAT_TOTAL_MINUTES,
                section_allocations=section_rows,
                passage_clusters=all_clusters,
                questions=all_questions,
                issue_codes=[],
                checksum=_checksum(all_questions, all_clusters),
                metadata_json={
                    "demonstration_only": True,
                    "scoring_profile": "+1/-0.25/0-blank",
                    "current_affairs_rag_mode": "synthetic_fixture",
                    "replay_mode": "in_process_synthetic_only",
                    "synthetic_generation_count": self.synthetic_generation_count,
                },
            )

            if replay_key:
                if request.metadata_json.get("simulate_publish_failure"):
                    msg = "simulated_publish_failure"
                    raise OSError(msg)

                published = self._replay.publish(
                    replay_key,
                    fingerprint,
                    result.model_dump(),
                    generation_token=generation_token,
                )
                if not published:
                    retry = self._replay.acquire(replay_key, fingerprint, wait_timeout=replay_wait)
                    if retry.status is ReplayAcquireStatus.WAIT_TIMEOUT:
                        return self._fail(
                            request,
                            [IssueCode.REPLAY_WAIT_TIMEOUT],
                            PlanVerdict.REVIEW_REQUIRED,
                        )
                    if (
                        retry.status is ReplayAcquireStatus.CACHE_HIT
                        and retry.result_payload is not None
                    ):
                        generation_owned = False
                        return self._hydrate_cached(retry.result_payload)
                    return self._fail(request, [IssueCode.STALE_REPLAY], PlanVerdict.FAIL)
                generation_owned = False

            return result
        except BaseException as exc:
            if replay_key and generation_owned and generation_token:
                self._replay.abort_generation(
                    replay_key,
                    fingerprint,
                    generation_token=generation_token,
                )
            if isinstance(exc, RuntimeError) and request.metadata_json.get(
                "simulate_generation_failure"
            ):
                return self._fail(request, [IssueCode.STALE_REPLAY], PlanVerdict.FAIL)
            if isinstance(exc, ValueError):
                return self._fail(request, [IssueCode.CLAT_COUNT_MISMATCH], PlanVerdict.FAIL)
            simulated = request.metadata_json.get("simulate_post_assembly_failure") or (
                request.metadata_json.get("simulate_publish_failure")
            )
            if isinstance(exc, OSError) and simulated:
                return self._fail(request, [IssueCode.STALE_REPLAY], PlanVerdict.REVIEW_REQUIRED)
            raise

    def _hydrate_cached(self, payload: dict[str, object]) -> ClatPaperPlanResult:
        cached = ClatPaperPlanResult.model_validate(payload)
        cached.metadata_json = {
            **cached.metadata_json,
            "replay_mode": "in_process_synthetic_only",
            "synthetic_generation_count": self.synthetic_generation_count,
        }
        return cached

    def _assemble(
        self,
        allocations: dict[str, int],
        *,
        simulate_failure: bool = False,
        simulate_value_error: bool = False,
    ) -> tuple[list[PracticeQuestionRef], list[PassageCluster], list[ClatSectionAllocation]]:
        if simulate_failure:
            raise RuntimeError("simulated_generation_failure")
        if simulate_value_error:
            msg = "simulated_value_error"
            raise ValueError(msg)
        all_questions: list[PracticeQuestionRef] = []
        all_clusters: list[PassageCluster] = []
        section_rows: list[ClatSectionAllocation] = []

        for section_code, count in allocations.items():
            section_qs = [
                build_clat_question(section_code=section_code, index=i, passage_id=None)
                for i in range(count)
            ]
            clusters = build_passage_clusters(section_code, section_qs)
            all_clusters.extend(clusters)
            all_questions.extend(section_qs)
            lo, hi = CLAT_SECTION_RANGES[section_code]
            section_rows.append(
                ClatSectionAllocation(
                    section_code=section_code,
                    question_count=count,
                    min_allowed=lo,
                    max_allowed=hi,
                )
            )

        if len(all_questions) != CLAT_TOTAL_QUESTIONS:
            msg = f"expected {CLAT_TOTAL_QUESTIONS} assembled, got {len(all_questions)}"
            raise ValueError(msg)

        return all_questions, all_clusters, section_rows

    def _fail(
        self,
        request: ClatPaperPlanRequest,
        issues: list[IssueCode],
        verdict: PlanVerdict,
    ) -> ClatPaperPlanResult:
        _ = request
        return ClatPaperPlanResult(
            verdict=verdict,
            total_questions=0,
            duration_minutes=CLAT_TOTAL_MINUTES,
            section_allocations=[],
            passage_clusters=[],
            questions=[],
            issue_codes=issues,
            checksum="",
            metadata_json={
                "demonstration_only": True,
                "replay_mode": "in_process_synthetic_only",
            },
        )


def _dedupe(issues: list[IssueCode]) -> list[IssueCode]:
    seen: set[IssueCode] = set()
    ordered: list[IssueCode] = []
    for code in issues:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered


def _checksum(
    questions: list[PracticeQuestionRef],
    clusters: list[PassageCluster],
) -> str:
    payload = json.dumps(
        {
            "q": [q.model_dump() for q in questions],
            "c": [c.model_dump() for c in clusters],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:40]