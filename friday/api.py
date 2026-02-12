from __future__ import annotations

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from friday.config import Settings
from friday.orchestrator import Orchestrator
from friday.schemas import ActionRun, ChatRequest, ChatResponse, ExecuteRequest, Plan, PlanRequest


def create_app() -> FastAPI:
    settings = Settings.from_env()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.state.orchestrator = Orchestrator(settings)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/chat", response_model=ChatResponse)
    async def chat(payload: ChatRequest) -> ChatResponse:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.chat(payload)

    @app.post("/v1/plan", response_model=Plan)
    async def create_plan(payload: PlanRequest) -> Plan:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.create_plan(payload)

    @app.post("/v1/actions/execute", response_model=ActionRun)
    async def execute(payload: ExecuteRequest) -> ActionRun:
        orchestrator: Orchestrator = app.state.orchestrator
        try:
            return await orchestrator.execute_plan(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/actions/{run_id}", response_model=ActionRun)
    async def get_action(run_id: str) -> ActionRun:
        orchestrator: Orchestrator = app.state.orchestrator
        run = await orchestrator.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        return run

    @app.get("/v1/tools")
    async def list_tools() -> dict[str, list[dict[str, object]]]:
        orchestrator: Orchestrator = app.state.orchestrator
        return {"tools": orchestrator.list_tools()}

    @app.websocket("/v1/events")
    async def events(websocket: WebSocket) -> None:
        orchestrator: Orchestrator = app.state.orchestrator
        await websocket.accept()
        queue = await orchestrator.events.subscribe()
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            await orchestrator.events.unsubscribe(queue)

    return app


app = create_app()

