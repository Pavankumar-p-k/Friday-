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

