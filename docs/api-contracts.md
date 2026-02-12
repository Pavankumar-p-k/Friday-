# API Contracts

## `POST /v1/chat`

Request:

```json
{
  "session_id": "default",
  "text": "open notepad",
  "mode": "action",
  "context": {}
}
```

Response:

```json
{
  "reply": "Plan created with 1 step(s). Approval required for steps: none.",
  "citations": [],
  "plan": {
    "id": "plan_123",
    "goal": "open notepad",
    "mode": "action",
    "status": "draft",
    "created_at": "2026-02-12T12:00:00+00:00",
    "steps": []
  },
  "run_id": null
}
```

## `POST /v1/plan`

Creates a plan and returns structured steps with risk/approval fields.

## `POST /v1/actions/execute`

Runs only approved plan steps.

## `GET /v1/actions/{run_id}`

Returns action run status and timeline.

## `GET /v1/tools`

Returns tool metadata and JSON input schema for UI integration.

## `GET /v1/models`

Returns discovered local Ollama models.

Response:

```json
{
  "models": [],
  "count": 0
}
```

## `POST /v1/models/pull`

Request:

```json
{
  "model": "qwen2.5:7b-instruct"
}
```

Response:

```json
{
  "ok": true,
  "message": "success",
  "model": "qwen2.5:7b-instruct"
}
```

## `GET /v1/models/{model_name}`

Returns model metadata from Ollama show API.

## `POST /v1/code/propose_patch`

Request:

```json
{
  "task": "add structured logging to planner",
  "path": "friday/planner.py"
}
```

## `POST /v1/code/apply_patch`

Request:

```json
{
  "patch": "diff --git a/file.py b/file.py ...",
  "dry_run": true
}
```

Response:

```json
{
  "ok": true,
  "applied": false,
  "dry_run": true,
  "message": "patch check passed (dry run)"
}
```

Response:

```json
{
  "ok": true,
  "proposal": "diff --git a/friday/planner.py b/friday/planner.py ...",
  "citations": ["friday/planner.py"],
  "message": null
}
```

## `POST /v1/voice/transcribe`

Multipart upload:

- `file`: audio file (or `.txt` fallback file)

Response:

```json
{
  "transcript": "open calculator",
  "backend": "command",
  "warning": null
}
```

## `POST /v1/voice/speak`

Request:

```json
{
  "text": "Hello from FRIDAY"
}
```

Response:

```json
{
  "audio_path": "data/voice/out/reply_abc.wav",
  "backend": "command",
  "warning": null
}
```

## `POST /v1/voice/command`

Multipart form:

- `file`: audio input (or `.txt` fallback)
- `mode`: `chat|action|code`
- `session_id`: string

Response:

```json
{
  "transcript": "set reminder in 10 minutes",
  "reply": "Plan created with 1 step(s).",
  "plan": null,
  "run_id": null,
  "audio_path": "data/voice/out/reply_xyz.wav",
  "stt_backend": "command",
  "tts_backend": "command",
  "warnings": []
}
```

## `POST /v1/voice/wakeword/check`

Request:

```json
{
  "text": "hey friday open vscode"
}
```

## `POST /v1/voice/interrupt`

Request:

```json
{
  "session_id": "voice-session-1"
}
```

Response:

```json
{
  "ok": true,
  "session_id": "voice-session-1",
  "interrupted": true
}
```

## `WS /v1/voice/live`

Client messages:

- `{"type":"start","session_id":"s1","mode":"action"}`
- `{"type":"partial","text":"open note"}`
- `{"type":"final","text":"open notepad","mode":"action"}`
- `{"type":"barge_in"}`
- `{"type":"stop"}`

Server events:

- `session.started`
- `partial.ack`
- `barge_in.ack`
- `final.result`
- `session.stopped`

Response:

```json
{
  "detected": true,
  "wake_words": ["friday", "jarvis"]
}
```

## `WS /v1/events`

Streams runtime events:

- `plan.created`
- `run.started`
- `step.running`
- `step.success`
- `step.failed`
- `run.finished`
- `reminder.due`
