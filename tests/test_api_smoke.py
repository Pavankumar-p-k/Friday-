from pathlib import Path

from fastapi.testclient import TestClient

from friday.api import create_app


def test_health_endpoint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "api.db"))
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_plan_endpoint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "api2.db"))
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/v1/plan",
        json={"goal": "open notepad", "mode": "action", "context": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "action"
    assert len(body["steps"]) >= 1


def test_code_patch_proposal_endpoint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "api3.db"))
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/v1/code/propose_patch",
        json={"task": "add better error handling in api module"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "ok" in body
    assert "proposal" in body
