# FRIDAY Offline Assistant

Offline-first, free, local AI assistant with:

- chat mode for general Q&A
- action mode for task execution (apps, music, reminders)
- code mode for code generation and repository-aware coding help
- plan-then-execute workflow with safety policy checks
- event timeline stream for UI action traces
- voice command flow (transcribe -> intent -> response -> speak)
- local model operations (list/pull/show)

This repository is built as an industry-style backend foundation that you can connect to your existing UI.

## What is implemented

- FastAPI backend with endpoints:
  - `POST /v1/chat`
  - `POST /v1/plan`
  - `POST /v1/actions/execute`
  - `GET /v1/actions/{run_id}`
  - `GET /v1/tools`
  - `GET /v1/models`
  - `POST /v1/models/pull`
  - `GET /v1/models/{model_name}`
  - `GET /v1/jarvis/state`
  - `POST /v1/jarvis/run-command`
  - `POST /v1/jarvis/set-mode`
  - `POST /v1/jarvis/complete-reminder`
  - `POST /v1/jarvis/replay-command`
  - `POST /v1/jarvis/generate-briefing`
  - `POST /v1/jarvis/reload-plugins`
  - `POST /v1/jarvis/set-automation-enabled`
  - `POST /v1/jarvis/set-plugin-enabled`
  - `POST /v1/jarvis/terminate-process`
  - `POST /v1/code/propose_patch`
  - `POST /v1/code/apply_patch`
  - `POST /v1/voice/transcribe`
  - `POST /v1/voice/command`
  - `POST /v1/voice/speak`
  - `POST /v1/voice/interrupt`
  - `POST /v1/voice/wakeword/check`
  - `GET /v1/voice/loop/state`
  - `POST /v1/voice/loop/start`
  - `POST /v1/voice/loop/stop`
  - `WS /v1/voice/live`
  - `WS /v1/events`
- Orchestrator with deterministic action planning and execution
- Background reminder due-event worker (`reminder.due`)
- Policy engine with allowlist + approval gating
- Tool registry and concrete tools:
  - `open_app`
  - `media_control`
  - `reminder`
  - `code_agent`
  - `safe_shell`
- SQLite storage for reminders and chat history
- Repo-aware code context retrieval with file citations
- Codex-style patch proposal endpoint (unified diff suggestion)
- Patch dry-run/apply endpoint for approval-based code edits
- Jarvis UI compatibility API for existing Electron contracts
- Local LLM client (Ollama-compatible) with safe fallback when model is unavailable
- Voice pipeline adapter with command-based STT/TTS integration and fallback modes
- Live voice WebSocket flow with partial/final messages and `barge_in` support
- Always-on voice loop worker with wake-word gating and start/stop controls
- JSON schemas for tools in `core/schemas`
- Tests for planner, policy, API, models, voice, and code-context behavior

## Architecture

See:

- `docs/architecture.md`
- `docs/api-contracts.md`
- `docs/deployment.md`
- `docs/roadmap.md`
- `docs/master_prompt_codex.md` (master prompt requested)

## Quick start (Windows PowerShell)

```powershell
cd C:\Users\Pavan\AppData\Roaming\Friday-
.\scripts\bootstrap_windows.ps1
.\scripts\run_api.ps1
```

One-command launcher:

```powershell
./app
```

API docs:

- http://127.0.0.1:8000/docs

## Production stack (Docker/Compose/Kubernetes)

Build and run all services (API + engine + dashboard):

```powershell
docker compose up -d --build
```

Dashboard and API:

- http://127.0.0.1:8080
- http://127.0.0.1:8000/docs

Kubernetes manifests and CI/CD notes:

- `docs/deployment.md`
- Helm chart: `deploy/helm/friday`

## Local model setup (free/offline)

Install Ollama and pull any free model:

```powershell
ollama pull qwen2.5:7b-instruct
```

Then set in `.env`:

```text
FRIDAY_OLLAMA_MODEL=qwen2.5:7b-instruct
```

If Ollama is not running, FRIDAY still responds through deterministic fallback logic.

## Voice setup (offline)

Set command adapters in `.env`:

```text
FRIDAY_VOICE_STT_COMMAND=whisper-cli -m C:\models\ggml-base.en.bin -f {audio_path}
FRIDAY_VOICE_TTS_COMMAND=piper --model C:\models\en_US-lessac-medium.onnx --output_file {output_path} --text "{text}"
FRIDAY_VOICE_MAX_UPLOAD_BYTES=10485760
FRIDAY_VOICE_LOOP_AUTO_START=true
FRIDAY_VOICE_LOOP_POLL_INTERVAL_SEC=2
FRIDAY_VOICE_LOOP_REQUIRE_WAKE_WORD=true
FRIDAY_VOICE_LOOP_SESSION_ID=voice-loop
FRIDAY_VOICE_LOOP_MODE=action
# Optional mic poll command. Use {output_path} placeholder when your recorder writes files.
FRIDAY_VOICE_LOOP_CAPTURE_COMMAND=
```

If these commands are not set, FRIDAY uses fallback behavior:

- transcription fallback from `.txt` uploads
- speech fallback writes assistant reply to a text file in `data/voice/out`
- voice loop still works by processing new files dropped into `data/voice/inbox`

Voice loop API controls:

- `GET /v1/voice/loop/state`
- `POST /v1/voice/loop/start`
- `POST /v1/voice/loop/stop`

## Safety model

- tools are allowlisted
- unknown tools are blocked
- risky steps require explicit approval
- app launch is restricted to configured app names
- safe shell tool enforces allowed prefixes and blocked-term denylist
- action timeline records every step status
- reminder due events are emitted over websocket

## Jarvis UI bridge integration

Your existing Desktop UI can be reused without editing the original folder.

```powershell
cd C:\Users\Pavan\AppData\Roaming\Friday-
.\scripts\prepare_jarvis_ui_bridge.ps1
```

This creates `apps/jarvis-bridge` as a copy, replaces preload with an HTTP bridge, and keeps `C:\Users\Pavan\Desktop\jarvis` untouched.

## Suggested next upgrades

1. Add realtime microphone streaming + VAD instead of poll-based capture
2. Add stronger code patch workflow (`propose diff -> approve -> apply`)
3. Add vector retrieval over large local documentation sets
4. Add evaluation dashboard (`task success`, `latency`, `tool failure rate`)
