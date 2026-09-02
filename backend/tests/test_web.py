from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web import create_spa_router

WEB_FIXTURE = Path(__file__).parent / "fixtures" / "web-dist"
MISSING_WEB_FIXTURE = Path(__file__).parent / "fixtures" / "missing-web-dist"


def make_client(web_dist: Path) -> TestClient:
    app = FastAPI()

    @app.get("/api/v1/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(create_spa_router(web_dist, api_prefix="/api/v1"))
    return TestClient(app)


def test_spa_serves_shell_for_root_and_browser_routes() -> None:
    client = make_client(WEB_FIXTURE)

    for path in ("/", "/auth", "/profile/settings"):
        response = client.get(path)
        assert response.status_code == 200
        assert "NutriPilot" in response.text
        assert response.headers["cross-origin-opener-policy"] == "same-origin"
        assert response.headers["cross-origin-embedder-policy"] == "credentialless"
        assert response.headers["cache-control"] == "no-store"


def test_spa_assets_are_immutable_and_missing_files_stay_404() -> None:
    client = make_client(WEB_FIXTURE)

    asset = client.get("/assets/app.abc123.js")
    assert asset.status_code == 200
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert asset.headers["content-type"].startswith("text/javascript")

    assert client.get("/assets/missing.wasm").status_code == 404
    assert client.get("/api/v1/missing").status_code == 404


def test_spa_does_not_shadow_api_routes() -> None:
    client = make_client(WEB_FIXTURE)

    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_spa_router_requires_an_index_file() -> None:
    try:
        create_spa_router(MISSING_WEB_FIXTURE, api_prefix="/api/v1")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing index.html should fail during startup")
