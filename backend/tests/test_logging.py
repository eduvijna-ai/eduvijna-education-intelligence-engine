from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi.testclient import TestClient


def test_structured_request_log_contains_utc_timestamp(
    client: TestClient,
    caplog,
) -> None:
    with caplog.at_level(logging.INFO, logger="eduvijna.http"):
        response = client.get("/health")

    assert response.status_code == 200

    request_records = [
        record
        for record in caplog.records
        if record.name == "eduvijna.http" and '"event":"http_request"' in record.message
    ]
    assert request_records

    event = json.loads(request_records[-1].message)
    assert event["request_id"] == response.headers["x-request-id"]
    assert event["path"] == "/health"
    timestamp = datetime.fromisoformat(event["timestamp"])
    assert timestamp.tzinfo is not None
    assert timestamp.utcoffset() is not None
