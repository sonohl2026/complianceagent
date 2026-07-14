from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_200():
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert "database" in body


def test_settings_endpoint_never_returns_raw_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()

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
