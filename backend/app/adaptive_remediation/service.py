"""Day 16 adaptive remediation diagnostic service."""

from __future__ import annotations

from app.adaptive_remediation.contracts import AdaptiveRemediationPlan
from app.adaptive_remediation.internal_demo import build_authoritative_synthetic_plan
from app.adaptive_remediation.runtime_boundary import attempt_runtime_remediation


class AdaptiveRemediationDiagnosticService:
    """Public surface: runtime entry blocked; internal synthetic demo only."""

    def attempt_runtime_remediation(
        self, *args: object, **kwargs: object
    ) -> AdaptiveRemediationPlan:
        return attempt_runtime_remediation(*args, **kwargs)

    def run_authoritative_synthetic_demo(self) -> AdaptiveRemediationPlan:
        return build_authoritative_synthetic_plan()
