from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from starlette import status

from friday.config import Settings
from friday.dashboard_auth import DashboardAuthError, DashboardAuthManager, DashboardUser
from friday.dashboard_service import DashboardService
from friday.orchestrator import Orchestrator
from friday.schemas import (
    ActionRun,
    AssistantMode,
    ChatRequest,
    ChatResponse,
    DashboardActionExecuteRequest,
    DashboardActionExecuteResponse,
    DashboardActionHistoryEntry,
    DashboardLogEntry,
    DashboardLoginRequest,
    DashboardSettingsResponse,
    DashboardSettingsUpdateRequest,
    DashboardStatsResponse,
    DashboardTokenResponse,
    DashboardVoiceHistoryEntry,
    ExecuteRequest,
    JarvisAutomationToggleRequest,
    JarvisIdRequest,
    JarvisModeRequest,
    JarvisPluginToggleRequest,
    JarvisRunCommandRequest,
    JarvisTerminateProcessRequest,
    ModelPullRequest,
    PatchApplyRequest,
    PatchApplyResponse,
    PatchProposalRequest,
    PatchProposalResponse,
    Plan,
    PlanRequest,
    VoiceCommandResponse,
    VoiceDispatchRequest,
    VoiceDispatchResponse,
    VoiceLoopStartRequest,
    VoiceLoopStateResponse,
    VoiceSpeakRequest,
    VoiceSpeakResponse,
    VoiceTranscriptionResponse,
)


