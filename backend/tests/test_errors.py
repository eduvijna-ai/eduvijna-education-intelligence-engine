from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.main import app_error_handler


def test_standard_error_contract() -> None:
    test_app = FastAPI()
    test_app.add_exception_handler(AppError, app_error_handler)

    @test_app.get("/boom")
    def boom() -> None:
        raise AppError(code="TEST_ERROR", message="boom", status_code=409)

    response = TestClient(test_app).get("/boom", headers={"x-request-id": "test-request"})
    assert response.status_code == 409
    payload = response.json()
    assert payload["error"]["code"] == "TEST_ERROR"
    assert payload["error"]["message"] == "boom"
    assert "request_id" in payload["error"]
