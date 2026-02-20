from __future__ import annotations

import time
from typing import Any

import httpx

from friday.assistant_engine.config import EngineConfig
from friday.assistant_engine.interfaces import LLMBridge
from friday.assistant_engine.models import AssistantMode, LLMRequest, LLMResponse
from friday.config import Settings
from friday.llm import LocalLLMClient
from friday.schemas import AssistantMode as ApiAssistantMode


def _map_mode(mode: AssistantMode) -> ApiAssistantMode:
    if mode == AssistantMode.ACTION:
        return ApiAssistantMode.ACTION
    if mode == AssistantMode.CODE:
        return ApiAssistantMode.CODE
    return ApiAssistantMode.CHAT


class LocalLLMBridge(LLMBridge):
    def __init__(self, settings: Settings | None = None) -> None:
        self._client = LocalLLMClient(settings or Settings.from_env())

    async def generate(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        text = await self._client.generate(
            prompt=request.prompt,
            mode=_map_mode(request.intent.mode),
        )
        elapsed = int((time.perf_counter() - started) * 1000)
        return LLMResponse(text=text, backend="local", latency_ms=elapsed)


class CloudLLMBridge(LLMBridge):
    def __init__(self, config: EngineConfig) -> None:
        self._config = config

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if not self._config.cloud_llm_api_key:
            raise RuntimeError("cloud llm api key is empty")

        payload = {
            "model": self._config.cloud_llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a hybrid voice assistant. Respond concisely and safely for automation."
                    ),
                },
                {"role": "user", "content": request.prompt},
            ],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {self._config.cloud_llm_api_key}"}

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self._config.cloud_timeout_sec) as client:
            response = await client.post(
                self._config.cloud_llm_base_url,
                json=payload,
                headers=headers,
            )
        response.raise_for_status()
        data = response.json()
        text = _extract_cloud_text(data)
        elapsed = int((time.perf_counter() - started) * 1000)
        return LLMResponse(text=text, backend="cloud", latency_ms=elapsed)


def _extract_cloud_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message", {})
            if isinstance(message, dict):
                content = message.get("content", "")
                if isinstance(content, str):
                    return content.strip()
    return ""


class HybridLLMBridge(LLMBridge):
    def __init__(
        self,
        local_bridge: LLMBridge,
        cloud_bridge: LLMBridge | None = None,
    ) -> None:
        self._local = local_bridge
        self._cloud = cloud_bridge

    async def generate(self, request: LLMRequest) -> LLMResponse:
        local_response = await self._local.generate(request)
        if local_response.text.strip():
            return local_response

        if self._cloud is None:
            return local_response

        cloud_response = await self._cloud.generate(request)
        if cloud_response.text.strip():
            return cloud_response
        return local_response
