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
    interrupted: bool = False
    warnings: list[str] = Field(default_factory=list)


class VoiceDispatchRequest(BaseModel):
    session_id: str = Field(default="default", min_length=1)
    transcript: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


class VoiceDispatchAction(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""


class VoiceDispatchResponse(BaseModel):
    transcript: str
    intent: str
    mode: AssistantMode
    reply: str
    actions: list[VoiceDispatchAction] = Field(default_factory=list)
    llm_backend: str
    used_cloud_fallback: bool = False
    local_attempts: int = 0
    cloud_attempts: int = 0
    warnings: list[str] = Field(default_factory=list)


class VoiceLoopStartRequest(BaseModel):
    session_id: str = Field(default="voice-loop", min_length=1)
    mode: AssistantMode = AssistantMode.ACTION
    require_wake_word: bool = True
    poll_interval_sec: int = Field(default=2, ge=1)


class VoiceLoopStateResponse(BaseModel):
    running: bool
    session_id: str
    mode: AssistantMode
    require_wake_word: bool
    poll_interval_sec: int
    wake_words: list[str] = Field(default_factory=list)
    processed_count: int = 0
    skipped_count: int = 0
    last_transcript: str = ""
    last_command: str = ""
    last_reply: str = ""
    last_backend: str = ""
    last_error: str = ""
    started_at: str | None = None
    updated_at: str | None = None


class PatchProposalRequest(BaseModel):
    task: str = Field(min_length=1)
    path: str | None = None


class PatchProposalResponse(BaseModel):
    ok: bool
    proposal: str
    citations: list[str] = Field(default_factory=list)
    message: str | None = None


class PatchApplyRequest(BaseModel):
    patch: str = Field(min_length=1)
    dry_run: bool = True


class PatchApplyResponse(BaseModel):
    ok: bool
    applied: bool
    dry_run: bool
    message: str


class JarvisRunCommandRequest(BaseModel):
    command: str = Field(min_length=1)
    bypass_confirmation: bool = False


class JarvisModeRequest(BaseModel):
    mode: str = Field(min_length=1)


class JarvisIdRequest(BaseModel):
    id: str = Field(min_length=1)


class JarvisAutomationToggleRequest(BaseModel):
    id: str = Field(min_length=1)
    enabled: bool


class JarvisPluginToggleRequest(BaseModel):
    plugin_id: str = Field(min_length=1)
    enabled: bool


class JarvisTerminateProcessRequest(BaseModel):
    pid: int
    bypass_confirmation: bool = False


class DashboardLoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class DashboardTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class DashboardStatsResponse(BaseModel):
    chat_history_count: int = 0
    voice_history_count: int = 0
    action_history_count: int = 0
    action_success_count: int = 0
    action_failure_count: int = 0
    log_count: int = 0
    started_at: str = ""
    uptime_sec: int = 0


class DashboardLogEntry(BaseModel):
    id: int
    level: str
    message: str
    source: str
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class DashboardVoiceHistoryEntry(BaseModel):
    id: int
    session_id: str
    transcript: str
    reply: str
    mode: str
    llm_backend: str
    stt_backend: str
    tts_backend: str
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class DashboardSettingsUpdateRequest(BaseModel):
    updates: dict[str, str] = Field(default_factory=dict)


class DashboardSettingsResponse(BaseModel):
    settings: dict[str, str] = Field(default_factory=dict)


class DashboardActionExecuteRequest(BaseModel):
    session_id: str = Field(default="dashboard", min_length=1)
    tool: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)


class DashboardActionExecuteResponse(BaseModel):
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    tool: str


class DashboardActionHistoryEntry(BaseModel):
    id: int
    session_id: str
    actor: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: str
