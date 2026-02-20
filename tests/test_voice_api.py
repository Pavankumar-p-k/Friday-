from pathlib import Path
import time

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


def test_voice_transcribe_rejects_large_upload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "voice_limit.db"))
    monkeypatch.setenv("FRIDAY_VOICE_INPUT_DIR", str(tmp_path / "voice_limit_in"))
    monkeypatch.setenv("FRIDAY_VOICE_OUTPUT_DIR", str(tmp_path / "voice_limit_out"))
    monkeypatch.setenv("FRIDAY_VOICE_MAX_UPLOAD_BYTES", "8")

    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/v1/voice/transcribe",
        files={"file": ("large.txt", b"123456789", "text/plain")},
    )

    assert response.status_code == 413


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


def test_voice_loop_processes_wake_word_command(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "voice_loop_in"
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "voice_loop.db"))
    monkeypatch.setenv("FRIDAY_VOICE_INPUT_DIR", str(input_dir))
    monkeypatch.setenv("FRIDAY_VOICE_OUTPUT_DIR", str(tmp_path / "voice_loop_out"))
    monkeypatch.setenv("FRIDAY_VOICE_LOOP_AUTO_START", "false")

    app = create_app()
    with TestClient(app) as client:
        start = client.post(
            "/v1/voice/loop/start",
            json={
                "session_id": "loop-chat",
                "mode": "chat",
                "require_wake_word": True,
                "poll_interval_sec": 1,
            },
        )
        assert start.status_code == 200
        assert start.json()["running"] is True

        input_dir.mkdir(parents=True, exist_ok=True)
        (input_dir / "wake.txt").write_text("friday what can you do offline", encoding="utf-8")

        processed = False
        for _ in range(30):
            state = client.get("/v1/voice/loop/state")
            assert state.status_code == 200
            payload = state.json()
            if payload["processed_count"] >= 1:
                processed = True
                assert payload["last_command"] == "what can you do offline"
                assert payload["last_reply"]
                break
            time.sleep(0.1)
        assert processed is True

        stop = client.post("/v1/voice/loop/stop")
        assert stop.status_code == 200
        assert stop.json()["running"] is False


def test_voice_loop_skips_when_wake_word_missing(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "voice_loop_in2"
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "voice_loop2.db"))
    monkeypatch.setenv("FRIDAY_VOICE_INPUT_DIR", str(input_dir))
    monkeypatch.setenv("FRIDAY_VOICE_OUTPUT_DIR", str(tmp_path / "voice_loop_out2"))
    monkeypatch.setenv("FRIDAY_VOICE_LOOP_AUTO_START", "false")

    app = create_app()
    with TestClient(app) as client:
        start = client.post(
            "/v1/voice/loop/start",
            json={
                "session_id": "loop-chat-2",
                "mode": "chat",
                "require_wake_word": True,
                "poll_interval_sec": 1,
            },
        )
        assert start.status_code == 200
        assert start.json()["running"] is True

        input_dir.mkdir(parents=True, exist_ok=True)
        (input_dir / "no_wake.txt").write_text("open notepad", encoding="utf-8")

        skipped = False
        for _ in range(30):
            state = client.get("/v1/voice/loop/state")
            assert state.status_code == 200
            payload = state.json()
            if payload["skipped_count"] >= 1:
                skipped = True
                assert payload["processed_count"] == 0
                assert payload["last_error"] == "wake word not detected"
                break
            time.sleep(0.1)
        assert skipped is True

        stop = client.post("/v1/voice/loop/stop")
        assert stop.status_code == 200
        assert stop.json()["running"] is False


def test_voice_dispatch_returns_structured_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FRIDAY_DB_PATH", str(tmp_path / "voice_dispatch.db"))
    monkeypatch.setenv("FRIDAY_CLOUD_LLM_ENABLED", "false")

    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/v1/voice/dispatch",
        json={
            "session_id": "dispatch-session",
            "transcript": "open notepad",
            "context": {"source": "test"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"] == "open notepad"
    assert payload["intent"] == "automation"
    assert payload["mode"] == "action"
    assert payload["reply"]
    assert isinstance(payload["actions"], list)
    assert payload["llm_backend"] in {"local", "deterministic-fallback"}
