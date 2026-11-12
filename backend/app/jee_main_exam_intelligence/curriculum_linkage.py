from __future__ import annotations

from typing import Any

from app.jee_main_exam_intelligence.enums import PaperPlanIssueCode

# Source-aligned catalogue entries only; no invented NTA↔CBSE graph edges.
OFFICIAL_TOPIC_CURRICULUM_REFS: dict[str, dict[str, Any]] = {
    "sets-relations-functions": {
        "curriculum_node_code": "jee-main-math-sets",
        "link_provenance": "pending_nta_syllabus_revision",
        "invented_edge": False,
    },
    "complex-numbers-quadratic": {
        "curriculum_node_code": "jee-main-math-complex-quadratic",
        "link_provenance": "pending_nta_syllabus_revision",
        "invented_edge": False,
    },
}


def curriculum_link_status(topic_code: str) -> tuple[str, list[PaperPlanIssueCode]]:
    """Return linkage status; fail-closed when NTA syllabus authority is on hold."""
    ref = OFFICIAL_TOPIC_CURRICULUM_REFS.get(topic_code)
    if ref is None:
        return "unmapped", [PaperPlanIssueCode.UNKNOWN_TOPIC]
    provenance = str(ref.get("link_provenance") or "")
    if provenance == "pending_nta_syllabus_revision":
        return "on_hold_pending_nta", [PaperPlanIssueCode.OFFICIAL_SOURCE_NOT_VERIFIED]
    return "approved", []
