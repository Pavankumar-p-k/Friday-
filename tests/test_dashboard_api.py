from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from friday.api import create_app


def _auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/v1/dashboard/auth/login",
        json={"username": "admin", "password": "test-pass"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_auth_required(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "dashboard_auth.db"))
    monkeypatch.setenv("FRIDAY_DASHBOARD_AUTH_ENABLED", "true")
    monkeypatch.setenv("FRIDAY_DASHBOARD_AUTH_USERNAME", "admin")
    monkeypatch.setenv("FRIDAY_DASHBOARD_AUTH_PASSWORD", "test-pass")
    monkeypatch.setenv("FRIDAY_DASHBOARD_AUTH_SECRET", "test-secret")

    app = create_app()
    with TestClient(app) as client:
        denied = client.get("/v1/dashboard/stats")
        assert denied.status_code == 401

        failed_login = client.post(
            "/v1/dashboard/auth/login",
            json={"username": "admin", "password": "wrong-pass"},
        )
        assert failed_login.status_code == 401

        ok_login = client.post(
            "/v1/dashboard/auth/login",
            json={"username": "admin", "password": "test-pass"},
        )
        assert ok_login.status_code == 200
        payload = ok_login.json()
        assert payload["access_token"]
        assert payload["token_type"] == "bearer"


def test_dashboard_endpoints_with_auth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "dashboard_data.db"))
    monkeypatch.setenv("FRIDAY_DASHBOARD_AUTH_ENABLED", "true")
    monkeypatch.setenv("FRIDAY_DASHBOARD_AUTH_USERNAME", "admin")
    monkeypatch.setenv("FRIDAY_DASHBOARD_AUTH_PASSWORD", "test-pass")
    monkeypatch.setenv("FRIDAY_DASHBOARD_AUTH_SECRET", "test-secret")
    monkeypatch.setenv("FRIDAY_CLOUD_LLM_ENABLED", "false")

    app = create_app()
    with TestClient(app) as client:
        headers = _auth_headers(client)

        get_settings = client.get("/v1/dashboard/settings", headers=headers)
        assert get_settings.status_code == 200
        assert "settings" in get_settings.json()

        update_settings = client.put(
            "/v1/dashboard/settings",
            headers=headers,
            json={"updates": {"voice_loop_mode": "chat"}},
        )
        assert update_settings.status_code == 200
        assert update_settings.json()["settings"]["voice_loop_mode"] == "chat"

        dispatch = client.post(
            "/v1/voice/dispatch",
            json={"session_id": "dash-voice", "transcript": "open notepad"},
        )
        assert dispatch.status_code == 200

        action = client.post(
            "/v1/dashboard/actions/execute",
            headers=headers,
            json={
                "session_id": "dash-actions",
                "tool": "reminder",
                "args": {"action": "set", "note": "sync standup"},
            },
        )
        assert action.status_code == 200
        action_payload = action.json()
        assert action_payload["tool"] == "reminder"
        assert action_payload["success"] is True

        history = client.get("/v1/dashboard/actions/history", headers=headers)
        assert history.status_code == 200
        entries = history.json()
        assert entries
        assert entries[0]["tool"] == "reminder"

        voice_history = client.get("/v1/dashboard/voice-history", headers=headers)
        assert voice_history.status_code == 200
        assert voice_history.json()

        stats = client.get("/v1/dashboard/stats", headers=headers)
        assert stats.status_code == 200
        stats_payload = stats.json()
        assert stats_payload["action_history_count"] >= 1
        assert stats_payload["voice_history_count"] >= 1

        logs = client.get("/v1/dashboard/logs", headers=headers)
        assert logs.status_code == 200
        assert logs.json()


def test_dashboard_websocket_streams_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "dashboard_ws.db"))
    monkeypatch.setenv("FRIDAY_DASHBOARD_AUTH_ENABLED", "true")
    monkeypatch.setenv("FRIDAY_DASHBOARD_AUTH_USERNAME", "admin")
    monkeypatch.setenv("FRIDAY_DASHBOARD_AUTH_PASSWORD", "test-pass")
    monkeypatch.setenv("FRIDAY_DASHBOARD_AUTH_SECRET", "test-secret")

    app = create_app()
    with TestClient(app) as client:
        headers = _auth_headers(client)
        token = headers["Authorization"].split(" ", 1)[1]
        with client.websocket_connect(f"/v1/dashboard/ws?token={token}") as ws:
            first = ws.receive_json()
            assert first["type"] == "dashboard.snapshot"
            assert "stats" in first
