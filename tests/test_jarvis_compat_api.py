from pathlib import Path

from fastapi.testclient import TestClient

from friday.api import create_app


def test_jarvis_state_endpoint_shape(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "jarvis.db"))
    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/jarvis/state")
    assert response.status_code == 200
    payload = response.json()
    assert "mode" in payload
    assert "telemetry" in payload
    assert "reminders" in payload
    assert "commandHistory" in payload


def test_jarvis_mode_and_command_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "jarvis2.db"))
    app = create_app()
    client = TestClient(app)

    set_mode = client.post("/v1/jarvis/set-mode", json={"mode": "focus"})
    assert set_mode.status_code == 200
    assert set_mode.json()["mode"] == "focus"

    run = client.post(
        "/v1/jarvis/run-command",
        json={"command": "run command Get-Date", "bypass_confirmation": False},
    )
    assert run.status_code == 200
    payload = run.json()
    assert payload["result"]["ok"] is False
    assert payload["result"].get("needsConfirmation") is True

    run_bypass = client.post(
        "/v1/jarvis/run-command",
        json={"command": "run command Get-Date", "bypass_confirmation": True},
    )
    assert run_bypass.status_code == 200
    payload_bypass = run_bypass.json()
    assert payload_bypass["result"]["ok"] is True


def test_jarvis_briefing_endpoint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "jarvis3.db"))
    app = create_app()
    client = TestClient(app)

    response = client.post("/v1/jarvis/generate-briefing")
    assert response.status_code == 200
    payload = response.json()
    assert "headline" in payload
    assert "suggestedFocus" in payload


def test_jarvis_run_command_reports_failure_when_tool_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "jarvis4.db"))
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/v1/jarvis/run-command",
        json={"command": "run command python --versionx", "bypass_confirmation": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["ok"] is False
