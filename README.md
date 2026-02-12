# FRIDAY Offline Assistant

Offline-first, free, local AI assistant with:

- chat mode for general Q&A
- action mode for task execution (apps, music, reminders)
- code mode for code generation and repository-aware coding help
- plan-then-execute workflow with safety policy checks
- event timeline stream for UI action traces

This repository is built as an industry-style backend foundation that you can connect to your existing UI.

## What is implemented

- FastAPI backend with endpoints:
  - `POST /v1/chat`
  - `POST /v1/plan`
  - `POST /v1/actions/execute`
  - `GET /v1/actions/{run_id}`
  - `GET /v1/tools`
  - `WS /v1/events`
- Orchestrator with deterministic action planning and execution
- Policy engine with allowlist + approval gating
- Tool registry and concrete tools:
  - `open_app`
  - `media_control`
  - `reminder`
  - `code_agent`
  - `safe_shell`
- SQLite storage for reminders and chat history
- Local LLM client (Ollama-compatible) with safe fallback when model is unavailable
- JSON schemas for tools in `core/schemas`
- Tests for planner and policy behavior

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

## Safety model

- tools are allowlisted
- unknown tools are blocked
- risky steps require explicit approval
- app launch is restricted to configured app names
- action timeline records every step status

## Suggested next upgrades

1. Add real voice pipeline integration (`whisper.cpp`, `Piper`, `openWakeWord`)
2. Add richer code agent tools for file patching and test execution sandbox
3. Add vector retrieval over local docs and codebase
4. Add evaluation dashboard (`task success`, `latency`, `tool failure rate`)
