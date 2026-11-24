"""Shared Day 15 harness helpers for tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.learner_intelligence.harness_runtime import (
    ephemeral_file_harness,
    isolated_harness_session,
)


@pytest.fixture()
def harness_session(tmp_path: Path):
    with isolated_harness_session(ephemeral_file_harness(tmp_path)) as bundle:
        yield bundle