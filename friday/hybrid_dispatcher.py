from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
import json
import os
import re
from typing import Any, Protocol

import httpx

from friday.config import Settings
from friday.llm import LocalLLMClient
from friday.schemas import AssistantMode


class SpeechIntent(str, Enum):
    CHAT = "chat"
    AUTOMATION = "automation"
    CODE = "code"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class IntentPrediction:
    intent: SpeechIntent
    mode: AssistantMode
    confidence: float
    requires_deep_reasoning: bool


@dataclass(frozen=True)
class StructuredAction:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "args": dict(self.args),
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DispatchResult:
    transcript: str
    intent: SpeechIntent
    mode: AssistantMode
    reply: str
    actions: list[StructuredAction]
    llm_backend: str
    used_cloud_fallback: bool
    local_attempts: int
    cloud_attempts: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transcript": self.transcript,
            "intent": self.intent.value,
            "mode": self.mode.value,
            "reply": self.reply,
            "actions": [action.to_dict() for action in self.actions],
            "llm_backend": self.llm_backend,
            "used_cloud_fallback": self.used_cloud_fallback,
            "local_attempts": self.local_attempts,
            "cloud_attempts": self.cloud_attempts,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class _ParsedPayload:
    reply: str
    actions: list[StructuredAction]
    is_structured: bool


class CloudReasoner(Protocol):
    async def generate(self, prompt: str) -> str:
        raise NotImplementedError


