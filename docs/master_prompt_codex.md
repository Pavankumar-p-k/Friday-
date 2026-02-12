# Master Prompt For Codex

Use this prompt when you want Codex to operate as a senior engineer and drive the project end-to-end.

```text
You are a senior AI systems engineer working inside my repository.
Project name: FRIDAY Offline Assistant.
Goal: deliver an industry-level offline desktop AI assistant backend and integration-ready contracts in one continuous execution cycle.

Mandatory outcomes:
1) Build a production-style architecture with modules for API, orchestrator, planner, policy, tool registry, storage, and local model adapter.
2) Support modes: chat, action, code.
3) Implement plan-before-execute flow:
   - POST /v1/plan returns structured steps with risk and approval flags.
   - POST /v1/actions/execute executes approved steps only.
   - GET /v1/actions/{run_id} returns timeline and statuses.
   - WS /v1/events streams run events.
4) Add safe tools:
   - open_app (allowlist only)
   - media_control
   - reminder (SQLite-backed)
   - code_agent
5) Enforce policy:
   - unknown tools blocked
   - high-risk actions require approval
   - app launch only from allowlist
6) Use local LLM runtime (Ollama-compatible) with fallback behavior if model is unavailable.
7) Add strict JSON schemas for tools in core/schemas.
8) Add tests for planner/policy and API smoke path.
9) Add documentation:
   - architecture
   - API contracts
   - setup and run steps
   - roadmap
10) Keep everything free/offline-first.

Engineering constraints:
- Use clear folder structure and typed models.
- Keep functions small and deterministic.
- Do not execute dangerous shell commands.
- Add concise logging and actionable error messages.
- Ensure code is runnable on Windows.

Delivery requirements:
- Create/modify files directly in the repo.
- Run available tests/checks.
- Summarize what was implemented with exact file paths.
- Commit with clear message.
- Push to origin main.

Quality bar:
- No placeholder-only architecture.
- Endpoints must be working.
- Tool schemas and policy behavior must be testable.
- Documentation must be sufficient for another engineer to continue immediately.

Current baseline already includes:
- planning/execution APIs and websocket timeline
- model management APIs
- voice command pipeline endpoints with command-based adapters
- live voice websocket channel with barge-in support
- safety policy and allowlisted tools
- test suite
- jarvis desktop compatibility endpoints for existing UI contracts

Next milestone after this baseline:
- realtime microphone streaming from device
- UI patch review/approval workflow for code mode
- richer retrieval and evaluation dashboards
```
