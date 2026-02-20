from __future__ import annotations

import asyncio
from typing import Any

from friday.config import Settings
from friday.hybrid_dispatcher import HybridAIDispatcher


class FakeLocalLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def generate(self, prompt: str, mode: Any, max_tokens: int = 512) -> str:
        _ = (prompt, mode, max_tokens)
        self.calls += 1
        if not self._responses:
            return ""
        return self._responses.pop(0)


class FakeCloudReasoner:
    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def generate(self, prompt: str) -> str:
        _ = prompt
        self.calls += 1
        if not self._responses:
            raise RuntimeError("no more cloud responses")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_dispatcher_uses_local_structured_response() -> None:
    local = FakeLocalLLM(
        [
            (
                '{"reply":"Opening notepad.","actions":[{"tool":"open_app",'
                '"args":{"app_name":"notepad"},"confidence":0.9,"reason":"direct command"}]}'
            )
        ]
    )
    cloud = FakeCloudReasoner([])
    dispatcher = HybridAIDispatcher(
        settings=Settings(),
        local_llm=local,
        cloud_reasoner=cloud,
        cloud_enabled=True,
    )

    result = asyncio.run(dispatcher.dispatch("open notepad"))
    assert result.llm_backend == "local"
    assert result.reply == "Opening notepad."
    assert result.actions
    assert result.actions[0].tool == "open_app"
    assert cloud.calls == 0


def test_dispatcher_retries_cloud_for_deep_reasoning() -> None:
    local = FakeLocalLLM([""])  # force cloud fallback path
    cloud = FakeCloudReasoner(
        [
            RuntimeError("temporary cloud failure"),
            '{"reply":"Use modular architecture.","actions":[]}',
        ]
    )
    dispatcher = HybridAIDispatcher(
        settings=Settings(),
        local_llm=local,
        cloud_reasoner=cloud,
        cloud_enabled=True,
        cloud_max_retries=2,
        cloud_retry_delay_sec=0.0,
    )

    result = asyncio.run(dispatcher.dispatch("analyze architecture tradeoff"))
    assert result.llm_backend == "cloud"
    assert result.used_cloud_fallback is True
    assert result.cloud_attempts == 2
    assert any("cloud attempt 1 failed" in item for item in result.warnings)


def test_dispatcher_returns_local_when_cloud_retries_exhausted() -> None:
    local = FakeLocalLLM(["I can open notepad for you."])
    cloud = FakeCloudReasoner([RuntimeError("cloud down"), RuntimeError("still down")])
    dispatcher = HybridAIDispatcher(
        settings=Settings(),
        local_llm=local,
        cloud_reasoner=cloud,
        cloud_enabled=True,
        cloud_max_retries=1,
        cloud_retry_delay_sec=0.0,
    )

    result = asyncio.run(dispatcher.dispatch("analyze and open notepad"))
    assert result.llm_backend == "local"
    assert result.reply == "I can open notepad for you."
    assert result.cloud_attempts == 2
    assert any("cloud fallback unavailable" in item for item in result.warnings)
