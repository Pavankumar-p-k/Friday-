from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AssistantMode(str, Enum):
    CHAT = "chat"
    ACTION = "action"
    CODE = "code"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlanStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial_success"


class StepStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class ChatRequest(BaseModel):
    session_id: str = Field(default="default", min_length=1)
    text: str = Field(min_length=1)
    mode: AssistantMode = AssistantMode.CHAT
    context: dict[str, Any] = Field(default_factory=dict)


class PlanRequest(BaseModel):
    goal: str = Field(min_length=1)
    mode: AssistantMode = AssistantMode.ACTION
    context: dict[str, Any] = Field(default_factory=dict)


class PlanStep(BaseModel):
    id: str
    description: str
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    risk: RiskLevel = RiskLevel.LOW
    needs_approval: bool = False


class Plan(BaseModel):
    id: str
    goal: str
    mode: AssistantMode
    status: PlanStatus = PlanStatus.DRAFT
    created_at: str = Field(default_factory=utc_now_iso)
    steps: list[PlanStep] = Field(default_factory=list)


class ExecuteRequest(BaseModel):
    plan_id: str = Field(min_length=1)
    approved_steps: list[str] = Field(default_factory=list)


class RunStepEvent(BaseModel):
    timestamp: str = Field(default_factory=utc_now_iso)
    step_id: str
    status: StepStatus
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class ActionRun(BaseModel):
    id: str
    plan_id: str
    status: RunStatus
    started_at: str = Field(default_factory=utc_now_iso)
    finished_at: str | None = None
    timeline: list[RunStepEvent] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    citations: list[str] = Field(default_factory=list)
    plan: Plan | None = None
    run_id: str | None = None


class PolicyDecision(BaseModel):
    allowed: bool
    risk: RiskLevel
    needs_approval: bool
    reason: str = ""


class ToolExecutionResult(BaseModel):
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class ModelPullRequest(BaseModel):
    model: str = Field(min_length=1)


class VoiceSpeakRequest(BaseModel):
    text: str = Field(min_length=1)


class VoiceTranscriptionResponse(BaseModel):
    transcript: str
    backend: str
    warning: str | None = None


class VoiceSpeakResponse(BaseModel):
    audio_path: str
    backend: str
    warning: str | None = None


class VoiceCommandResponse(BaseModel):
    transcript: str
    reply: str
    plan: Plan | None = None
    run_id: str | None = None
    audio_path: str = ""
    stt_backend: str = ""
    tts_backend: str = ""
    warnings: list[str] = Field(default_factory=list)


class PatchProposalRequest(BaseModel):
    task: str = Field(min_length=1)
    path: str | None = None


class PatchProposalResponse(BaseModel):
    ok: bool
    proposal: str
    citations: list[str] = Field(default_factory=list)
    message: str | None = None
