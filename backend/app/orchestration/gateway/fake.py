from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from app.orchestration.enums import GenerationNodeRole
from app.orchestration.gateway.types import (
    GenerationCallContext,
    GenerationGatewayError,
    GenerationRequest,
    GenerationResponse,
)


class FakeGenerationGateway:
    """Deterministic author/solver/reviewer responses for CI (D8-06)."""

    def __init__(self) -> None:
        self._history: list[GenerationResponse] = []
        self._author_pass_counts: dict[str, int] = {}
        self._diagnostic_pass_counts: dict[str, int] = {}

    def call_history(self) -> list[GenerationResponse]:
        return list(self._history)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        started = time.perf_counter()
        scenario = request.scenario
        if scenario == "gateway_timeout":
            raise GenerationGatewayError("gateway_timeout", "simulated timeout", retryable=True)
        if scenario == "gateway_401":
            raise GenerationGatewayError(
                "gateway_unauthorized", "simulated unauthorized", retryable=False, http_status=401
            )
        if scenario == "gateway_5xx":
            raise GenerationGatewayError(
                "gateway_unavailable", "simulated 503", retryable=True, http_status=503
            )
        if scenario == "malformed_json":
            raise GenerationGatewayError("gateway_invalid_json", "simulated malformed JSON")

        payload = request.user_payload
        item_id = str(payload.get("item_id", "item-0"))
        revision_ids = list(payload.get("allowed_source_revision_ids") or [])
        primary_revision = revision_ids[0] if revision_ids else "missing-revision"
        lo_ids = list(payload.get("learning_outcome_ids") or [])
        learning_outcome_id = lo_ids[0] if lo_ids else None

        parsed: dict[str, Any]
        if request.role == GenerationNodeRole.AUTHOR:
            parsed = self._author_payload(
                scenario, item_id, primary_revision, learning_outcome_id, payload
            )
        elif request.role == GenerationNodeRole.SOLVER:
            parsed = self._solver_payload(scenario, item_id, payload)
        elif request.role == GenerationNodeRole.REPAIR:
            parsed = {
                "repair_instructions": dict(payload.get("repair_instructions") or {}),
            }
        elif request.role == GenerationNodeRole.DIAGNOSTIC:
            parsed = self._diagnostic_payload(payload)
        else:
            parsed = self._review_payload(request.role, scenario, item_id, payload)

        raw = json.dumps(parsed, sort_keys=True)
        latency_ms = (time.perf_counter() - started) * 1000
        input_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        response = GenerationResponse(
            parsed=parsed,
            raw_text=raw,
            latency_ms=latency_ms,
            gateway_request_id=f"fake-{len(self._history)}",
            usage={"model_calls": 1, "tokens_in": len(raw), "tokens_out": len(raw)},
            call_context=GenerationCallContext(
                run_id=str(payload.get("run_id", "run")),
                item_id=item_id,
                role=request.role,
                prompt_version=request.prompt_version,
                scenario=scenario,
                input_hash=input_hash,
            ),
        )
        self._history.append(response)
        return response

    def _author_payload(
        self,
        scenario: str,
        item_id: str,
        revision_id: str,
        learning_outcome_id: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        run_key = f"{payload.get('run_id')}:{item_id}"
        attempt = self._author_pass_counts.get(run_key, 0)
        self._author_pass_counts[run_key] = attempt + 1

        if scenario == "bad_provenance":
            revision_id = "00000000-0000-0000-0000-000000000099"
        if scenario == "foreign_tenant":
            revision_id = str(payload.get("foreign_revision_id") or revision_id)
        if scenario == "injection_evidence":
            allowed = list(payload.get("allowed_source_revision_ids") or [])
            bounded = str(payload.get("bounded_context") or "").lower()
            if "ignore previous instructions" in bounded:
                for candidate in allowed:
                    if str(candidate) != str(revision_id):
                        revision_id = str(candidate)
                        break
        if scenario == "duplicate":
            stem = "SYNTHETIC DUPLICATE STEM 7+5"
        elif scenario == "repair_then_pass" and attempt == 0:
            return {
                "item_id": item_id,
                "stem_text": "Synthetic fixture: What is 7 + 5?",
                "question_type": "single_choice",
                "options": [
                    {"option_key": "A", "text": "11", "is_correct": False},
                    {"option_key": "B", "text": "12", "is_correct": True},
                ],
                "marks": None,
                "source_revision_ids": [revision_id],
                "learning_outcome_ids": [learning_outcome_id] if learning_outcome_id else [],
                "competency_codes": ["application"],
                "declared_cognitive_level": "Apply",
                "declared_difficulty": 2,
                "metadata_json": {
                    "difficulty_evidence": {
                        "cognitive_demand_band": 2,
                        "step_count": 1,
                        "computation_load": 2,
                        "language_load": 1,
                    },
                    "cognitive_demand_evidence": {"application_required": True},
                    "age_min": 12,
                    "age_max": 14,
                    "synthetic_fixture": True,
                },
            }
        elif scenario == "unsupported_question_type":
            return {
                "item_id": item_id,
                "stem_text": "Synthetic fixture: What is 7 + 5?",
                "question_type": "essay",
                "options": [
                    {"option_key": "A", "text": "11", "is_correct": False},
                    {"option_key": "B", "text": "12", "is_correct": True},
                ],
                "marks": float(payload.get("marks") or 1),
                "source_revision_ids": [revision_id],
                "learning_outcome_ids": [learning_outcome_id] if learning_outcome_id else [],
                "competency_codes": ["application"],
                "declared_cognitive_level": "Apply",
                "declared_difficulty": 2,
                "metadata_json": {"synthetic_fixture": True},
            }
        elif scenario == "double_correct":
            return {
                "item_id": item_id,
                "stem_text": "Synthetic fixture: What is 7 + 5?",
                "question_type": "single_choice",
                "options": [
                    {"option_key": "A", "text": "11", "is_correct": True},
                    {"option_key": "B", "text": "12", "is_correct": True},
                ],
                "marks": float(payload.get("marks") or 1),
                "source_revision_ids": [revision_id],
                "learning_outcome_ids": [learning_outcome_id] if learning_outcome_id else [],
                "competency_codes": ["application"],
                "declared_cognitive_level": "Apply",
                "declared_difficulty": 2,
                "metadata_json": {"synthetic_fixture": True},
            }
        elif scenario == "blocking_day6":
            stem = "Synthetic fixture with unsafe content trigger"
        elif scenario == "non_arithmetic_diagnostic_review":
            stem = "Synthetic number-sense fixture: choose the best statement."
        elif scenario == "injection_evidence":
            stem = "Synthetic fixture: What is 7 + 5?"
        elif payload.get("slot_index") == 1:
            stem = "Synthetic fixture slot B: What is 7 + 5?"
        else:
            stem = "Synthetic fixture: What is 7 + 5?"

        metadata_json: dict[str, Any] = {}
        if scenario == "blocking_day6":
            metadata_json["content_text_for_safety"] = (
                "Perform this unsafe lab experiment at home without supervision."
            )
        elif scenario == "human_review":
            metadata_json = {"synthetic_fixture": True}
        elif scenario not in {"bad_provenance", "foreign_tenant", "malformed_json"}:
            metadata_json = {
                "difficulty_evidence": {
                    "cognitive_demand_band": 2,
                    "step_count": 1,
                    "computation_load": 2,
                    "language_load": 1,
                },
                "cognitive_demand_evidence": {"application_required": True},
                "age_min": 12,
                "age_max": 14,
                "synthetic_fixture": True,
            }

        return {
            "item_id": item_id,
            "stem_text": stem,
            "question_type": "single_choice",
            "options": [
                {"option_key": "A", "text": "11", "is_correct": False},
                {"option_key": "B", "text": "12", "is_correct": True},
            ],
            "marks": float(payload.get("marks") or 1),
            "source_revision_ids": [revision_id],
            "learning_outcome_ids": [learning_outcome_id] if learning_outcome_id else [],
            "competency_codes": ["application"],
            "declared_cognitive_level": "Apply",
            "declared_difficulty": 2,
            "metadata_json": metadata_json,
        }

    def _solver_payload(
        self, scenario: str, item_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        if scenario == "solver_disagree":
            return {
                "item_id": item_id,
                "proposed_answer_key": "A",
                "working_summary": "Synthetic solver disagrees",
                "check_status": "mismatch",
                "agrees_with_author": False,
            }
        return {
            "item_id": item_id,
            "proposed_answer_key": "B",
            "working_summary": "Synthetic solver: 7+5=12",
            "check_status": "ok",
            "agrees_with_author": True,
        }

    def _diagnostic_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        item_id = str(payload.get("item_id", "item-0"))
        scenario = str(payload.get("fixture_scenario") or "diagnostic_clean_pass")
        run_key = f"{payload.get('run_id')}:{item_id}"
        attempt = self._diagnostic_pass_counts.get(run_key, 0)
        self._diagnostic_pass_counts[run_key] = attempt + 1
        options = list(payload.get("options") or [])
        allowed_refs = list(payload.get("allowed_evidence_refs") or [])
        evidence_ref = allowed_refs[0] if allowed_refs else "[CIT-1]"

        def tag(
            option_key: str,
            code: str | None,
            signal: str | None,
            *,
            evidence_refs: list[str] | None = None,
        ) -> dict[str, Any]:
            option: dict[str, Any] = next(
                (o for o in options if o.get("option_key") == option_key), {}
            )
            refs = evidence_refs
            if refs is None:
                refs = [evidence_ref] if code else []
            return {
                "option_key": option_key,
                "is_correct": bool(option.get("is_correct")),
                "misconception_code": code,
                "diagnostic_signal": signal,
                "evidence_refs": refs,
            }

        def clean_pass_tags() -> list[dict[str, Any]]:
            wrong_keys = [str(o.get("option_key")) for o in options if not o.get("is_correct")]
            option_tags: list[dict[str, Any]] = []
            if wrong_keys:
                option_tags.append(
                    tag(wrong_keys[0], "MATH.ADD.WHOLE.OFF_BY_ONE_LOW", "off-by-one-low")
                )
            if len(wrong_keys) > 1:
                option_tags.append(
                    tag(wrong_keys[1], "MATH.ADD.WHOLE.SUM_AS_NEXT", "successor")
                )
            for option in options:
                if option.get("is_correct"):
                    option_tags.append(tag(str(option.get("option_key")), None, None))
            return option_tags

        wrong_keys = [str(o.get("option_key")) for o in options if not o.get("is_correct")]
        wrong_key = wrong_keys[0] if wrong_keys else "A"
        correct_key = next(
            (str(o.get("option_key")) for o in options if o.get("is_correct")),
            "B",
        )

        if scenario == "diagnostic_repair_then_pass" and attempt == 0:
            tags = clean_pass_tags()
            for index, entry in enumerate(tags):
                if entry.get("misconception_code") == "MATH.ADD.WHOLE.OFF_BY_ONE_LOW":
                    tags[index] = tag(
                        str(entry["option_key"]),
                        "MATH.ADD.WHOLE.SUM_AS_NEXT",
                        "successor",
                    )
                    break
            return {"item_id": item_id, "option_tags": tags}

        if scenario == "diagnostic_unknown_code":
            tags = clean_pass_tags()
            tags[0] = tag(wrong_key, "MATH.INVENTED.CODE", "fake")
            return {"item_id": item_id, "option_tags": tags}
        if scenario == "diagnostic_inactive":
            tags = clean_pass_tags()
            tags[0] = tag(wrong_key, "MATH.ADD.WHOLE.INACTIVE_SAMPLE", "inactive")
            return {"item_id": item_id, "option_tags": tags}
        if scenario == "diagnostic_wrong_subject":
            tags = clean_pass_tags()
            tags[0] = tag(wrong_key, "SCI.PHYS.FORCE.WRONG_SUBJECT", "newton")
            return {"item_id": item_id, "option_tags": tags}
        if scenario == "diagnostic_correct_mislabeled":
            tags = clean_pass_tags()
            tags[-1] = tag(correct_key, "MATH.ADD.WHOLE.SUM_AS_NEXT", "successor")
            return {"item_id": item_id, "option_tags": tags}
        if scenario == "diagnostic_foreign_revision":
            foreign = str(payload.get("foreign_revision_id") or "")
            tags = clean_pass_tags()
            tags[0] = tag(
                wrong_key,
                "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                "off-by-one-low",
                evidence_refs=[foreign] if foreign else ["FORGED-REF"],
            )
            return {"item_id": item_id, "option_tags": tags}
        if scenario == "diagnostic_forged_evidence":
            tags = clean_pass_tags()
            tags[0] = tag(
                wrong_key,
                "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                "off-by-one-low",
                evidence_refs=["FORGED-REF"],
            )
            return {"item_id": item_id, "option_tags": tags}
        if scenario == "diagnostic_review_required":
            tags = clean_pass_tags()
            tags[0] = tag(
                wrong_key,
                "MATH.ADD.WHOLE.SUM_AS_NEXT",
                "successor",
            )
            return {"item_id": item_id, "option_tags": tags}
        if scenario == "diagnostic_second_correct":
            tags = clean_pass_tags()
            tags[0] = tag(wrong_key, "MATH.ADD.WHOLE.SUM_AS_NEXT", "12")
            return {"item_id": item_id, "option_tags": tags}
        if scenario == "diagnostic_malformed_output":
            return {"item_id": item_id, "option_tags": "not-a-list"}
        if scenario == "diagnostic_duplicate_option_keys":
            tags = clean_pass_tags()
            if tags:
                tags.append(dict(tags[0]))
            return {"item_id": item_id, "option_tags": tags}

        return {"item_id": item_id, "option_tags": clean_pass_tags()}

    def _review_payload(
        self,
        role: GenerationNodeRole,
        scenario: str,
        item_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        status = "pass"
        issue_codes: list[str] = []
        repair_instructions: list[str] = []
        if role == GenerationNodeRole.PATTERN_REVIEW and scenario == "repair_then_pass":
            draft = payload.get("draft") or {}
            if draft.get("marks") is None:
                status = "repair"
                issue_codes = ["pattern_missing_marks"]
                repair_instructions = ["Set marks to the requested value"]
        if role == GenerationNodeRole.EDUCATIONAL_REVIEW and scenario == "blocking_day6":
            status = "reject"
            issue_codes = ["educational_model_reject"]
        if role == GenerationNodeRole.CURRICULUM_REVIEW and scenario == "bad_provenance":
            status = "reject"
            issue_codes = ["curriculum_unknown_revision"]
        return {
            "reviewer": role.value,
            "item_id": item_id,
            "status": status,
            "issue_codes": issue_codes,
            "field_paths": [],
            "evidence_refs": [],
            "repair_instructions": repair_instructions,
        }
