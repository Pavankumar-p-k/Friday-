from pathlib import Path

from fastapi.testclient import TestClient

from friday.api import create_app


def test_models_list_endpoint_returns_shape(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "models.db"))
    monkeypatch.setenv("FRIDAY_OLLAMA_BASE_URL", "http://127.0.0.1:59999")

    app = create_app()
    client = TestClient(app)
    response = client.get("/v1/models")

    assert response.status_code == 200
    payload = response.json()
    assert "models" in payload
    assert "count" in payload


def test_pull_model_endpoint_handles_missing_runtime(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "models2.db"))
    monkeypatch.setenv("FRIDAY_OLLAMA_BASE_URL", "http://127.0.0.1:59999")

    app = create_app()
    client = TestClient(app)
    response = client.post("/v1/models/pull", json={"model": "qwen2.5:7b-instruct"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "qwen2.5:7b-instruct"
    assert "ok" in payload

