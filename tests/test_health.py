"""Smoke tests for the application factory and the health endpoint."""

from __future__ import annotations

from app.main import create_app
from fastapi.testclient import TestClient


def test_health_returns_ok() -> None:
    """/health returns 200 with a service-only status payload."""
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"]
    assert body["environment"]


def test_health_sets_correlation_id_header() -> None:
    """Every response carries a correlation id for tracing."""
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.headers.get("X-Correlation-ID")


def test_inbound_correlation_id_is_echoed() -> None:
    """A caller-supplied correlation id is threaded back unchanged."""
    client = TestClient(create_app())
    response = client.get("/health", headers={"X-Correlation-ID": "trace-123"})

    assert response.headers["X-Correlation-ID"] == "trace-123"
