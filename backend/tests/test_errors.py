from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError
from app.main import (
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
)


def test_standard_app_error_contract() -> None:
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


def test_http_404_uses_standard_error_contract() -> None:
    test_app = FastAPI()
    test_app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    response = TestClient(test_app).get("/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert response.json()["error"]["message"] == "Not Found"
    assert "request_id" in response.json()["error"]


def test_unhandled_exception_is_sanitized() -> None:
    test_app = FastAPI()
    test_app.add_exception_handler(Exception, unhandled_exception_handler)

    @test_app.get("/explode")
    def explode() -> None:
        raise RuntimeError("sensitive internal detail")

    response = TestClient(test_app, raise_server_exceptions=False).get("/explode")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert response.json()["error"]["message"] == "Internal server error"
    assert "sensitive internal detail" not in response.text
