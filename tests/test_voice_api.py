from pathlib import Path

from fastapi.testclient import TestClient

from friday.api import create_app


def test_voice_transcribe_txt_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "voice.db"))
    monkeypatch.setenv("FRIDAY_VOICE_INPUT_DIR", str(tmp_path / "voice_in"))
    monkeypatch.setenv("FRIDAY_VOICE_OUTPUT_DIR", str(tmp_path / "voice_out"))

    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/v1/voice/transcribe",
        files={"file": ("input.txt", b"hello friday", "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"] == "hello friday"


def test_voice_command_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "voice2.db"))
    monkeypatch.setenv("FRIDAY_VOICE_INPUT_DIR", str(tmp_path / "voice2_in"))
    monkeypatch.setenv("FRIDAY_VOICE_OUTPUT_DIR", str(tmp_path / "voice2_out"))

    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/v1/voice/command",
        data={"mode": "chat", "session_id": "voice-session"},
        files={"file": ("query.txt", b"what can you do offline", "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"] == "what can you do offline"
    assert payload["reply"]
    assert payload["audio_path"]


def test_voice_interrupt_endpoint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "voice3.db"))
    app = create_app()
    client = TestClient(app)

    response = client.post("/v1/voice/interrupt", json={"session_id": "s1"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["session_id"] == "s1"
    assert payload["interrupted"] is True


def test_voice_live_websocket_final_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "voice4.db"))
    monkeypatch.setenv("FRIDAY_VOICE_INPUT_DIR", str(tmp_path / "voice4_in"))
    monkeypatch.setenv("FRIDAY_VOICE_OUTPUT_DIR", str(tmp_path / "voice4_out"))
    app = create_app()
    client = TestClient(app)

    with client.websocket_connect("/v1/voice/live") as ws:
        first = ws.receive_json()
        assert first["type"] == "session.started"

        ws.send_json({"type": "partial", "text": "open note"})
        partial = ws.receive_json()
        assert partial["type"] == "partial.ack"

        ws.send_json({"type": "barge_in"})
        interrupted = ws.receive_json()
        assert interrupted["type"] == "barge_in.ack"
        assert interrupted["interrupted"] is True

        ws.send_json({"type": "final", "text": "open notepad", "mode": "action"})
        result = ws.receive_json()
        assert result["type"] == "final.result"
        assert result["payload"]["reply"]

        ws.send_json({"type": "stop"})
        stopped = ws.receive_json()
        assert stopped["type"] == "session.stopped"
