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
  "reply": "Plan created with 1 step(s).",
  "citations": [],
  "plan": {
    "id": "plan_123",
    "goal": "open notepad",
    "mode": "action",
    "status": "draft",
    "created_at": "2026-02-12T12:00:00Z",
    "steps": []
  },
  "run_id": null
}
```

## `POST /v1/plan`

Request:

```json
{
  "goal": "set a reminder in 20 minutes to drink water",
  "mode": "action",
  "context": {}
}
```

Response:

```json
{
  "id": "plan_123",
  "goal": "set a reminder in 20 minutes to drink water",
  "mode": "action",
  "status": "draft",
  "created_at": "2026-02-12T12:00:00Z",
  "steps": []
}
```

## `POST /v1/actions/execute`

Request:

```json
{
  "plan_id": "plan_123",
  "approved_steps": ["step_1"]
}
```

Response:

```json
{
  "id": "run_123",
  "plan_id": "plan_123",
  "status": "completed",
  "started_at": "2026-02-12T12:00:03Z",
  "finished_at": "2026-02-12T12:00:05Z",
  "timeline": []
}
```

## `GET /v1/actions/{run_id}`

Returns action run status and timeline.

## `GET /v1/tools`

Returns tool metadata and JSON input schema for UI integration.

## `WS /v1/events`

Streams runtime events:

- `plan.created`
- `run.started`
- `step.running`
- `step.success`
- `step.failed`
- `run.finished`

