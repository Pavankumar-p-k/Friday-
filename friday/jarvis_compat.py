from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
import subprocess
import time
import uuid
from typing import Any

from friday.config import Settings
from friday.llm import LocalLLMClient
from friday.schemas import AssistantMode, ChatRequest, ExecuteRequest, RunStatus
from friday.storage import Storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clone(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clone(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clone(v) for v in value]
    return value


class JarvisCompatService:
    def __init__(
        self,
        settings: Settings,
        storage: Storage,
        llm: LocalLLMClient,
        orchestrator: Any,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.llm = llm
        self.orchestrator = orchestrator
        self.started_at = time.time()
        self._lock = asyncio.Lock()

        self.mode = "work"
        self.memory = {
            "preferredApps": ["chrome", "spotify", "vscode"],
            "commonCommands": [],
            "lastMode": "work",
            "updatedAtIso": _now_iso(),
        }
        self.suggestions: list[dict[str, Any]] = []
        self.command_history: list[dict[str, Any]] = []
        self.alarms: list[dict[str, Any]] = []
        self.routines = self._default_routines()
        self.automations = self._default_automations()
        self.plugins = self._load_plugins()

    async def get_state(self) -> dict[str, Any]:
        telemetry = await asyncio.to_thread(self._telemetry_snapshot)
        reminders = await asyncio.to_thread(self._map_reminders)
        async with self._lock:
            state = {
                "mode": self.mode,
                "telemetry": telemetry,
                "reminders": reminders,
                "alarms": _clone(self.alarms),
                "routines": _clone(self.routines),
                "memory": _clone(self.memory),
                "suggestions": _clone(self.suggestions),
                "commandHistory": _clone(self.command_history),
                "automations": _clone(self.automations),
                "plugins": _clone(self.plugins),
            }
        return state

    async def set_mode(self, mode: str) -> dict[str, Any]:
        if mode not in {"work", "gaming", "focus", "night"}:
            return await self.get_state()
        async with self._lock:
            self.mode = mode
            self.memory["lastMode"] = mode
            self.memory["updatedAtIso"] = _now_iso()
            self._push_suggestion(f"Mode switched to {mode}", "Mission control")
        return await self.get_state()

    async def run_command(self, command: str, bypass_confirmation: bool = False) -> dict[str, Any]:
        text = command.strip()
        if not text:
            return {
                "result": {"ok": False, "message": "Invalid command input."},
                "state": await self.get_state(),
            }
        lowered = text.lower()

        needs_confirmation = False
        ok = True
        message = "Done."

        if lowered.startswith("/mode "):
            requested = lowered.replace("/mode ", "", 1).strip()
            if requested in {"work", "gaming", "focus", "night"}:
                await self.set_mode(requested)
                message = f"Mode updated to {requested}."
                ok = True
            else:
                message = "Invalid mode. Use work, gaming, focus, night."
                ok = False
        elif lowered.startswith("/ask "):
            prompt = text[5:].strip()
            answer = await self.llm.generate(prompt, mode=AssistantMode.CHAT)
            message = answer
            ok = True
        else:
            chat_response = await self.orchestrator.chat(
                ChatRequest(
                    session_id="jarvis-ui",
                    text=text,
                    mode=AssistantMode.ACTION,
                )
            )
            message = chat_response.reply
            plan = chat_response.plan
            needs_confirmation = bool(plan and any(step.needs_approval for step in plan.steps))

            if needs_confirmation and bypass_confirmation and plan:
                run = await self.orchestrator.execute_plan(
                    ExecuteRequest(
                        plan_id=plan.id,
                        approved_steps=[step.id for step in plan.steps],
                    ),
                    session_id="jarvis-ui",
                )
                message = (
                    f"Executed with status {run.status.value}. "
                    f"Timeline events: {len(run.timeline)}."
                )
                ok = run.status != RunStatus.FAILED
                needs_confirmation = False

            if needs_confirmation and not bypass_confirmation:
                ok = False
                message = "Confirmation needed for this action. Run again with confirmation."
            else:
                if chat_response.run_id:
                    run = await self.orchestrator.get_run(chat_response.run_id)
                    if run is not None:
                        ok = run.status != RunStatus.FAILED

        async with self._lock:
            self._record_command(
                command=text,
                intent=self._infer_intent(text),
                success=ok,
                result_message=message,
            )
            if ok:
                self._push_suggestion(message[:160], "Command result")

        result: dict[str, Any] = {"ok": ok, "message": message}
        if needs_confirmation:
            result["needsConfirmation"] = True

        return {"result": result, "state": await self.get_state()}

    async def complete_reminder(self, reminder_id: str) -> dict[str, Any]:
        try:
            rid = int(reminder_id)
        except ValueError:
            return await self.get_state()
        self.storage.complete_reminder(rid)
        async with self._lock:
            self._push_suggestion(f"Reminder completed: {reminder_id}", "Planner")
        return await self.get_state()

    async def replay_command(self, command_id: str) -> dict[str, Any]:
        async with self._lock:
            found = next((item for item in self.command_history if item["id"] == command_id), None)
        if found is None:
            return {
                "result": {"ok": False, "message": "Command history item not found."},
                "state": await self.get_state(),
            }
        return await self.run_command(str(found["command"]), bypass_confirmation=True)

    async def generate_briefing(self) -> dict[str, Any]:
        reminders = self._map_reminders()
        pending_today = [item for item in reminders if item["status"] == "pending"][:5]
        focus_map = {
            "work": "Prioritize deep work and top priority tasks.",
            "focus": "Minimize context switching and protect concentration blocks.",
            "gaming": "Performance mode: keep background activity minimal.",
            "night": "Low-noise mode: complete quick tasks and wind down.",
        }
        return {
            "headline": f"{len(pending_today)} reminder(s) pending. Mode: {self.mode}.",
            "remindersToday": pending_today,
            "suggestedFocus": focus_map.get(self.mode, focus_map["work"]),
            "generatedAtIso": _now_iso(),
        }

    async def reload_plugins(self) -> dict[str, Any]:
        async with self._lock:
            existing = {item["manifest"]["id"]: item["enabled"] for item in self.plugins}
            loaded = self._load_plugins()
            for item in loaded:
                pid = item["manifest"]["id"]
                if pid in existing:
                    item["enabled"] = bool(existing[pid])
            self.plugins = loaded
            self._push_suggestion(f"Loaded {len(self.plugins)} plugin(s).", "Plugin store")
        return await self.get_state()

    async def set_automation_enabled(self, automation_id: str, enabled: bool) -> dict[str, Any]:
        async with self._lock:
            for item in self.automations:
                if item["id"] == automation_id:
                    item["enabled"] = bool(enabled)
                    self._push_suggestion(
                        f'{item["name"]} is now {"enabled" if enabled else "disabled"}.',
                        "Automation control",
                    )
                    break
        return await self.get_state()

    async def set_plugin_enabled(self, plugin_id: str, enabled: bool) -> dict[str, Any]:
        async with self._lock:
            for item in self.plugins:
                if item["manifest"]["id"] == plugin_id:
                    item["enabled"] = bool(enabled)
                    self._push_suggestion(
                        f'Plugin {item["manifest"]["name"]} {"enabled" if enabled else "disabled"}.',
                        "Plugin control",
                    )
                    break
        return await self.get_state()

    async def terminate_process(self, pid: int, bypass_confirmation: bool = False) -> dict[str, Any]:
        if not bypass_confirmation:
            return {
                "result": {
                    "ok": False,
                    "message": "Confirmation needed before terminating a process.",
                    "needsConfirmation": True,
                },
                "state": await self.get_state(),
            }

        if not isinstance(pid, int) or pid <= 0:
            return {
                "result": {"ok": False, "message": "Invalid PID."},
                "state": await self.get_state(),
            }
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                text=True,
                timeout=12,
            )
            ok = result.returncode == 0
            message = f"Process {pid} terminated." if ok else "Failed to terminate process."
        except Exception:
            ok = False
            message = "Failed to terminate process."

        async with self._lock:
            self._record_command(
                command=f"terminate process {pid}",
                intent="system_info",
                success=ok,
                result_message=message,
            )
        return {"result": {"ok": ok, "message": message}, "state": await self.get_state()}

    def _map_reminders(self) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        items = self.storage.list_reminders(include_done=True)
        result: list[dict[str, Any]] = []
        for item in items:
            due_raw = str(item["due_at"])
            status = "pending"
            if int(item["is_done"]) == 1:
                status = "done"
            else:
                due = self._parse_iso(due_raw)
                if due and due < now:
                    status = "missed"
            result.append(
                {
                    "id": str(item["id"]),
                    "title": str(item["note"]),
                    "note": str(item["note"]),
                    "dueAtIso": due_raw,
                    "status": status,
                    "createdAtIso": str(item["created_at"]),
                }
            )
        return result

    def _telemetry_snapshot(self) -> dict[str, Any]:
        processes = self._top_processes()
        used_mb = sum(item["memoryMb"] for item in processes)
        return {
            "cpuPercent": 0,
            "memoryUsedMb": used_mb,
            "memoryTotalMb": 0,
            "uptimeSec": int(max(0, time.time() - self.started_at)),
            "networkRxKb": 0,
            "networkTxKb": 0,
            "topProcesses": processes,
            "timestampIso": _now_iso(),
        }

    def _top_processes(self) -> list[dict[str, Any]]:
        try:
            output = subprocess.check_output(
                ["tasklist", "/FO", "CSV", "/NH"],
                text=True,
                timeout=8,
                errors="ignore",
            )
            reader = csv.reader(StringIO(output))
            rows = []
            for row in reader:
                if len(row) < 5:
                    continue
                name = row[0]
                pid_raw = row[1]
                mem_raw = row[4]
                try:
                    pid = int(pid_raw)
                except ValueError:
                    continue
                mem_mb = self._parse_mem_mb(mem_raw)
                rows.append({"pid": pid, "name": name, "memoryMb": mem_mb, "cpuPercent": 0})
            rows.sort(key=lambda item: item["memoryMb"], reverse=True)
            return rows[:12]
        except Exception:
            return []

    def _parse_mem_mb(self, value: str) -> int:
        text = value.replace(",", "").replace("K", "").replace("k", "").strip()
        try:
            kb = int(text)
            return max(0, kb // 1024)
        except ValueError:
            return 0

    def _record_command(self, command: str, intent: str, success: bool, result_message: str) -> None:
        record = {
            "id": f"cmd_{uuid.uuid4().hex[:10]}",
            "command": command,
            "intent": intent,
            "success": success,
            "resultMessage": result_message,
            "timestampIso": _now_iso(),
        }
        self.command_history.insert(0, record)
        self.command_history = self.command_history[:120]

        current = [item for item in self.memory["commonCommands"] if item != command]
        current.insert(0, command)
        self.memory["commonCommands"] = current[:30]
        self.memory["updatedAtIso"] = _now_iso()

        app = self._extract_opened_app(command)
        if app:
            preferred = [item for item in self.memory["preferredApps"] if item != app]
            preferred.insert(0, app)
            self.memory["preferredApps"] = preferred[:12]

    def _extract_opened_app(self, command: str) -> str | None:
        lowered = command.lower().strip()
        if lowered.startswith("open "):
            app = lowered.replace("open ", "", 1).strip().split(" ")[0]
            return app if app else None
        return None

    def _push_suggestion(self, text: str, reason: str) -> None:
        if not text:
            return
        self.suggestions.insert(
            0,
            {
                "id": f"sg_{uuid.uuid4().hex[:10]}",
                "text": text,
                "reason": reason,
                "createdAtIso": _now_iso(),
            },
        )
        self.suggestions = self.suggestions[:40]

    def _infer_intent(self, command: str) -> str:
        lowered = command.lower()
        if lowered.startswith("open "):
            return "open_app"
        if "play" in lowered:
            return "play_media"
        if "pause" in lowered:
            return "pause_media"
        if "remind" in lowered:
            return "set_reminder"
        if "alarm" in lowered:
            return "set_alarm"
        if "routine" in lowered:
            return "run_routine"
        if "list reminders" in lowered or "show reminders" in lowered:
            return "list_reminders"
        if lowered.startswith("/mode ") or "system info" in lowered:
            return "system_info"
        return "unknown"

    def _parse_iso(self, value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _default_routines(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "routine_good_morning",
                "name": "good morning",
                "steps": [
                    {"id": "step_open_chrome", "command": "open chrome", "description": "Open browser"},
                    {"id": "step_system_info", "command": "system info", "description": "Load telemetry"},
                ],
                "createdAtIso": _now_iso(),
            },
            {
                "id": "routine_focus_sprint",
                "name": "focus sprint",
                "steps": [
                    {"id": "step_mode_focus", "command": "/mode focus"},
                    {"id": "step_reminder", "command": "remind me standup in 50m"},
                ],
                "createdAtIso": _now_iso(),
            },
        ]

    def _default_automations(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "auto_gaming_helper",
                "name": "Gaming mode helper",
                "enabled": True,
                "conditions": [{"type": "contains_command", "value": "open steam"}],
                "actions": [
                    {"type": "set_mode", "value": "gaming"},
                    {"type": "show_hint", "value": "Gaming mode active: background alerts reduced."},
                ],
                "createdAtIso": _now_iso(),
            },
            {
                "id": "auto_morning_work",
                "name": "Morning work hint",
                "enabled": True,
                "conditions": [
                    {"type": "time_range", "value": "08:00-11:00"},
                    {"type": "mode_is", "value": "work"},
                ],
                "actions": [
                    {
                        "type": "show_hint",
                        "value": "Morning block: tackle highest priority task first.",
                    }
                ],
                "createdAtIso": _now_iso(),
            },
        ]

    def _load_plugins(self) -> list[dict[str, Any]]:
        plugins_dir = self.settings.jarvis_plugins_dir
        if not plugins_dir.is_absolute():
            plugins_dir = (self.settings.workspace_root / plugins_dir).resolve()
        if not plugins_dir.exists() or not plugins_dir.is_dir():
            return []

        items: list[dict[str, Any]] = []
        for child in plugins_dir.iterdir():
            if not child.is_dir():
                continue
            manifest = child / "manifest.json"
            if not manifest.exists():
                continue
            try:
                payload = manifest.read_text(encoding="utf-8", errors="ignore")
                import json

                data = json.loads(payload)
                if not isinstance(data, dict):
                    continue
                plugin_id = str(data.get("id", child.name))
                name = str(data.get("name", child.name))
                version = str(data.get("version", "1.0.0"))
                description = str(data.get("description", ""))
                entry_command = str(data.get("entryCommand", ""))
                permission_level = str(data.get("permissionLevel", "safe"))
                items.append(
                    {
                        "manifest": {
                            "id": plugin_id,
                            "name": name,
                            "version": version,
                            "description": description,
                            "entryCommand": entry_command,
                            "permissionLevel": permission_level,
                        },
                        "enabled": True,
                        "installedAtIso": _now_iso(),
                    }
                )
            except Exception:
                continue
        return items
