# Architecture

## Layers

1. API Layer (`friday/api.py`)
- Exposes chat, plan, execute, status, and event APIs
- Keeps contracts stable for your UI

2. Orchestration Layer (`friday/orchestrator.py`)
- Converts user goals to plans
- Enforces policy decisions
- Executes approved steps with timeline logging
- Runs background reminder notification worker
- Coordinates voice command pipeline and model management

3. Planning Layer (`friday/planner.py`)
- Rule-based intent extraction for deterministic offline behavior
- Converts goal text to structured `PlanStep` objects

4. Policy Layer (`friday/policy.py`)
- Tool allowlist enforcement
- App allowlist enforcement
- Risk and approval gating

5. Tool Layer (`friday/tools/*`)
- App launch, media controls, reminders, code assistance
- Strict input schema per tool

6. Model Layer (`friday/llm.py`)
- Local Ollama-compatible generation
- Fallback output if local model is unavailable

7. Model Ops Layer (`friday/model_manager.py`)
- Local model discovery, pull, and metadata operations

8. Voice Layer (`friday/voice.py`)
- Upload handling, STT adapter, TTS adapter, wake-word checks
- Command-based integration with local binaries (`whisper.cpp`, `Piper`)

9. Retrieval Layer (`friday/code_context.py`)
- Lightweight repository context ranking for code tasks
- Returns file citations and snippets for grounding

10. Code Workflow Layer (`friday/code_workflow.py`)
- Generates unified diff proposals for coding tasks
- Feeds repo context into local model for Codex-style patch suggestions

11. Storage Layer (`friday/storage.py`)
- SQLite for reminders and history

12. Event Layer (`friday/events.py`)
- In-memory async pub/sub for action timeline streaming

## Data flow

1. Client sends request (`/v1/chat`, `/v1/plan`, `/v1/voice/*`, `/v1/models*`)
2. Planner creates structured steps
3. Policy evaluates each step
4. Client approves risky steps
5. Orchestrator executes tools in sequence
6. Timeline events stream through `/v1/events`
7. Run status retrievable from `/v1/actions/{run_id}`
8. Reminder worker emits `reminder.due` when due reminders are detected