def create_app() -> FastAPI:
    settings = Settings.from_env()
    orchestrator = Orchestrator(settings)
    auth = DashboardAuthManager()
    dashboard = DashboardService(storage=orchestrator.storage, settings=settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await orchestrator.start_background_workers()
        await dashboard.start(orchestrator.events)
        try:
            yield
        finally:
            await dashboard.stop(orchestrator.events)
            await orchestrator.stop_background_workers()

    app = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.orchestrator = orchestrator
    app.state.dashboard = dashboard
    app.state.auth = auth

    def require_dashboard_user(
        authorization: str | None = Header(default=None),
    ) -> DashboardUser:
        auth: DashboardAuthManager = app.state.auth
        if not auth.enabled:
            return DashboardUser(username=auth.username)
        token = _extract_bearer_token(authorization)
        try:
            return auth.verify_token(token)
        except DashboardAuthError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/dashboard/auth/login", response_model=DashboardTokenResponse)
    async def dashboard_login(payload: DashboardLoginRequest) -> DashboardTokenResponse:
        auth: DashboardAuthManager = app.state.auth
        dashboard: DashboardService = app.state.dashboard
        try:
            token = auth.issue_token(payload.username, payload.password)
        except DashboardAuthError as exc:
            await dashboard.log(
                level="WARNING",
                message="dashboard login failed",
                source="auth",
                meta={"username": payload.username},
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

        await dashboard.log(
            level="INFO",
            message="dashboard login succeeded",
            source="auth",
            meta={"username": payload.username},
        )
        return DashboardTokenResponse(
            access_token=str(token["access_token"]),
            token_type=str(token["token_type"]),
            expires_in=int(token["expires_in"]),
        )

    @app.get("/v1/dashboard/stats", response_model=DashboardStatsResponse)
    async def dashboard_stats(
        user: DashboardUser = Depends(require_dashboard_user),
    ) -> DashboardStatsResponse:
        _ = user
        dashboard: DashboardService = app.state.dashboard
        return DashboardStatsResponse(**dashboard.get_stats())

    @app.get("/v1/dashboard/logs", response_model=list[DashboardLogEntry])
    async def dashboard_logs(
        limit: int = Query(default=100, ge=1, le=500),
        user: DashboardUser = Depends(require_dashboard_user),
    ) -> list[DashboardLogEntry]:
        _ = user
        dashboard: DashboardService = app.state.dashboard
        return [DashboardLogEntry(**row) for row in dashboard.list_logs(limit=limit)]

    @app.get("/v1/dashboard/voice-history", response_model=list[DashboardVoiceHistoryEntry])
    async def dashboard_voice_history(
        limit: int = Query(default=100, ge=1, le=500),
        user: DashboardUser = Depends(require_dashboard_user),
    ) -> list[DashboardVoiceHistoryEntry]:
        _ = user
        dashboard: DashboardService = app.state.dashboard
        return [DashboardVoiceHistoryEntry(**row) for row in dashboard.list_voice_history(limit=limit)]

    @app.get("/v1/dashboard/settings", response_model=DashboardSettingsResponse)
    async def dashboard_settings_get(
        user: DashboardUser = Depends(require_dashboard_user),
    ) -> DashboardSettingsResponse:
        _ = user
        dashboard: DashboardService = app.state.dashboard
        return DashboardSettingsResponse(settings=dashboard.get_settings())

    @app.put("/v1/dashboard/settings", response_model=DashboardSettingsResponse)
    async def dashboard_settings_update(
        payload: DashboardSettingsUpdateRequest,
        user: DashboardUser = Depends(require_dashboard_user),
    ) -> DashboardSettingsResponse:
        dashboard: DashboardService = app.state.dashboard
        settings_map = dashboard.update_settings(payload.updates)
        await dashboard.log(
            level="INFO",
            message="dashboard settings updated",
            source="dashboard",
            meta={"actor": user.username, "keys": list(payload.updates.keys())},
        )
        return DashboardSettingsResponse(settings=settings_map)

    @app.post("/v1/dashboard/actions/execute", response_model=DashboardActionExecuteResponse)
    async def dashboard_execute_action(
        payload: DashboardActionExecuteRequest,
        user: DashboardUser = Depends(require_dashboard_user),
    ) -> DashboardActionExecuteResponse:
        orchestrator: Orchestrator = app.state.orchestrator
        dashboard: DashboardService = app.state.dashboard
        result = await orchestrator.execute_tool_action(
            session_id=payload.session_id,
            actor=user.username,
            tool=payload.tool,
            args=payload.args,
        )
        await dashboard.log(
            level="INFO" if result.success else "ERROR",
            message="dashboard action execute",
            source="dashboard.actions",
            meta={
                "actor": user.username,
                "session_id": payload.session_id,
                "tool": payload.tool,
                "success": result.success,
            },
        )
        await dashboard.realtime.publish(
            {
                "type": "dashboard.action.executed",
                "tool": payload.tool,
                "success": result.success,
                "session_id": payload.session_id,
            }
        )
        return DashboardActionExecuteResponse(
            success=result.success,
            message=result.message,
            data=result.data,
            tool=payload.tool,
        )

    @app.get("/v1/dashboard/actions/history", response_model=list[DashboardActionHistoryEntry])
    async def dashboard_action_history(
        limit: int = Query(default=100, ge=1, le=500),
        user: DashboardUser = Depends(require_dashboard_user),
    ) -> list[DashboardActionHistoryEntry]:
        _ = user
        dashboard: DashboardService = app.state.dashboard
        return [DashboardActionHistoryEntry(**row) for row in dashboard.list_action_history(limit=limit)]

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

    @app.get("/v1/models")
    async def list_models() -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        models = await orchestrator.list_models()
        return {"models": models, "count": len(models)}

    @app.post("/v1/models/pull")
    async def pull_model(payload: ModelPullRequest) -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.pull_model(payload.model)

    @app.get("/v1/models/{model_name}")
    async def show_model(model_name: str) -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.show_model(model_name)

    @app.get("/v1/jarvis/state")
    async def jarvis_get_state() -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.jarvis_get_state()

    @app.post("/v1/jarvis/run-command")
    async def jarvis_run_command(payload: JarvisRunCommandRequest) -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.jarvis_run_command(
            command=payload.command,
            bypass_confirmation=payload.bypass_confirmation,
        )

    @app.post("/v1/jarvis/set-mode")
    async def jarvis_set_mode(payload: JarvisModeRequest) -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.jarvis_set_mode(mode=payload.mode)

    @app.post("/v1/jarvis/complete-reminder")
    async def jarvis_complete_reminder(payload: JarvisIdRequest) -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.jarvis_complete_reminder(reminder_id=payload.id)

    @app.post("/v1/jarvis/replay-command")
    async def jarvis_replay_command(payload: JarvisIdRequest) -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.jarvis_replay_command(command_id=payload.id)

    @app.post("/v1/jarvis/generate-briefing")
    async def jarvis_generate_briefing() -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.jarvis_generate_briefing()

    @app.post("/v1/jarvis/reload-plugins")
    async def jarvis_reload_plugins() -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.jarvis_reload_plugins()

    @app.post("/v1/jarvis/set-automation-enabled")
    async def jarvis_set_automation_enabled(
        payload: JarvisAutomationToggleRequest,
    ) -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.jarvis_set_automation_enabled(
            automation_id=payload.id,
            enabled=payload.enabled,
        )

    @app.post("/v1/jarvis/set-plugin-enabled")
    async def jarvis_set_plugin_enabled(payload: JarvisPluginToggleRequest) -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.jarvis_set_plugin_enabled(
            plugin_id=payload.plugin_id,
            enabled=payload.enabled,
        )

    @app.post("/v1/jarvis/terminate-process")
    async def jarvis_terminate_process(payload: JarvisTerminateProcessRequest) -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.jarvis_terminate_process(
            pid=payload.pid,
            bypass_confirmation=payload.bypass_confirmation,
        )

    @app.post("/v1/code/propose_patch", response_model=PatchProposalResponse)
    async def propose_patch(payload: PatchProposalRequest) -> PatchProposalResponse:
        orchestrator: Orchestrator = app.state.orchestrator
        result = await orchestrator.propose_patch(task=payload.task, path=payload.path)
        return PatchProposalResponse(
            ok=bool(result.get("ok", False)),
            proposal=str(result.get("proposal", "")),
            citations=[str(item) for item in result.get("citations", [])],
            message=str(result.get("message")) if result.get("message") else None,
        )

    @app.post("/v1/code/apply_patch", response_model=PatchApplyResponse)
    async def apply_patch(payload: PatchApplyRequest) -> PatchApplyResponse:
        orchestrator: Orchestrator = app.state.orchestrator
        result = await orchestrator.apply_patch(
            patch=payload.patch,
            dry_run=payload.dry_run,
        )
        return PatchApplyResponse(
            ok=bool(result.get("ok", False)),
            applied=bool(result.get("applied", False)),
            dry_run=bool(result.get("dry_run", payload.dry_run)),
            message=str(result.get("message", "")),
        )

    @app.post("/v1/voice/transcribe", response_model=VoiceTranscriptionResponse)
    async def voice_transcribe(file: UploadFile = File(...)) -> VoiceTranscriptionResponse:
        orchestrator: Orchestrator = app.state.orchestrator
        path = await _save_upload(orchestrator=orchestrator, file=file)
        result = await orchestrator.transcribe_audio(path)
        return VoiceTranscriptionResponse(
            transcript=result.get("text", ""),
            backend=result.get("backend", "none"),
            warning=result.get("warning", None) or None,
        )

    @app.post("/v1/voice/speak", response_model=VoiceSpeakResponse)
    async def voice_speak(payload: VoiceSpeakRequest) -> VoiceSpeakResponse:
        orchestrator: Orchestrator = app.state.orchestrator
        result = await orchestrator.synthesize_text(payload.text)
        return VoiceSpeakResponse(
            audio_path=result.get("audio_path", ""),
            backend=result.get("backend", "none"),
            warning=result.get("warning", None) or None,
        )

    @app.post("/v1/voice/command", response_model=VoiceCommandResponse)
    async def voice_command(
        file: UploadFile = File(...),
        mode: AssistantMode = Form(default=AssistantMode.ACTION),
        session_id: str = Form(default="default"),
    ) -> VoiceCommandResponse:
        orchestrator: Orchestrator = app.state.orchestrator
        dashboard: DashboardService = app.state.dashboard
        path = await _save_upload(orchestrator=orchestrator, file=file)
        result = await orchestrator.process_voice_command(
            audio_path=path,
            session_id=session_id,
            mode=mode,
        )
        await dashboard.realtime.publish(
            {
                "type": "dashboard.voice_history.updated",
                "session_id": session_id,
                "mode": mode.value,
            }
        )
        return result

    @app.post("/v1/voice/dispatch", response_model=VoiceDispatchResponse)
    async def voice_dispatch(payload: VoiceDispatchRequest) -> VoiceDispatchResponse:
        orchestrator: Orchestrator = app.state.orchestrator
        dashboard: DashboardService = app.state.dashboard
        result = await orchestrator.dispatch_transcribed_speech(
            transcript=payload.transcript,
            session_id=payload.session_id,
            context=payload.context,
        )
        await dashboard.realtime.publish(
            {
                "type": "dashboard.voice_history.updated",
                "session_id": payload.session_id,
                "mode": result.mode.value,
            }
        )
        return result

    @app.post("/v1/voice/interrupt")
    async def voice_interrupt(payload: dict[str, str]) -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        session_id = payload.get("session_id", "default")
        state = await orchestrator.interrupt_voice_session(session_id=session_id)
        return {"ok": True, "session_id": state.session_id, "interrupted": state.interrupted}

    @app.get("/v1/voice/loop/state", response_model=VoiceLoopStateResponse)
    async def voice_loop_state() -> VoiceLoopStateResponse:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.get_voice_loop_state()

    @app.post("/v1/voice/loop/start", response_model=VoiceLoopStateResponse)
    async def voice_loop_start(payload: VoiceLoopStartRequest) -> VoiceLoopStateResponse:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.start_voice_loop(
            session_id=payload.session_id,
            mode=payload.mode,
            require_wake_word=payload.require_wake_word,
            poll_interval_sec=payload.poll_interval_sec,
        )

    @app.post("/v1/voice/loop/stop", response_model=VoiceLoopStateResponse)
    async def voice_loop_stop() -> VoiceLoopStateResponse:
        orchestrator: Orchestrator = app.state.orchestrator
        return await orchestrator.stop_voice_loop()

    @app.post("/v1/voice/wakeword/check")
    async def wakeword_check(payload: VoiceSpeakRequest) -> dict[str, object]:
        orchestrator: Orchestrator = app.state.orchestrator
        detected = orchestrator.voice.wake_word_detected(payload.text)
        return {"detected": detected, "wake_words": list(orchestrator.settings.voice_wake_words)}

    @app.websocket("/v1/voice/live")
    async def voice_live(websocket: WebSocket) -> None:
        orchestrator: Orchestrator = app.state.orchestrator
        await websocket.accept()
        session_id = f"live-{id(websocket)}"
        mode = AssistantMode.ACTION
        await orchestrator.register_voice_session(session_id=session_id, mode=mode)
        await websocket.send_json(
            {
                "type": "session.started",
                "session_id": session_id,
                "mode": mode.value,
            }
        )

        try:
            while True:
                message = await websocket.receive_json()
                msg_type = str(message.get("type", "")).strip().lower()
                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                if msg_type == "start":
                    requested_session = str(message.get("session_id", session_id)).strip() or session_id
                    requested_mode = _parse_mode(message.get("mode", mode.value))
                    session_id = requested_session
                    mode = requested_mode
                    await orchestrator.register_voice_session(session_id=session_id, mode=mode)
                    await websocket.send_json(
                        {
                            "type": "session.started",
                            "session_id": session_id,
                            "mode": mode.value,
                        }
                    )
                    continue

                if msg_type == "partial":
                    text = str(message.get("text", ""))
                    state = await orchestrator.set_voice_partial(session_id=session_id, text=text)
                    await websocket.send_json(
                        {
                            "type": "partial.ack",
                            "session_id": state.session_id,
                            "text": state.last_partial,
                        }
                    )
                    continue

                if msg_type == "barge_in":
                    state = await orchestrator.interrupt_voice_session(session_id=session_id)
                    await websocket.send_json(
                        {
                            "type": "barge_in.ack",
                            "session_id": state.session_id,
                            "interrupted": state.interrupted,
                        }
                    )
                    continue

                if msg_type == "final":
                    text = str(message.get("text", "")).strip()
                    message_mode = _parse_mode(message.get("mode", mode.value))
                    result = await orchestrator.process_voice_text(
                        transcript=text,
                        session_id=session_id,
                        mode=message_mode,
                    )
                    await websocket.send_json(
                        {
                            "type": "final.result",
                            "session_id": session_id,
                            "payload": result.model_dump(),
                        }
                    )
                    continue

                if msg_type == "stop":
                    await orchestrator.close_voice_session(session_id=session_id)
                    await websocket.send_json({"type": "session.stopped", "session_id": session_id})
                    return

                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"unknown message type: {msg_type}",
                    }
                )
        except WebSocketDisconnect:
            pass
        finally:
            await orchestrator.close_voice_session(session_id=session_id)

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

    @app.websocket("/v1/dashboard/ws")
    async def dashboard_ws(websocket: WebSocket, token: str = Query(default="")) -> None:
        dashboard: DashboardService = app.state.dashboard
        auth: DashboardAuthManager = app.state.auth

        if auth.enabled:
            try:
                auth.verify_token(token)
            except DashboardAuthError:
                await websocket.close(code=4401, reason="Unauthorized")
                return

        await websocket.accept()
        queue = await dashboard.realtime.subscribe()
        try:
            await websocket.send_json(
                {
                    "type": "dashboard.snapshot",
                    "stats": dashboard.get_stats(),
                }
            )
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            await dashboard.realtime.unsubscribe(queue)

    return app


def _parse_mode(value: Any) -> AssistantMode:
    text = str(value).strip().lower()
    if text == AssistantMode.CODE.value:
        return AssistantMode.CODE
    if text == AssistantMode.CHAT.value:
        return AssistantMode.CHAT
    return AssistantMode.ACTION


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    text = authorization.strip()
    parts = text.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expected Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return parts[1].strip()


async def _save_upload(orchestrator: Orchestrator, file: UploadFile) -> Path:
    max_bytes = max(1, orchestrator.settings.voice_max_upload_bytes)
    target = orchestrator.voice.allocate_upload_path(file.filename or "audio.bin")
    written = 0
    try:
        with target.open("wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Uploaded file exceeds limit ({max_bytes} bytes).",
                    )
                handle.write(chunk)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to save uploaded file: {exc}") from exc
    finally:
        await file.close()
    return target


app = create_app()
