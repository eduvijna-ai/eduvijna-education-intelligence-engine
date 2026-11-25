from __future__ import annotations

import pytest

from app.platform.capability_registry import (
    assert_capability_ready,
    reject_untrusted_authority_fields,
)
from app.platform.errors import CapabilityNotReadyError


def test_reject_untrusted_authority_fields() -> None:
    with pytest.raises(ValueError):
        reject_untrusted_authority_fields({"ready": True, "topic": "math"})


def test_learner_capability_fail_closed() -> None:
    with pytest.raises(CapabilityNotReadyError):
        assert_capability_ready("learners.read")
