"""Author draft canonicalization and binding to persisted Questions (Issue #50)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.models import Question


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def display_candidate_from_question(question: Question) -> dict[str, Any]:
    options = [
        {
            "option_key": opt.option_key,
            "text": _normalize_ws(opt.text),
            "sequence": opt.sequence,
        }
        for opt in sorted(question.options, key=lambda row: row.sequence)
    ]
    return {
        "stem_text": _normalize_ws(question.stem_text or ""),
        "question_type": str(question.question_type or "").lower(),
        "options": options,
    }


def redact_author_for_solver(author_parsed: dict[str, Any]) -> dict[str, Any]:
    """Answer-blind candidate for the SOLVER gateway only."""

    options: list[dict[str, Any]] = []
    for raw in list(author_parsed.get("options") or []):
        if not isinstance(raw, dict):
            continue
        options.append(
            {
                "option_key": str(raw.get("option_key") or ""),
                "text": _normalize_ws(str(raw.get("text") or "")),
                "sequence": raw.get("sequence"),
            }
        )
    options.sort(key=lambda row: (row.get("sequence") or 0, row.get("option_key") or ""))
    return {
        "stem_text": _normalize_ws(str(author_parsed.get("stem_text") or "")),
        "question_type": str(author_parsed.get("question_type") or "").lower(),
        "options": options,
    }


def author_visible_fingerprint(author_parsed: dict[str, Any]) -> str:
    visible = redact_author_for_solver(author_parsed)
    encoded = json.dumps(visible, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def question_visible_fingerprint(question: Question) -> str:
    return author_visible_fingerprint(display_candidate_from_question(question))


def author_claimed_answer_key(
    author_parsed: dict[str, Any],
) -> tuple[str | None, tuple[str, ...]]:
    """Extract exactly one authoritative author answer claim."""

    issues: list[str] = []
    options = [o for o in list(author_parsed.get("options") or []) if isinstance(o, dict)]
    flagged = [
        str(o.get("option_key") or "").strip()
        for o in options
        if bool(o.get("is_correct"))
    ]
    flagged = [k for k in flagged if k]
    explicit_key = ""
    answer_json = author_parsed.get("answer_json")
    if isinstance(answer_json, dict):
        explicit_key = str(answer_json.get("option_key") or "").strip()
    proposed = str(author_parsed.get("proposed_answer_key") or "").strip()

    if len(flagged) > 1:
        issues.append("author_answer_ambiguous")
    if len(flagged) == 0 and not explicit_key and not proposed:
        issues.append("author_answer_missing")
        return None, tuple(issues)

    key_from_flags = flagged[0] if len(flagged) == 1 else None
    candidates = {k for k in (key_from_flags, explicit_key, proposed) if k}
    if len(candidates) > 1:
        issues.append("author_answer_mismatch")
        return None, tuple(issues)
    if not candidates:
        issues.append("author_answer_missing")
        return None, tuple(issues)
    return next(iter(candidates)), tuple(issues)


def author_draft_matches_question(
    author_parsed: dict[str, Any],
    question: Question,
) -> tuple[bool, tuple[str, ...]]:
    issues: list[str] = []
    bound_id = str(author_parsed.get("item_id") or "").strip()
    if not bound_id:
        issues.append("generated_draft_not_bound")
    elif bound_id != str(question.id):
        issues.append("author_item_id_mismatch")
    author_fp = author_visible_fingerprint(author_parsed)
    question_fp = question_visible_fingerprint(question)
    if author_fp != question_fp:
        issues.append("author_draft_content_mismatch")
    return (not issues, tuple(issues))


def solver_payload_has_answer_leak(user_payload: dict[str, object]) -> bool:
    banned_keys = {
        "expected_answer_key",
        "correct_answer",
        "answer_json",
        "solution",
        "is_correct",
        "stored_answer_key",
    }

    def walk(value: object, depth: int) -> bool:
        if depth > 8:
            return False
        if isinstance(value, dict):
            for key, child in value.items():
                low = str(key).lower()
                if low in banned_keys or low.endswith("_is_correct"):
                    return True
                if walk(child, depth + 1):
                    return True
        elif isinstance(value, list):
            for child in value:
                if walk(child, depth + 1):
                    return True
        return False

    return walk(user_payload, 0)