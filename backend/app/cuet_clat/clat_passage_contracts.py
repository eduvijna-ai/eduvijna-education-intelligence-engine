"""F03-B: contracts for CLAT original synthetic passage-grounded examples."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, Field

from app.cuet_clat.constants import CLAT_MARK_CORRECT, CLAT_MARK_INCORRECT
from app.cuet_clat.contracts import PassageCluster, PracticeQuestionRef
from app.cuet_clat.enums import PlanVerdict

CLAT_ORIGINAL_SOURCE_MODE = "eduvijna_original_synthetic_test_only"
CLAT_PASSAGE_HARNESS_TOKEN = "validated_clat_original_passage_examples"


class ClatPassageIssueCode(StrEnum):
    WRONG_PASSAGE = "d13.clat.f03b.wrong_passage"
    WRONG_PASSAGE_ID = "d13.clat.f03b.wrong_passage_id"
    ANSWER_KEY_TAMPER = "d13.clat.f03b.answer_key_tamper"
    DUPLICATE_OPTION = "d13.clat.f03b.duplicate_option"
    BLANK_OPTION = "d13.clat.f03b.blank_option"
    MULTIPLE_CORRECT = "d13.clat.f03b.multiple_correct_options"
    DUPLICATE_QUESTION = "d13.clat.f03b.duplicate_question"
    DUPLICATE_PASSAGE = "d13.clat.f03b.duplicate_passage"
    PASSAGE_MISMATCH = "d13.clat.f03b.passage_cluster_mismatch"
    CROSS_SECTION = "d13.clat.f03b.cross_section_cluster"
    INDEPENDENT_FAIL = "d13.clat.f03b.independent_check_fail"
    UNSUPPORTED_INFERENCE = "d13.clat.f03b.unsupported_inference"
    CONTENT_FINGERPRINT_STALE = "d13.clat.f03b.stale_fingerprint"
    HARNESS_UNAUTHORIZED = "d13.clat.f03b.harness_unauthorized"
    CURRENT_AFFAIRS_NOT_READY = "d13.clat.f03b.current_affairs_source_pending"


class ClatIndependentVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW_REQUIRED = "review_required"


class ClatAuthoredMcq(BaseModel):
    question_id: str
    passage_id: str
    section_code: str
    stem_text: str
    options: dict[str, str]
    author_key: str
    explanation: str = ""


class ClatOriginalPassage(BaseModel):
    passage_id: str
    section_code: str
    passage_text: str
    questions: list[ClatAuthoredMcq] = Field(default_factory=list)
    source_mode: str = CLAT_ORIGINAL_SOURCE_MODE

    def passage_fingerprint(self) -> str:
        payload = {
            "passage_id": self.passage_id,
            "section_code": self.section_code,
            "source_mode": self.source_mode,
            "text": self.passage_text,
        }
        raw = json.dumps(payload, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()[:40]


def question_content_fingerprint(question: ClatAuthoredMcq) -> str:
    payload = {
        "passage_id": question.passage_id,
        "section": question.section_code,
        "stem": question.stem_text,
        "options": dict(sorted(question.options.items())),
        "key": question.author_key,
    }
    raw = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:40]


class ClatIndependentCheckResult(BaseModel):
    verdict: ClatIndependentVerdict
    derived_key: str | None = None
    anchor_quote: str = ""
    proof_steps: list[str] = Field(default_factory=list)
    reason: str | None = None


class ClatValidatedQuestionRecord(BaseModel):
    question: PracticeQuestionRef
    passage_id: str
    section_code: str
    independent: ClatIndependentCheckResult
    content_fingerprint: str


class ClatValidatedExamplesResult(BaseModel):
    verdict: PlanVerdict
    harness_authorized: bool
    official_source_verified: bool = False
    demonstration_only: bool = False
    item_count: int = 0
    passage_count: int = 0
    passages: list[ClatOriginalPassage] = Field(default_factory=list)
    passage_clusters: list[PassageCluster] = Field(default_factory=list)
    questions: list[ClatValidatedQuestionRecord] = Field(default_factory=list)
    issue_codes: list[ClatPassageIssueCode] = Field(default_factory=list)
    metadata_json: dict[str, object] = Field(default_factory=dict)


def authored_to_practice_ref(question: ClatAuthoredMcq) -> PracticeQuestionRef:
    return PracticeQuestionRef(
        question_id=question.question_id,
        subject_code=question.section_code,
        passage_id=question.passage_id,
        fingerprint=question_content_fingerprint(question),
        correct_key=question.author_key,
        marks_if_correct=CLAT_MARK_CORRECT,
        marks_if_incorrect=CLAT_MARK_INCORRECT,
        stem_text=question.stem_text,
        options=dict(question.options),
        independently_validated=False,
    )