"""Bind gateway author/solver output to persisted approved questions."""

from __future__ import annotations

from app.jee_advanced.author_draft_binding import (
    author_claimed_answer_key,
    author_draft_matches_question,
)
from app.jee_advanced.orchestration_chain import OrchestrationChainResult
from app.jee_advanced.stored_answer_resolution import stored_mcq_correct_keys
from app.models import Question


def stored_mcq_answer_key(question: Question) -> str | None:
    keys = stored_mcq_correct_keys(question)
    if len(keys) == 1:
        return next(iter(keys))
    return None


def bind_chain_to_persisted_question(
    chain: OrchestrationChainResult,
    question: Question,
) -> tuple[bool, tuple[str, ...]]:
    issues: list[str] = []
    qid = str(question.id)
    if chain.item_id != qid:
        issues.append("chain_item_id_mismatch")
    expected = stored_mcq_answer_key(question)
    proposed = (chain.proposed_answer_key or "").strip()
    if not expected:
        issues.append("stored_answer_key_missing")
    elif not proposed:
        issues.append("solver_proposed_answer_missing")
    elif proposed != expected:
        issues.append("solver_answer_mismatch")
    if not chain.author_item_id:
        issues.append("generated_draft_not_bound")
    elif chain.author_item_id != qid:
        issues.append("author_item_id_mismatch")
    if chain.author_draft_fingerprint and chain.persisted_visible_fingerprint:
        if chain.author_draft_fingerprint != chain.persisted_visible_fingerprint:
            issues.append("author_draft_content_mismatch")
    elif chain.author_parsed:
        draft_ok, draft_issues = author_draft_matches_question(chain.author_parsed, question)
        if not draft_ok:
            issues.extend(draft_issues)

    author_key = chain.author_claimed_answer_key
    author_parsed = chain.author_parsed or {}
    if not author_key and author_parsed:
        author_key, claim_issues = author_claimed_answer_key(author_parsed)
        if claim_issues:
            issues.extend(claim_issues)
    if author_key and expected and author_key != expected:
        issues.append("author_answer_mismatch")
    if author_key and proposed and author_key != proposed:
        issues.append("author_solver_disagreement")
    if not author_key and expected:
        issues.append("author_answer_missing")

    return (not issues, tuple(dict.fromkeys(issues)))