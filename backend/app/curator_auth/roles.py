from __future__ import annotations

from enum import StrEnum


class CuratorRole(StrEnum):
    MAPPING_CURATOR = "mapping_curator"
    MANDATORY_POLICY_CURATOR = "mandatory_policy_curator"


class CuratorOperation(StrEnum):
    MAPPING_APPROVE = "mapping_approve"
    MAPPING_REVOKE = "mapping_revoke"
    MANDATORY_POLICY_APPROVE = "mandatory_policy_approve"
    MANDATORY_POLICY_REVOKE = "mandatory_policy_revoke"
