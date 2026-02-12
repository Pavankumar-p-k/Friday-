from __future__ import annotations

import asyncio
import uuid
from typing import Any

from friday.config import Settings
from friday.events import InMemoryEventBus
from friday.llm import LocalLLMClient
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
    utc_now_iso,
)
from friday.storage import Storage
from friday.tools.registry import ToolRegistry, build_default_registry


class Orchestrator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.storage = Storage(self.settings.db_path)
        self.events = InMemoryEventBus()
        self.llm = LocalLLMClient(self.settings)
        self.policy = PolicyEngine(self.settings)
        self.planner = Planner(self.settings, self.policy)
        self.registry: ToolRegistry = build_default_registry(self.settings, self.storage, self.llm)

        self._plans: dict[str, Plan] = {}
        self._runs: dict[str, ActionRun] = {}
        self._lock = asyncio.Lock()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if request.mode == AssistantMode.CHAT:
            reply = await self.llm.generate(request.text, mode=AssistantMode.CHAT)
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

    def list_tools(self) -> list[dict[str, Any]]:
        return self.registry.list_tools()

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

