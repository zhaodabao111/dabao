from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app


def make_client() -> TestClient:
    settings = Settings(
        _env_file=None,
        frontend_origin="http://localhost:5175",
        bailian_api_key="",
        deepseek_api_key="",
        amap_api_key="",
    )
    return TestClient(create_app(settings))


def test_health_returns_the_success_envelope_without_external_keys() -> None:
    with make_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"].startswith("req_")
    assert payload["data"] == {"status": "ok"}


def test_health_allows_the_configured_frontend_origin() -> None:
    with make_client() as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5175",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:5175"
    )
