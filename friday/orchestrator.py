from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
import uuid
from typing import Any

from friday.config import Settings
from friday.code_workflow import CodeWorkflow
from friday.events import InMemoryEventBus
from friday.llm import LocalLLMClient
from friday.model_manager import ModelManager
from friday.planner import Planner
from friday.policy import PolicyEngine
from friday.schemas import (
    ActionRun,
    AssistantMode,
    ChatRequest,
    ChatResponse,
    ExecuteRequest,
    Plan,
    PlanRequest,
    PlanStatus,
    RunStatus,
    RunStepEvent,
    StepStatus,
    VoiceCommandResponse,
    utc_now_iso,
)
from friday.storage import Storage
from friday.tools.registry import ToolRegistry, build_default_registry
from friday.voice import VoicePipeline


class Orchestrator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.storage = Storage(self.settings.db_path)
        self.events = InMemoryEventBus()
        self.llm = LocalLLMClient(self.settings)
        self.code_workflow = CodeWorkflow(self.settings, self.llm)
        self.policy = PolicyEngine(self.settings)
        self.planner = Planner(self.settings, self.policy)
        self.registry: ToolRegistry = build_default_registry(self.settings, self.storage, self.llm)
        self.model_manager = ModelManager(self.settings)
        self.voice = VoicePipeline(self.settings)

        self._plans: dict[str, Plan] = {}
        self._runs: dict[str, ActionRun] = {}
        self._lock = asyncio.Lock()

        self._running = False
        self._reminder_task: asyncio.Task[None] | None = None

    async def start_background_workers(self) -> None:
        if self._running:
            return
        self._running = True
        self._reminder_task = asyncio.create_task(self._reminder_due_worker())

    async def stop_background_workers(self) -> None:
        self._running = False
        if self._reminder_task is None:
            return
        self._reminder_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._reminder_task
        self._reminder_task = None

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if request.mode == AssistantMode.CHAT:
            prompt = self._chat_prompt_with_history(
                session_id=request.session_id,
                user_text=request.text,
            )
            reply = await self.llm.generate(prompt, mode=AssistantMode.CHAT)
            self.storage.save_history(request.session_id, request.text, reply, request.mode.value)
            return ChatResponse(reply=reply, citations=[])

        plan_request = PlanRequest(goal=request.text, mode=request.mode, context=request.context)
        plan = await self.create_plan(plan_request)

        if request.mode == AssistantMode.CODE:
            reply = "Code plan created. Approve the step to run code generation."
            self.storage.save_history(request.session_id, request.text, reply, request.mode.value)
            return ChatResponse(reply=reply, plan=plan)

        risky_steps = [step.id for step in plan.steps if step.needs_approval]
        if not risky_steps and self.settings.auto_execute_low_risk:
            run = await self.execute_plan(
                ExecuteRequest(plan_id=plan.id, approved_steps=[]),
                session_id=request.session_id,
            )
            reply = self._summarize_run(run)
            return ChatResponse(reply=reply, plan=plan, run_id=run.id)

        reply = (
            f"Plan created with {len(plan.steps)} step(s). "
            f"Approval required for steps: {', '.join(risky_steps) if risky_steps else 'none'}."
        )
        self.storage.save_history(request.session_id, request.text, reply, request.mode.value)
        return ChatResponse(reply=reply, plan=plan)

    async def create_plan(self, request: PlanRequest) -> Plan:
        plan = await self.planner.create_plan(request)
        async with self._lock:
            self._plans[plan.id] = plan
        await self.events.publish(
            {
                "type": "plan.created",
                "timestamp": utc_now_iso(),
                "plan_id": plan.id,
                "mode": plan.mode.value,
                "steps": [step.model_dump() for step in plan.steps],
            }
        )
        return plan

    async def execute_plan(self, request: ExecuteRequest, session_id: str = "default") -> ActionRun:
        async with self._lock:
            plan = self._plans.get(request.plan_id)
        if plan is None:
            raise KeyError(f"Plan not found: {request.plan_id}")

        run = ActionRun(
            id=f"run_{uuid.uuid4().hex[:10]}",
            plan_id=plan.id,
            status=RunStatus.RUNNING,
            started_at=utc_now_iso(),
            timeline=[],
        )
        async with self._lock:
            self._runs[run.id] = run

        await self.events.publish(
            {
                "type": "run.started",
                "timestamp": utc_now_iso(),
                "run_id": run.id,
                "plan_id": plan.id,
            }
        )

        failures = 0
        successes = 0

        for step in plan.steps:
            decision = self.policy.evaluate(step)
            if not decision.allowed:
                failures += 1
                self._add_timeline(
                    run,
                    step_id=step.id,
                    status=StepStatus.BLOCKED,
                    message=decision.reason or "Blocked by policy.",
                )
                await self.events.publish(
                    {
                        "type": "step.blocked",
                        "timestamp": utc_now_iso(),
                        "run_id": run.id,
                        "step_id": step.id,
                        "reason": decision.reason,
                    }
                )
                continue

            if step.needs_approval and step.id not in request.approved_steps:
                self._add_timeline(
                    run,
                    step_id=step.id,
                    status=StepStatus.SKIPPED,
                    message="Skipped because approval is missing.",
                )
                await self.events.publish(
                    {
                        "type": "step.skipped",
                        "timestamp": utc_now_iso(),
                        "run_id": run.id,
                        "step_id": step.id,
                    }
                )
                continue

            await self.events.publish(
                {
                    "type": "step.running",
                    "timestamp": utc_now_iso(),
                    "run_id": run.id,
                    "step_id": step.id,
                }
            )
            self._add_timeline(
                run,
                step_id=step.id,
                status=StepStatus.RUNNING,
                message=step.description,
            )

            if step.tool is None:
                answer = await self.llm.generate(plan.goal, mode=plan.mode)
                successes += 1
                self._add_timeline(
                    run,
                    step_id=step.id,
                    status=StepStatus.SUCCESS,
                    message="Direct response generated.",
                    data={"response": answer},
                )
                await self.events.publish(
                    {
                        "type": "step.success",
                        "timestamp": utc_now_iso(),
                        "run_id": run.id,
                        "step_id": step.id,
                    }
                )
                continue

            result = await self.registry.execute(step.tool, step.args)
            if result.success:
                successes += 1
                self._add_timeline(
                    run,
                    step_id=step.id,
                    status=StepStatus.SUCCESS,
                    message=result.message,
                    data=result.data,
                )
                await self.events.publish(
                    {
                        "type": "step.success",
                        "timestamp": utc_now_iso(),
                        "run_id": run.id,
                        "step_id": step.id,
                    }
                )
            else:
                failures += 1
                self._add_timeline(
                    run,
                    step_id=step.id,
                    status=StepStatus.FAILED,
                    message=result.message,
                    data=result.data,
                )
                await self.events.publish(
                    {
                        "type": "step.failed",
                        "timestamp": utc_now_iso(),
                        "run_id": run.id,
                        "step_id": step.id,
                        "error": result.message,
                    }
                )

        if failures == 0 and successes > 0:
            run.status = RunStatus.COMPLETED
        elif failures > 0 and successes > 0:
            run.status = RunStatus.PARTIAL
        else:
            run.status = RunStatus.FAILED
        run.finished_at = utc_now_iso()
        plan.status = PlanStatus.COMPLETED if run.status != RunStatus.FAILED else PlanStatus.FAILED

        summary = self._summarize_run(run)
        self.storage.save_history(
            session_id=session_id,
            user_text=plan.goal,
            assistant_text=summary,
            mode=plan.mode.value,
        )

        await self.events.publish(
            {
                "type": "run.finished",
                "timestamp": utc_now_iso(),
                "run_id": run.id,
                "status": run.status.value,
            }
        )
        return run

    async def get_run(self, run_id: str) -> ActionRun | None:
        async with self._lock:
            return self._runs.get(run_id)

    async def list_models(self) -> list[dict[str, Any]]:
        return await self.model_manager.list_models()

    async def pull_model(self, model_name: str) -> dict[str, Any]:
        return await self.model_manager.pull_model(model_name)

    async def show_model(self, model_name: str) -> dict[str, Any]:
        return await self.model_manager.show_model(model_name)

    async def propose_patch(self, task: str, path: str | None = None) -> dict[str, object]:
        return await self.code_workflow.propose_patch(task=task, path=path)

    async def transcribe_audio(self, audio_path: Path) -> dict[str, str]:
        return await self.voice.transcribe(audio_path)

    async def synthesize_text(self, text: str) -> dict[str, str]:
        return await self.voice.synthesize(text)

    async def process_voice_command(
        self,
        audio_path: Path,
        session_id: str = "default",
        mode: AssistantMode = AssistantMode.ACTION,
    ) -> VoiceCommandResponse:
        stt = await self.transcribe_audio(audio_path)
        transcript = stt.get("text", "").strip()
        warnings: list[str] = []
        if stt.get("warning"):
            warnings.append(str(stt["warning"]))

        if not transcript:
            return VoiceCommandResponse(
                transcript="",
                reply="Could not transcribe audio.",
                audio_path="",
                stt_backend=stt.get("backend", "none"),
                tts_backend="none",
                warnings=warnings or ["transcription failed"],
            )

        response = await self.chat(
            ChatRequest(
                session_id=session_id,
                text=transcript,
                mode=mode,
                context={},
            )
        )
        tts = await self.synthesize_text(response.reply)
        if tts.get("warning"):
            warnings.append(str(tts["warning"]))

        return VoiceCommandResponse(
            transcript=transcript,
            reply=response.reply,
            plan=response.plan,
            run_id=response.run_id,
            audio_path=tts.get("audio_path", ""),
            stt_backend=stt.get("backend", "none"),
            tts_backend=tts.get("backend", "none"),
            warnings=warnings,
        )

    def list_tools(self) -> list[dict[str, Any]]:
        return self.registry.list_tools()

    def _chat_prompt_with_history(self, session_id: str, user_text: str) -> str:
        recent = self.storage.list_recent_history(session_id=session_id, limit=4)
        if not recent:
            return user_text
        lines = ["Recent conversation context (oldest -> newest):"]
        for item in reversed(recent):
            lines.append(f"User: {item['user_text']}")
            lines.append(f"Assistant: {item['assistant_text']}")
        lines.append(f"User: {user_text}")
        return "\n".join(lines)

    async def _reminder_due_worker(self) -> None:
        while self._running:
            now_iso = utc_now_iso()
            due = self.storage.list_due_unnotified(before_iso=now_iso)
            for item in due:
                reminder_id = int(item["id"])
                self.storage.mark_reminder_notified(reminder_id)
                await self.events.publish(
                    {
                        "type": "reminder.due",
                        "timestamp": utc_now_iso(),
                        "reminder": item,
                    }
                )
            await asyncio.sleep(max(3, self.settings.reminder_poll_interval_sec))

    def _add_timeline(
        self,
        run: ActionRun,
        step_id: str,
        status: StepStatus,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        run.timeline.append(
            RunStepEvent(
                step_id=step_id,
                status=status,
                message=message,
                data=data or {},
            )
        )

    def _summarize_run(self, run: ActionRun) -> str:
        success_count = sum(1 for event in run.timeline if event.status == StepStatus.SUCCESS)
        failure_count = sum(
            1 for event in run.timeline if event.status in {StepStatus.FAILED, StepStatus.BLOCKED}
        )
        return (
            f"Run {run.id} finished with status '{run.status.value}'. "
            f"Successful steps: {success_count}, failed/blocked: {failure_count}."
        )
