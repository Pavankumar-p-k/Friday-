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
  - `POST /v1/code/propose_patch`
  - `POST /v1/code/apply_patch`
  - `POST /v1/voice/transcribe`
  - `POST /v1/voice/command`
  - `POST /v1/voice/speak`
  - `POST /v1/voice/interrupt`
  - `POST /v1/voice/wakeword/check`
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
- Local LLM client (Ollama-compatible) with safe fallback when model is unavailable
- Voice pipeline adapter with command-based STT/TTS integration and fallback modes
- Live voice WebSocket flow with partial/final messages and `barge_in` support
- JSON schemas for tools in `core/schemas`
- Tests for planner, policy, API, models, voice, and code-context behavior

## Architecture

See:

- `docs/architecture.md`
- `docs/api-contracts.md`
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
```

If these commands are not set, FRIDAY uses fallback behavior:

- transcription fallback from `.txt` uploads
- speech fallback writes assistant reply to a text file in `data/voice/out`

## Safety model

- tools are allowlisted
- unknown tools are blocked
- risky steps require explicit approval
- app launch is restricted to configured app names
- safe shell tool enforces allowed prefixes and blocked-term denylist
- action timeline records every step status
- reminder due events are emitted over websocket

## Suggested next upgrades

1. Add realtime microphone streaming and interruption handling
2. Add stronger code patch workflow (`propose diff -> approve -> apply`)
3. Add vector retrieval over large local documentation sets
4. Add evaluation dashboard (`task success`, `latency`, `tool failure rate`)
