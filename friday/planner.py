from __future__ import annotations

from datetime import datetime, timedelta
import re
import uuid

from friday.config import Settings
from friday.policy import PolicyEngine
from friday.schemas import AssistantMode, Plan, PlanRequest, PlanStep


class Planner:
    def __init__(self, settings: Settings, policy: PolicyEngine) -> None:
        self.settings = settings
        self.policy = policy

    async def create_plan(self, request: PlanRequest) -> Plan:
        steps = self._extract_steps(request.goal, request.mode)
        for step in steps:
            decision = self.policy.evaluate(step)
            step.risk = decision.risk
            step.needs_approval = decision.needs_approval
            if not decision.allowed:
                step.description = f"{step.description} [BLOCKED: {decision.reason}]"

        limited_steps = steps[: self.settings.max_plan_steps]
        return Plan(
            id=f"plan_{uuid.uuid4().hex[:10]}",
            goal=request.goal,
            mode=request.mode,
            steps=limited_steps,
        )

    def _extract_steps(self, goal: str, mode: AssistantMode) -> list[PlanStep]:
        text = goal.strip()
        lowered = text.lower()
        steps: list[PlanStep] = []

        if mode == AssistantMode.CODE:
            return [
                PlanStep(
                    id="step_1",
                    description="Generate or explain code for the request",
                    tool="code_agent",
                    args={"task": text, "language": self._infer_language(lowered)},
                )
            ]

        app_name = self._extract_app_name(lowered)
        if app_name:
            steps.append(
                PlanStep(
                    id=f"step_{len(steps) + 1}",
                    description=f"Open {app_name}",
                    tool="open_app",
                    args={"app_name": app_name},
                )
            )

        if "remind" in lowered or "reminder" in lowered:
            note, due_at = self._extract_reminder_payload(text)
            steps.append(
                PlanStep(
                    id=f"step_{len(steps) + 1}",
                    description="Create a reminder",
                    tool="reminder",
                    args={"action": "set", "note": note, "due_at": due_at},
                )
            )

        if "list reminders" in lowered or "show reminders" in lowered:
            steps.append(
                PlanStep(
                    id=f"step_{len(steps) + 1}",
                    description="List active reminders",
                    tool="reminder",
                    args={"action": "list"},
                )
            )

        if "play music" in lowered or lowered.startswith("play "):
            target = self._extract_media_target(text)
            steps.append(
                PlanStep(
                    id=f"step_{len(steps) + 1}",
                    description="Play requested media",
                    tool="media_control",
                    args={"action": "play", "target": target},
                )
            )

        if any(token in lowered for token in ("write code", "generate code", "create script")):
            steps.append(
                PlanStep(
                    id=f"step_{len(steps) + 1}",
                    description="Generate code output",
                    tool="code_agent",
                    args={"task": text, "language": self._infer_language(lowered)},
                )
            )

        shell_command = self._extract_shell_command(text)
        if shell_command:
            steps.append(
                PlanStep(
                    id=f"step_{len(steps) + 1}",
                    description="Run a safe shell command",
                    tool="safe_shell",
                    args={"command": shell_command},
                )
            )

        if not steps:
            steps.append(
                PlanStep(
                    id="step_1",
                    description="Respond directly with local model",
                    tool=None,
                    args={},
                )
            )
        return steps

    def _extract_app_name(self, lowered_text: str) -> str | None:
        known = tuple(self.settings.allowed_apps.keys())
        for app in known:
            if f"open {app}" in lowered_text or lowered_text == app:
                return app

        match = re.search(r"\bopen\s+([a-z0-9._ -]+)", lowered_text)
        if match:
            candidate = match.group(1).strip().split()[0]
            if candidate:
                return candidate
        return None

    def _extract_reminder_payload(self, text: str) -> tuple[str, str]:
        lowered = text.lower()
        now = datetime.utcnow()
        due = now + timedelta(minutes=30)
        note = text

        match = re.search(r"in\s+(\d+)\s+(minute|minutes|hour|hours)", lowered)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)
            if "hour" in unit:
                due = now + timedelta(hours=amount)
            else:
                due = now + timedelta(minutes=amount)

        strip_tokens = ["remind me to", "set reminder to", "reminder to"]
        for token in strip_tokens:
            idx = lowered.find(token)
            if idx >= 0:
                note = text[idx + len(token) :].strip()
                break

        if not note:
            note = "Reminder"
        return note, due.isoformat() + "Z"

    def _extract_media_target(self, text: str) -> str:
        lowered = text.lower()
        if lowered.startswith("play "):
            return text[5:].strip() or "music"
        return "music"

    def _infer_language(self, lowered_text: str) -> str:
        if "python" in lowered_text:
            return "python"
        if "javascript" in lowered_text or "node" in lowered_text:
            return "javascript"
        if "java" in lowered_text:
            return "java"
        return "text"

    def _extract_shell_command(self, text: str) -> str | None:
        lowered = text.lower().strip()
        token = "run command "
        if lowered.startswith(token):
            return text[len(token) :].strip()
        token = "execute command "
        if lowered.startswith(token):
            return text[len(token) :].strip()
        return None
