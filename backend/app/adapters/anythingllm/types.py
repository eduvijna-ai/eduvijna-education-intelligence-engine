from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class GatewayAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    UNAUTHORIZED = "unauthorized"
    INVALID_RESPONSE = "invalid_response"


class AdapterErrorCode(StrEnum):
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"
    UNAUTHORIZED = "unauthorized"
    NOT_FOUND = "not_found"
    INVALID_RESPONSE = "invalid_response"
    UNAVAILABLE = "unavailable"
    VALIDATION = "validation"


@dataclass(frozen=True, slots=True)
class GatewayProbeResult:
    availability: GatewayAvailability
    message: str = ""
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkspaceKey:
    """Deterministic workspace identity derived from knowledge scope."""

    scope_key: str
    slug: str


@dataclass(frozen=True, slots=True)
class IndexDocumentPayload:
    title: str
    evidence_text: str
    content_checksum: str
    source_locator: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdapterDocumentRef:
    workspace_slug: str
    document_id: str
    title: str | None = None


@dataclass(frozen=True, slots=True)
class AdapterUploadedDocument:
    """Upload result: stable docSource identity plus remote removal keys (D7-PIC-04)."""

    stable_id: str
    remote_doc_id: str | None = None
    remote_location: str | None = None
    doc_source_identity: str | None = None


@dataclass(frozen=True, slots=True)
class AdapterRetrievalHit:
    workspace_slug: str
    document_id: str
    text: str
    score: float
    rank: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdapterRetrievalRequest:
    query_text: str
    top_k: int
    workspace_slugs: tuple[str, ...]
    metadata_filters: dict[str, Any] = field(default_factory=dict)


class AdapterError(Exception):
    def __init__(
        self,
        code: AdapterErrorCode,
        message: str,
        *,
        retryable: bool = False,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status


def availability_from_http_status(status: int) -> GatewayAvailability:
    if status in {401, 403}:
        return GatewayAvailability.UNAUTHORIZED
    if status >= 500:
        return GatewayAvailability.UNAVAILABLE
    if status >= 400:
        return GatewayAvailability.DEGRADED
    return GatewayAvailability.AVAILABLE
