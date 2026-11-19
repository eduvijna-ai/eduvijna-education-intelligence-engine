"""Canonical persisted Question fingerprint for Day6 validation binding."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.models import Question


def question_content_fingerprint(question: Question) -> str:
    options: list[dict[str, Any]] = [
        {
            "key": opt.option_key,
            "text": opt.text,
            "correct": bool(opt.is_correct),
            "sequence": opt.sequence,
        }
        for opt in sorted(question.options, key=lambda row: row.sequence)
    ]
    payload = {
        "stem_text": question.stem_text,
        "answer_json": question.answer_json or {},
        "options": options,
        "content_version": question.content_version,
        "question_type": question.question_type,
        "exam_version_id": question.exam_version_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()