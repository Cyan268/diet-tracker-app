from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.routes import health
from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_root_describes_service(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["name"] == "NutriPilot API"


def test_liveness_does_not_require_database(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_succeeds_when_database_is_available(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def database_is_available() -> None:
        return None

    monkeypatch.setattr(health, "check_database", database_is_available)

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_503_when_database_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def database_is_unavailable() -> None:
        raise OperationalError("SELECT 1", {}, RuntimeError("connection failed"))

    monkeypatch.setattr(health, "check_database", database_is_unavailable)

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