class OpenAICompatibleCloudReasoner(CloudReasoner):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout_sec: int,
    ) -> None:
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.timeout_sec = timeout_sec

    async def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("FRIDAY_CLOUD_LLM_API_KEY is not configured.")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a reliable dispatcher reasoning model. "
                        "Return strict JSON with 'reply' and 'actions'."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            response = await client.post(self.base_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices", [])
        if isinstance(choices, list) and choices:
            item = choices[0]
            if isinstance(item, dict):
                message = item.get("message", {})
                if isinstance(message, dict):
                    content = message.get("content", "")
                    if isinstance(content, str):
                        return content.strip()
        return ""


class RuleBasedSpeechIntentClassifier:
    def classify(self, transcript: str) -> IntentPrediction:
        text = transcript.strip().lower()
        if not text:
            return IntentPrediction(
                intent=SpeechIntent.UNKNOWN,
                mode=AssistantMode.CHAT,
                confidence=0.0,
                requires_deep_reasoning=False,
            )

        requires_deep_reasoning = any(
            token in text
            for token in (
                "analyze",
                "reason",
                "compare",
                "tradeoff",
                "architecture",
                "deep",
                "why",
            )
        )

        if any(token in text for token in ("code", "python", "typescript", "bug", "refactor")):
            return IntentPrediction(
                intent=SpeechIntent.CODE,
                mode=AssistantMode.CODE,
                confidence=0.86,
                requires_deep_reasoning=True,
            )
        if any(
            token in text
            for token in ("open ", "launch ", "play ", "run ", "execute ", "remind me", "set reminder")
        ):
            return IntentPrediction(
                intent=SpeechIntent.AUTOMATION,
                mode=AssistantMode.ACTION,
                confidence=0.84,
                requires_deep_reasoning=requires_deep_reasoning,
            )
        return IntentPrediction(
            intent=SpeechIntent.CHAT,
            mode=AssistantMode.CHAT,
            confidence=0.77,
            requires_deep_reasoning=requires_deep_reasoning,
        )


class HybridAIDispatcher:
    def __init__(
        self,
        settings: Settings | None = None,
        local_llm: LocalLLMClient | None = None,
        classifier: RuleBasedSpeechIntentClassifier | None = None,
        cloud_reasoner: CloudReasoner | None = None,
        cloud_enabled: bool | None = None,
        cloud_max_retries: int | None = None,
        cloud_retry_delay_sec: float | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.local_llm = local_llm or LocalLLMClient(self.settings)
        self.classifier = classifier or RuleBasedSpeechIntentClassifier()

        enabled_from_env = os.getenv("FRIDAY_CLOUD_LLM_ENABLED", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.cloud_enabled = enabled_from_env if cloud_enabled is None else cloud_enabled

        retries_from_env = _parse_int_env("FRIDAY_CLOUD_LLM_MAX_RETRIES", 2)
        delay_from_env = _parse_float_env("FRIDAY_CLOUD_LLM_RETRY_DELAY_SEC", 0.75)
        self.cloud_max_retries = max(0, retries_from_env if cloud_max_retries is None else cloud_max_retries)
        self.cloud_retry_delay_sec = max(
            0.0,
            delay_from_env if cloud_retry_delay_sec is None else cloud_retry_delay_sec,
        )

        if cloud_reasoner is not None:
            self.cloud_reasoner = cloud_reasoner
        else:
            self.cloud_reasoner = OpenAICompatibleCloudReasoner(
                base_url=os.getenv(
                    "FRIDAY_CLOUD_LLM_BASE_URL",
                    "https://api.openai.com/v1/chat/completions",
                ),
                model=os.getenv("FRIDAY_CLOUD_LLM_MODEL", "gpt-4o-mini"),
                api_key=os.getenv("FRIDAY_CLOUD_LLM_API_KEY", ""),
                timeout_sec=max(5, _parse_int_env("FRIDAY_CLOUD_LLM_TIMEOUT_SEC", 30)),
            )

    async def dispatch(
        self,
        transcript: str,
        *,
        session_id: str = "default",
        context: dict[str, Any] | None = None,
    ) -> DispatchResult:
        cleaned = transcript.strip()
        if not cleaned:
            return DispatchResult(
                transcript="",
                intent=SpeechIntent.UNKNOWN,
                mode=AssistantMode.CHAT,
                reply="No transcript provided.",
                actions=[],
                llm_backend="none",
                used_cloud_fallback=False,
                local_attempts=0,
                cloud_attempts=0,
                warnings=["empty transcript"],
            )

        prediction = self.classifier.classify(cleaned)
        prompt = self._build_dispatch_prompt(
            transcript=cleaned,
            intent=prediction,
            session_id=session_id,
            context=context or {},
        )

        warnings: list[str] = []
        local_attempts = 0
        cloud_attempts = 0

        local_attempts += 1
        local_raw = await self.local_llm.generate(prompt=prompt, mode=prediction.mode)
        local_parsed = self._parse_payload(local_raw, cleaned, prediction)

        should_try_cloud = self.cloud_enabled and (
            prediction.requires_deep_reasoning or not local_parsed.is_structured
        )
        cloud_parsed: _ParsedPayload | None = None

        if should_try_cloud:
            cloud_raw, cloud_attempts, cloud_warnings = await self._generate_with_cloud_retry(prompt)
            warnings.extend(cloud_warnings)
            if cloud_raw:
                cloud_parsed = self._parse_payload(cloud_raw, cleaned, prediction)
                if cloud_parsed.reply:
                    return DispatchResult(
                        transcript=cleaned,
                        intent=prediction.intent,
                        mode=prediction.mode,
                        reply=cloud_parsed.reply,
                        actions=cloud_parsed.actions,
                        llm_backend="cloud",
                        used_cloud_fallback=True,
                        local_attempts=local_attempts,
                        cloud_attempts=cloud_attempts,
                        warnings=warnings,
                    )

        if local_parsed.reply:
            if should_try_cloud and cloud_parsed is None:
                warnings.append("cloud fallback unavailable; returned local response")
            return DispatchResult(
                transcript=cleaned,
                intent=prediction.intent,
                mode=prediction.mode,
                reply=local_parsed.reply,
                actions=local_parsed.actions,
                llm_backend="local",
                used_cloud_fallback=False,
                local_attempts=local_attempts,
                cloud_attempts=cloud_attempts,
                warnings=warnings,
            )

        fallback_actions = self._infer_actions_from_transcript(cleaned, prediction)
        fallback_reply = (
            "I understood your request but could not get a model response. "
            "I prepared structured actions for execution."
        )
        warnings.append("used deterministic fallback response")
        return DispatchResult(
            transcript=cleaned,
            intent=prediction.intent,
            mode=prediction.mode,
            reply=fallback_reply,
            actions=fallback_actions,
            llm_backend="deterministic-fallback",
            used_cloud_fallback=should_try_cloud,
            local_attempts=local_attempts,
            cloud_attempts=cloud_attempts,
            warnings=warnings,
        )

    async def _generate_with_cloud_retry(self, prompt: str) -> tuple[str, int, list[str]]:
        attempts = 0
        warnings: list[str] = []
        max_attempts = self.cloud_max_retries + 1
        for index in range(max_attempts):
            attempts += 1
            try:
                text = await self.cloud_reasoner.generate(prompt)
                if text.strip():
                    return text, attempts, warnings
                warnings.append(f"cloud attempt {attempts} returned empty response")
            except Exception as exc:
                warnings.append(f"cloud attempt {attempts} failed: {exc}")

            if index < max_attempts - 1 and self.cloud_retry_delay_sec > 0:
                await asyncio.sleep(self.cloud_retry_delay_sec * (index + 1))
        return "", attempts, warnings

    def _build_dispatch_prompt(
        self,
        *,
        transcript: str,
        intent: IntentPrediction,
        session_id: str,
        context: dict[str, Any],
    ) -> str:
        return (
            "You are the hybrid dispatcher.\n"
            "Classified intent:\n"
            f"- intent: {intent.intent.value}\n"
            f"- mode: {intent.mode.value}\n"
            f"- requires_deep_reasoning: {intent.requires_deep_reasoning}\n"
            f"- session_id: {session_id}\n"
            f"- context: {json.dumps(context, ensure_ascii=True)}\n\n"
            "Return strict JSON with schema:\n"
            '{"reply":"string","actions":[{"tool":"string","args":{},"confidence":0.0,"reason":"string"}]}\n\n'
            f"Transcript: {transcript}"
        )

    def _parse_payload(
        self,
        payload_text: str,
        transcript: str,
        prediction: IntentPrediction,
    ) -> _ParsedPayload:
        cleaned = payload_text.strip()
        if not cleaned:
            return _ParsedPayload(reply="", actions=[], is_structured=False)

        parsed_json = self._try_parse_json(cleaned)
        if parsed_json is None:
            actions = self._infer_actions_from_transcript(transcript, prediction)
            return _ParsedPayload(reply=cleaned, actions=actions, is_structured=False)

        reply = str(parsed_json.get("reply", "")).strip()
        if not reply:
            reply = str(parsed_json.get("response", "")).strip()
        actions = self._parse_actions(parsed_json.get("actions"), transcript, prediction)
        return _ParsedPayload(reply=reply or cleaned, actions=actions, is_structured=True)

    def _try_parse_json(self, text: str) -> dict[str, Any] | None:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            try:
                data = json.loads(fenced.group(1))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass

        inline = re.search(r"(\{.*\})", text, flags=re.DOTALL)
        if inline:
            candidate = inline.group(1)
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                return None
        return None

    def _parse_actions(
        self,
        actions_obj: Any,
        transcript: str,
        prediction: IntentPrediction,
    ) -> list[StructuredAction]:
        if not isinstance(actions_obj, list):
            return self._infer_actions_from_transcript(transcript, prediction)

        parsed: list[StructuredAction] = []
        for item in actions_obj:
            if not isinstance(item, dict):
                continue
            tool = str(item.get("tool", "")).strip()
            if not tool:
                continue
            args = item.get("args", {})
            parsed.append(
                StructuredAction(
                    tool=tool,
                    args=args if isinstance(args, dict) else {},
                    confidence=float(item.get("confidence", 0.0) or 0.0),
                    reason=str(item.get("reason", "")).strip(),
                )
            )
        if parsed:
            return parsed
        return self._infer_actions_from_transcript(transcript, prediction)

    def _infer_actions_from_transcript(
        self,
        transcript: str,
        prediction: IntentPrediction,
    ) -> list[StructuredAction]:
        text = transcript.strip().lower()
        if prediction.intent != SpeechIntent.AUTOMATION:
            return []

        if text.startswith("open ") or text.startswith("launch "):
            app = transcript.split(" ", 1)[1].strip() if " " in transcript else ""
            return [
                StructuredAction(
                    tool="open_app",
                    args={"app_name": app},
                    confidence=0.62,
                    reason="inferred from open/launch command",
                )
            ]
        if text.startswith("play "):
            query = transcript.split(" ", 1)[1].strip() if " " in transcript else ""
            return [
                StructuredAction(
                    tool="media_control",
                    args={"action": "play", "query": query},
                    confidence=0.61,
                    reason="inferred from play command",
                )
            ]
        if "remind me" in text or "set reminder" in text:
            return [
                StructuredAction(
                    tool="reminder",
                    args={"text": transcript},
                    confidence=0.65,
                    reason="inferred from reminder phrase",
                )
            ]
        if text.startswith("run ") or text.startswith("execute "):
            command = transcript.split(" ", 1)[1].strip() if " " in transcript else ""
            return [
                StructuredAction(
                    tool="safe_shell",
                    args={"command": command},
                    confidence=0.55,
                    reason="inferred from run/execute command",
                )
            ]
        return []


def _parse_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _parse_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value.strip())
    except ValueError:
        return default
