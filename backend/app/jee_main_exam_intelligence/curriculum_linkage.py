from __future__ import annotations

from typing import Any

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
