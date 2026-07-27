from fastapi.testclient import TestClient

from app.main import app
from app.services.storage import settings_store


def test_health_endpoint_returns_200():
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert "database" in body


def test_settings_endpoint_never_returns_raw_secret():
    # Runtime settings live in one shared DB row (migration 0013), not a
    # per-test file -- snapshot/restore it so this test's fake key doesn't
    # permanently clobber a real, already-configured local deployment.
    original = settings_store.load_runtime_settings()
    try:
        client = TestClient(app)
        update = client.put("/api/v1/settings", json={"openrouter_api_key": "sk-supersecretvalue"})
        assert update.status_code == 200
        body = update.json()
        assert body["openrouter_api_key_configured"] is True
        assert "supersecretvalue" not in body["openrouter_api_key_masked"] or body[
            "openrouter_api_key_masked"
        ].endswith("alue")
        assert "sk-supersecretvalue" != body["openrouter_api_key_masked"]

        get = client.get("/api/v1/settings")
        assert "openrouter_api_key" not in get.json()
    finally:
        settings_store.save_runtime_settings(original)
