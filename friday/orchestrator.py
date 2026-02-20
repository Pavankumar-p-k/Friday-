from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
import uuid
from typing import Any

from friday.config import Settings
from friday.code_workflow import CodeWorkflow
from friday.events import InMemoryEventBus
from friday.hybrid_dispatcher import HybridAIDispatcher
from friday.jarvis_compat import JarvisCompatService
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
    PlanStep,
    PlanStatus,
    RunStatus,
    RunStepEvent,
    StepStatus,
    ToolExecutionResult,
    VoiceCommandResponse,
    VoiceDispatchAction,
    VoiceDispatchResponse,
    VoiceLoopStateResponse,
    utc_now_iso,
)
from friday.storage import Storage
from friday.tools.registry import ToolRegistry, build_default_registry
from friday.voice import VoicePipeline


@dataclass
class VoiceSessionState:
    session_id: str
    mode: AssistantMode
    interrupted: bool = False
    last_partial: str = ""
    updated_at: str = ""

    def touch(self) -> None:
        self.updated_at = utc_now_iso()


@dataclass
class VoiceLoopState:
    running: bool
    session_id: str
    mode: AssistantMode
    require_wake_word: bool
    poll_interval_sec: int
    wake_words: tuple[str, ...]
    processed_count: int = 0
    skipped_count: int = 0
    last_transcript: str = ""
    last_command: str = ""
    last_reply: str = ""
    last_backend: str = ""
    last_error: str = ""
    started_at: str | None = None
    updated_at: str = ""

    def touch(self) -> None:
        self.updated_at = utc_now_iso()


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
        self.dispatcher = HybridAIDispatcher(settings=self.settings, local_llm=self.llm)
        self.jarvis = JarvisCompatService(
            settings=self.settings,
            storage=self.storage,
            llm=self.llm,
            orchestrator=self,
        )

        self._plans: dict[str, Plan] = {}
        self._runs: dict[str, ActionRun] = {}
        self._voice_sessions: dict[str, VoiceSessionState] = {}
        self._voice_loop_seen_files: set[str] = set()
        self._voice_loop_state = VoiceLoopState(
            running=False,
            session_id=self.settings.voice_loop_session_id,
            mode=self._assistant_mode_from_text(self.settings.voice_loop_mode),
            require_wake_word=self.settings.voice_loop_require_wake_word,
            poll_interval_sec=max(1, self.settings.voice_loop_poll_interval_sec),
            wake_words=tuple(self.settings.voice_wake_words),
            updated_at=utc_now_iso(),
        )
        self._lock = asyncio.Lock()

        self._running = False
        self._reminder_task: asyncio.Task[None] | None = None
        self._voice_loop_task: asyncio.Task[None] | None = None

    async def start_background_workers(self) -> None:
        if self._running:
            return
        self._running = True
        self._reminder_task = asyncio.create_task(self._reminder_due_worker())
        if self.settings.voice_loop_auto_start:
            await self.start_voice_loop()

    async def stop_background_workers(self) -> None:
        await self.stop_voice_loop()
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

    async def apply_patch(self, patch: str, dry_run: bool = True) -> dict[str, object]:
        return await self.code_workflow.apply_patch(patch=patch, dry_run=dry_run)

    async def jarvis_get_state(self) -> dict[str, Any]:
        return await self.jarvis.get_state()

    async def jarvis_run_command(
        self,
        command: str,
        bypass_confirmation: bool = False,
    ) -> dict[str, Any]:
        return await self.jarvis.run_command(command, bypass_confirmation=bypass_confirmation)

    async def jarvis_set_mode(self, mode: str) -> dict[str, Any]:
        return await self.jarvis.set_mode(mode)

    async def jarvis_complete_reminder(self, reminder_id: str) -> dict[str, Any]:
        return await self.jarvis.complete_reminder(reminder_id)

    async def jarvis_replay_command(self, command_id: str) -> dict[str, Any]:
        return await self.jarvis.replay_command(command_id)

    async def jarvis_generate_briefing(self) -> dict[str, Any]:
        return await self.jarvis.generate_briefing()

    async def jarvis_reload_plugins(self) -> dict[str, Any]:
        return await self.jarvis.reload_plugins()

    async def jarvis_set_automation_enabled(
        self,
        automation_id: str,
        enabled: bool,
    ) -> dict[str, Any]:
        return await self.jarvis.set_automation_enabled(automation_id=automation_id, enabled=enabled)

    async def jarvis_set_plugin_enabled(self, plugin_id: str, enabled: bool) -> dict[str, Any]:
        return await self.jarvis.set_plugin_enabled(plugin_id=plugin_id, enabled=enabled)

    async def jarvis_terminate_process(
        self,
        pid: int,
        bypass_confirmation: bool = False,
    ) -> dict[str, Any]:
        return await self.jarvis.terminate_process(pid=pid, bypass_confirmation=bypass_confirmation)

    async def transcribe_audio(self, audio_path: Path) -> dict[str, str]:
        return await self.voice.transcribe(audio_path)

    async def synthesize_text(self, text: str) -> dict[str, str]:
        return await self.voice.synthesize(text)

    async def dispatch_transcribed_speech(
        self,
        transcript: str,
        session_id: str = "default",
        context: dict[str, Any] | None = None,
    ) -> VoiceDispatchResponse:
        result = await self.dispatcher.dispatch(
            transcript=transcript,
            session_id=session_id,
            context=context or {},
        )
        response = VoiceDispatchResponse(
            transcript=result.transcript,
            intent=result.intent.value,
            mode=result.mode,
            reply=result.reply,
            actions=[
                VoiceDispatchAction(
                    tool=item.tool,
                    args=item.args,
                    confidence=item.confidence,
                    reason=item.reason,
                )
                for item in result.actions
            ],
            llm_backend=result.llm_backend,
            used_cloud_fallback=result.used_cloud_fallback,
            local_attempts=result.local_attempts,
            cloud_attempts=result.cloud_attempts,
            warnings=result.warnings,
        )
        self.storage.save_voice_history(
            session_id=session_id,
            transcript=response.transcript,
            reply=response.reply,
            mode=response.mode.value,
            llm_backend=response.llm_backend,
            stt_backend="transcribed-input",
            tts_backend="none",
            meta={
                "intent": response.intent,
                "used_cloud_fallback": response.used_cloud_fallback,
                "local_attempts": response.local_attempts,
                "cloud_attempts": response.cloud_attempts,
            },
        )
        return response

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

        response = await self.process_voice_text(
            transcript=transcript,
            session_id=session_id,
            mode=mode,
        )
        response.stt_backend = stt.get("backend", "none")
        response.warnings = [*warnings, *response.warnings]
        return response

    async def process_voice_text(
        self,
        transcript: str,
        session_id: str = "default",
        mode: AssistantMode = AssistantMode.ACTION,
    ) -> VoiceCommandResponse:
        text = transcript.strip()
        if not text:
            return VoiceCommandResponse(
                transcript="",
                reply="No transcript text provided.",
                warnings=["empty transcript"],
            )

        state = await self.register_voice_session(session_id=session_id, mode=mode)
        state.interrupted = False
        state.last_partial = ""
        state.touch()

        response = await self.chat(
            ChatRequest(
                session_id=session_id,
                text=text,
                mode=mode,
                context={},
            )
        )

        if await self.is_voice_interrupted(session_id):
            await self.clear_voice_interrupt(session_id)
            return VoiceCommandResponse(
                transcript=text,
                reply=response.reply,
                plan=response.plan,
                run_id=response.run_id,
                audio_path="",
                tts_backend="none",
                interrupted=True,
                warnings=["interrupted before speech output"],
            )

        tts = await self.synthesize_text(response.reply)
        warnings: list[str] = []
        if tts.get("warning"):
            warnings.append(str(tts["warning"]))

        output = VoiceCommandResponse(
            transcript=text,
            reply=response.reply,
            plan=response.plan,
            run_id=response.run_id,
            audio_path=tts.get("audio_path", ""),
            tts_backend=tts.get("backend", "none"),
            warnings=warnings,
        )
        self.storage.save_voice_history(
            session_id=session_id,
            transcript=text,
            reply=output.reply,
            mode=mode.value,
            llm_backend="orchestrator",
            stt_backend="text",
            tts_backend=output.tts_backend,
            meta={"run_id": output.run_id or "", "plan_id": output.plan.id if output.plan else ""},
        )
        return output

    async def execute_tool_action(
        self,
        *,
        session_id: str,
        actor: str,
        tool: str,
        args: dict[str, Any],
    ) -> ToolExecutionResult:
        planned = PlanStep(
            id=f"adhoc_{uuid.uuid4().hex[:10]}",
            description=f"Direct tool action via dashboard: {tool}",
            tool=tool,
            args=args,
        )
        decision = self.policy.evaluate(planned)
        if not decision.allowed:
            result = ToolExecutionResult(
                success=False,
                message=decision.reason or "Blocked by policy.",
                data={"risk": decision.risk.value, "needs_approval": decision.needs_approval},
            )
            self.storage.save_action_history(
                session_id=session_id,
                actor=actor,
                tool=tool,
                args=args,
                success=result.success,
                message=result.message,
                data=result.data,
            )
            return result

        result = await self.registry.execute(tool, args)
        self.storage.save_action_history(
            session_id=session_id,
            actor=actor,
            tool=tool,
            args=args,
            success=result.success,
            message=result.message,
            data=result.data,
        )
        await self.events.publish(
            {
                "type": "dashboard.action.executed",
                "timestamp": utc_now_iso(),
                "session_id": session_id,
                "actor": actor,
                "tool": tool,
                "success": result.success,
                "message": result.message,
            }
        )
        return result

    async def register_voice_session(
        self,
        session_id: str,
        mode: AssistantMode = AssistantMode.ACTION,
    ) -> VoiceSessionState:
        async with self._lock:
            existing = self._voice_sessions.get(session_id)
            if existing is not None:
                existing.mode = mode
                existing.touch()
                return existing
            state = VoiceSessionState(session_id=session_id, mode=mode, updated_at=utc_now_iso())
            self._voice_sessions[session_id] = state
            return state

    async def close_voice_session(self, session_id: str) -> None:
        async with self._lock:
            self._voice_sessions.pop(session_id, None)

    async def set_voice_partial(self, session_id: str, text: str) -> VoiceSessionState:
        state = await self.register_voice_session(session_id=session_id)
        state.last_partial = text
        state.touch()
        return state

    async def interrupt_voice_session(self, session_id: str) -> VoiceSessionState:
        state = await self.register_voice_session(session_id=session_id)
        state.interrupted = True
        state.touch()
        await self.events.publish(
            {
                "type": "voice.interrupted",
                "timestamp": utc_now_iso(),
                "session_id": session_id,
            }
        )
        return state

    async def clear_voice_interrupt(self, session_id: str) -> None:
        async with self._lock:
            state = self._voice_sessions.get(session_id)
            if state is None:
                return
            state.interrupted = False
            state.touch()

    async def is_voice_interrupted(self, session_id: str) -> bool:
        async with self._lock:
            state = self._voice_sessions.get(session_id)
            if state is None:
                return False
            return state.interrupted

    async def start_voice_loop(
        self,
        session_id: str | None = None,
        mode: AssistantMode | None = None,
        require_wake_word: bool | None = None,
        poll_interval_sec: int | None = None,
    ) -> VoiceLoopStateResponse:
        started = False
        async with self._lock:
            state = self._voice_loop_state
            if session_id:
                state.session_id = session_id
            if mode is not None:
                state.mode = mode
            if require_wake_word is not None:
                state.require_wake_word = require_wake_word
            if poll_interval_sec is not None:
                state.poll_interval_sec = max(1, int(poll_interval_sec))

            if not state.running:
                started = True
                state.running = True
                state.processed_count = 0
                state.skipped_count = 0
                state.last_transcript = ""
                state.last_command = ""
                state.last_reply = ""
                state.last_backend = ""
                state.last_error = ""
                state.started_at = utc_now_iso()
                state.touch()
                self._voice_loop_seen_files = self._list_current_inbox_files()
                self._voice_loop_task = asyncio.create_task(self._voice_loop_worker())
            snapshot = self._voice_loop_snapshot_locked()

        if started:
            await self.events.publish(
                {
                    "type": "voice.loop.started",
                    "timestamp": utc_now_iso(),
                    "session_id": snapshot.session_id,
                    "mode": snapshot.mode.value,
                    "require_wake_word": snapshot.require_wake_word,
                    "poll_interval_sec": snapshot.poll_interval_sec,
                }
            )
        return snapshot

    async def stop_voice_loop(self) -> VoiceLoopStateResponse:
        stopped = False
        task: asyncio.Task[None] | None = None
        async with self._lock:
            state = self._voice_loop_state
            if state.running:
                stopped = True
                state.running = False
                state.touch()
                task = self._voice_loop_task
                self._voice_loop_task = None
            snapshot = self._voice_loop_snapshot_locked()

        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        if stopped:
            await self.events.publish(
                {
                    "type": "voice.loop.stopped",
                    "timestamp": utc_now_iso(),
                    "session_id": snapshot.session_id,
                }
            )
        return snapshot

    async def get_voice_loop_state(self) -> VoiceLoopStateResponse:
        async with self._lock:
            return self._voice_loop_snapshot_locked()

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

    async def _voice_loop_worker(self) -> None:
        while True:
            async with self._lock:
                state = self._voice_loop_state
                if not state.running:
                    return
                session_id = state.session_id
                mode = state.mode
                require_wake_word = state.require_wake_word
                poll_interval_sec = max(1, state.poll_interval_sec)

            try:
                capture = await asyncio.to_thread(self.voice.capture_once)
                transcript = str(capture.get("transcript", "")).strip()
                backend = str(capture.get("backend", "none"))
                warning = str(capture.get("warning", "")).strip()
                audio_path = str(capture.get("path", "")).strip()

                if audio_path:
                    stt = await self.transcribe_audio(Path(audio_path))
                    transcript = stt.get("text", "").strip()
                    backend = stt.get("backend", backend)
                    stt_warning = str(stt.get("warning", "")).strip()
                    if stt_warning:
                        warning = stt_warning if not warning else f"{warning}; {stt_warning}"

                if not transcript:
                    inbox_file = self.voice.next_inbox_file(self._voice_loop_seen_files)
                    if inbox_file is not None:
                        stt = await self.transcribe_audio(inbox_file)
                        transcript = stt.get("text", "").strip()
                        backend = stt.get("backend", backend)
                        stt_warning = str(stt.get("warning", "")).strip()
                        if stt_warning:
                            warning = stt_warning if not warning else f"{warning}; {stt_warning}"

                if warning:
                    await self._record_voice_loop_error(warning)

                if not transcript:
                    await asyncio.sleep(poll_interval_sec)
                    continue

                command_text = transcript
                if require_wake_word:
                    detected, command_text = self.voice.parse_wake_command(transcript)
                    if not detected:
                        await self._record_voice_loop_skip(
                            transcript=transcript,
                            backend=backend,
                            reason="wake word not detected",
                        )
                        await self.events.publish(
                            {
                                "type": "voice.loop.ignored",
                                "timestamp": utc_now_iso(),
                                "session_id": session_id,
                                "transcript": transcript,
                                "reason": "wake_word_not_detected",
                            }
                        )
                        await asyncio.sleep(poll_interval_sec)
                        continue
                    if not command_text:
                        await self._record_voice_loop_skip(
                            transcript=transcript,
                            backend=backend,
                            reason="wake word detected without command",
                        )
                        await self.events.publish(
                            {
                                "type": "voice.loop.ignored",
                                "timestamp": utc_now_iso(),
                                "session_id": session_id,
                                "transcript": transcript,
                                "reason": "wake_word_without_command",
                            }
                        )
                        await asyncio.sleep(poll_interval_sec)
                        continue

                response = await self.process_voice_text(
                    transcript=command_text,
                    session_id=session_id,
                    mode=mode,
                )
                await self._record_voice_loop_processed(
                    transcript=transcript,
                    command=command_text,
                    reply=response.reply,
                    backend=backend,
                )
                await self.events.publish(
                    {
                        "type": "voice.loop.processed",
                        "timestamp": utc_now_iso(),
                        "session_id": session_id,
                        "mode": mode.value,
                        "transcript": transcript,
                        "command": command_text,
                        "reply": response.reply,
                        "audio_path": response.audio_path,
                        "interrupted": response.interrupted,
                    }
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._record_voice_loop_error(str(exc))
                await self.events.publish(
                    {
                        "type": "voice.loop.error",
                        "timestamp": utc_now_iso(),
                        "session_id": session_id,
                        "message": str(exc),
                    }
                )

            await asyncio.sleep(poll_interval_sec)

    def _list_current_inbox_files(self) -> set[str]:
        files: set[str] = set()
        try:
            for path in self.voice.input_dir.iterdir():
                if path.is_file():
                    files.add(str(path.resolve()))
        except FileNotFoundError:
            return set()
        return files

    def _voice_loop_snapshot_locked(self) -> VoiceLoopStateResponse:
        state = self._voice_loop_state
        return VoiceLoopStateResponse(
            running=state.running,
            session_id=state.session_id,
            mode=state.mode,
            require_wake_word=state.require_wake_word,
            poll_interval_sec=state.poll_interval_sec,
            wake_words=list(state.wake_words),
            processed_count=state.processed_count,
            skipped_count=state.skipped_count,
            last_transcript=state.last_transcript,
            last_command=state.last_command,
            last_reply=state.last_reply,
            last_backend=state.last_backend,
            last_error=state.last_error,
            started_at=state.started_at,
            updated_at=state.updated_at,
        )

    async def _record_voice_loop_processed(
        self,
        transcript: str,
        command: str,
        reply: str,
        backend: str,
    ) -> None:
        async with self._lock:
            state = self._voice_loop_state
            state.processed_count += 1
            state.last_transcript = transcript
            state.last_command = command
            state.last_reply = reply
            state.last_backend = backend
            state.last_error = ""
            state.touch()

    async def _record_voice_loop_skip(self, transcript: str, backend: str, reason: str) -> None:
        async with self._lock:
            state = self._voice_loop_state
            state.skipped_count += 1
            state.last_transcript = transcript
            state.last_backend = backend
            state.last_error = reason
            state.touch()

    async def _record_voice_loop_error(self, error: str) -> None:
        if not error:
            return
        async with self._lock:
            state = self._voice_loop_state
            state.last_error = error
            state.touch()

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

    def _assistant_mode_from_text(self, mode: str) -> AssistantMode:
        value = mode.strip().lower()
        if value == AssistantMode.CHAT.value:
            return AssistantMode.CHAT
        if value == AssistantMode.CODE.value:
            return AssistantMode.CODE
        return AssistantMode.ACTION
