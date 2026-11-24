from __future__ import annotations

import hashlib
import json
import math
import re

from app.ca_imat_eapcet.contracts import QuestionRef
from app.ca_imat_eapcet.enums import IssueCode, PlanVerdict


def derive_content_fingerprint(
    *,
    stem_text: str,
    options: dict[str, str] | None,
    correct_key: str | None,
) -> str:
    payload = json.dumps(
        {"stem": stem_text.strip(), "options": options or {}, "key": correct_key or ""},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _independent_solve(stem_text: str, options: dict[str, str]) -> str | None:
    """Recompute correct option for authored synthetic stems (bounded set)."""

    stem = stem_text.strip()
    if stem.startswith("CA_QA:"):
        # "CA_QA: What is 15% of 203?"
        match = re.search(r"What is (\d+)% of (\d+)", stem)
        if match:
            pct, base = int(match.group(1)), int(match.group(2))
            target = str(int(base * pct / 100))
            for key, text in options.items():
                if text.strip() == target:
                    return key
    if stem.startswith("CA_BE:"):
        if "opportunity cost" in stem.lower():
            for key, text in options.items():
                if "value of the next best alternative" in text.lower():
                    return key
        if "law of demand" in stem.lower():
            for key, text in options.items():
                if text.strip().lower() == "falls":
                    return key
    if stem.startswith("IMAT_BIO:"):
        if "cellular respiration" in stem.lower():
            for key, text in options.items():
                if text.strip().lower() == "mitochondrion":
                    return key
    if stem.startswith("IMAT_MATH:"):
        match_m = re.search(r"Evaluate 3 \+ 7 \* 2 \+ (\d+)", stem)
        if match_m:
            target = str(17 + int(match_m.group(1)))
            for key, text in options.items():
                if text.strip() == target:
                    return key
    if stem.startswith("EAP_MAT:"):
        match_q = re.search(r"x\^2 - (\d+)x", stem)
        if match_q:
            target = match_q.group(1)
            for key, text in options.items():
                if text.strip() == target:
                    return key
    if stem.startswith("EAP_BOT:"):
        if "organelle" in stem.lower():
            for key, text in options.items():
                if text.strip() == "chloroplast":
                    return key
    if stem.startswith("EAP_ZOO:"):
        if "oxygen carriers" in stem.lower():
            for key, text in options.items():
                if text.strip() == "erythrocytes":
                    return key
    if stem.startswith("EAP_CHEM:"):
        if "negative charge" in stem.lower():
            for key, text in options.items():
                if text.strip() == "electron":
                    return key
    if stem.startswith("EAP_PHY:"):
        if "SI unit of force" in stem:
            for key, text in options.items():
                if text.strip() == "newton":
                    return key
    if stem.startswith("IMAT_READ:") or stem.startswith("IMAT_LOGIC:"):
        if "necessarily C" in stem:
            for key, text in options.items():
                if text.strip().lower() == "yes":
                    return key
    if stem.startswith("IMAT_CHEMISTRY:"):
        if "formula of water" in stem.lower():
            for key, text in options.items():
                if text.strip() == "H2O":
                    return key
    if stem.startswith("IMAT_PHYSICS:"):
        if "SI unit of force" in stem:
            for key, text in options.items():
                if text.strip() == "newton":
                    return key
    return None


def validate_and_bind_question_ref(
    question: QuestionRef,
    *,
    options_required: int,
) -> tuple[QuestionRef, PlanVerdict, list[IssueCode]]:
    """Content, fingerprint, and independent solver checks."""

    issues: list[IssueCode] = []
    if not question.stem_text or not question.stem_text.strip():
        issues.append(IssueCode.VALIDATION_NOT_PROVEN)
        return question, PlanVerdict.FAIL, issues

    if not question.options:
        issues.append(IssueCode.VALIDATION_NOT_PROVEN)
        return question, PlanVerdict.FAIL, issues

    if len(question.options) != options_required:
        issues.append(IssueCode.IMAT_DECIMAL_SCORING)
        return question, PlanVerdict.FAIL, issues

    texts = list(question.options.values())
    if len(set(t.strip().lower() for t in texts)) != len(texts):
        issues.append(IssueCode.VALIDATION_NOT_PROVEN)

    if not question.correct_key or question.correct_key not in question.options:
        issues.append(IssueCode.VALIDATION_NOT_PROVEN)
        return question, PlanVerdict.FAIL, issues

    expected_fp = derive_content_fingerprint(
        stem_text=question.stem_text,
        options=question.options,
        correct_key=question.correct_key,
    )
    if question.fingerprint != expected_fp:
        issues.append(IssueCode.FINGERPRINT_TAMPER)
        return question, PlanVerdict.FAIL, issues

    solved = _independent_solve(question.stem_text, question.options)
    if solved is None:
        return question, PlanVerdict.REVIEW_REQUIRED, issues + [IssueCode.SOLVER_EVIDENCE_MISSING]
    if solved != question.correct_key:
        issues.append(IssueCode.VALIDATION_NOT_PROVEN)
        return question, PlanVerdict.FAIL, issues

    if not math.isfinite(question.marks_if_correct) or question.marks_if_correct < 0:
        issues.append(IssueCode.VALIDATION_NOT_PROVEN)

    bound = question.model_copy(update={"independently_validated": True})
    if issues:
        return bound, PlanVerdict.REVIEW_REQUIRED, issues
    return bound, PlanVerdict.PASS, []