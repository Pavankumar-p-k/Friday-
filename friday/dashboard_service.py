from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from friday.config import Settings
from friday.events import InMemoryEventBus
from friday.storage import Storage


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DashboardService:
    def __init__(self, storage: Storage, settings: Settings) -> None:
        self.storage = storage
        self.settings = settings
        self.realtime = InMemoryEventBus(queue_size=400)
        self.started_at = _utc_now_iso()
        self._subscription: asyncio.Queue[dict[str, Any]] | None = None
        self._ingest_task: asyncio.Task[None] | None = None

    async def start(self, source_events: InMemoryEventBus) -> None:
        if self._ingest_task is not None:
            return
        self._subscription = await source_events.subscribe()
        self._ingest_task = asyncio.create_task(self._consume_source_events(), name="dashboard-event-ingest")
        self.storage.save_dashboard_log(
            level="INFO",
            message="Dashboard service started",
            source="dashboard",
            meta={"started_at": self.started_at},
        )

    async def stop(self, source_events: InMemoryEventBus) -> None:
        if self._ingest_task is not None:
            self._ingest_task.cancel()
            try:
                await self._ingest_task
            except asyncio.CancelledError:
                pass
            self._ingest_task = None
        if self._subscription is not None:
            await source_events.unsubscribe(self._subscription)
            self._subscription = None
        self.storage.save_dashboard_log(
            level="INFO",
            message="Dashboard service stopped",
            source="dashboard",
            meta={"stopped_at": _utc_now_iso()},
        )

    async def _consume_source_events(self) -> None:
        assert self._subscription is not None
        queue = self._subscription
        while True:
            event = await queue.get()
            await self.ingest_event(event)

    async def ingest_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type", "")).strip() or "unknown"
        source = "orchestrator"
        level = "INFO"
        if event_type.endswith(".error") or event_type.endswith(".failed"):
            level = "ERROR"
        elif event_type.endswith(".blocked"):
            level = "WARNING"

        self.storage.save_dashboard_log(
            level=level,
            message=f"assistant event: {event_type}",
            source=source,
            meta={"event": _safe_jsonable(event)},
        )
        await self.realtime.publish(
            {
                "type": "dashboard.event",
                "timestamp": _utc_now_iso(),
                "event_type": event_type,
                "payload": _safe_jsonable(event),
            }
        )

    async def log(
        self,
        *,
        level: str,
        message: str,
        source: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.storage.save_dashboard_log(
            level=level,
            message=message,
            source=source,
            meta=_safe_jsonable(meta or {}),
        )
        await self.realtime.publish(
            {
                "type": "dashboard.log",
                "timestamp": _utc_now_iso(),
                "level": level.upper(),
                "message": message,
                "source": source,
                "meta": _safe_jsonable(meta or {}),
            }
        )

    async def record_voice_command(
        self,
        *,
        session_id: str,
        transcript: str,
        reply: str,
        mode: str,
        llm_backend: str,
        stt_backend: str = "",
        tts_backend: str = "",
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.storage.save_voice_history(
            session_id=session_id,
            transcript=transcript,
            reply=reply,
            mode=mode,
            llm_backend=llm_backend,
            stt_backend=stt_backend,
            tts_backend=tts_backend,
            meta=_safe_jsonable(meta or {}),
        )
        await self.realtime.publish(
            {
                "type": "dashboard.voice_history.updated",
                "timestamp": _utc_now_iso(),
                "session_id": session_id,
            }
        )

    async def record_action(
        self,
        *,
        session_id: str,
        actor: str,
        tool: str,
        args: dict[str, Any],
        success: bool,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.storage.save_action_history(
            session_id=session_id,
            actor=actor,
            tool=tool,
            args=_safe_jsonable(args),
            success=success,
            message=message,
            data=_safe_jsonable(data or {}),
        )
        await self.realtime.publish(
            {
                "type": "dashboard.action_history.updated",
                "timestamp": _utc_now_iso(),
                "session_id": session_id,
                "tool": tool,
                "success": success,
            }
        )

    def get_stats(self) -> dict[str, Any]:
        persisted = self.storage.get_dashboard_stats()
        return {
            **persisted,
            "started_at": self.started_at,
            "uptime_sec": _uptime_seconds(self.started_at),
        }

    def list_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.storage.list_dashboard_logs(limit=limit)

    def list_voice_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.storage.list_voice_history(limit=limit)

    def list_action_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.storage.list_action_history(limit=limit)

    def get_settings(self) -> dict[str, str]:
        defaults = {
            "app_name": self.settings.app_name,
            "auto_execute_low_risk": str(self.settings.auto_execute_low_risk).lower(),
            "voice_loop_require_wake_word": str(self.settings.voice_loop_require_wake_word).lower(),
            "voice_loop_poll_interval_sec": str(self.settings.voice_loop_poll_interval_sec),
            "voice_loop_mode": self.settings.voice_loop_mode,
            "allowed_tools": ",".join(self.settings.allowed_tools),
            "request_timeout_sec": str(self.settings.request_timeout_sec),
        }
        stored = self.storage.get_dashboard_settings()
        return {**defaults, **stored}

    def update_settings(self, updates: dict[str, str]) -> dict[str, str]:
        allowed_keys = {
            "auto_execute_low_risk",
            "voice_loop_require_wake_word",
            "voice_loop_poll_interval_sec",
            "voice_loop_mode",
            "request_timeout_sec",
        }
        for key, value in updates.items():
            if key not in allowed_keys:
                continue
            self.storage.upsert_dashboard_setting(key, str(value))
        return self.get_settings()


def _uptime_seconds(started_at_iso: str) -> int:
    try:
        started_at = datetime.fromisoformat(started_at_iso)
    except ValueError:
        return 0
    delta = datetime.now(timezone.utc) - started_at
    return max(0, int(delta.total_seconds()))


def _safe_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_safe_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _safe_jsonable(item) for key, item in value.items()}
    return str(value)
