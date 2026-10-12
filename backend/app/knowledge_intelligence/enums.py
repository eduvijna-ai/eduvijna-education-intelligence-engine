from __future__ import annotations

from enum import StrEnum


class KnowledgeOwnershipScope(StrEnum):
    GLOBAL_OFFICIAL = "global_official"
    ORGANIZATION = "organization"
    INSTITUTION = "institution"
    TEACHER = "teacher"


class KnowledgeIndexStatus(StrEnum):
    PENDING = "pending"
    INDEXING = "indexing"
    ACTIVE = "active"
    FAILED = "failed"
    RETIRED = "retired"
    SUPERSEDED = "superseded"


class KnowledgeAuditEventType(StrEnum):
    INDEX_ATTEMPT = "index_attempt"
    INDEX_SUCCESS = "index_success"
    INDEX_FAILURE = "index_failure"
    INDEX_SUPERSEDE = "index_supersede"
    INDEX_RETIRE = "index_retire"
    RETRIEVE = "retrieve"
