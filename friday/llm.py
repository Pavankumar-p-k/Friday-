from __future__ import annotations

import httpx

from friday.config import Settings
from friday.schemas import AssistantMode


class LocalLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(
        self,
        prompt: str,
        mode: AssistantMode = AssistantMode.CHAT,
        max_tokens: int = 512,
    ) -> str:
        system_prompt = self._system_prompt(mode)
        payload = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_sec) as client:
                response = await client.post(
                    f"{self.settings.ollama_base_url}/api/generate",
                    json=payload,
                )
            response.raise_for_status()
            data = response.json()
            text = str(data.get("response", "")).strip()
            if text:
                return text
        except Exception:
            pass
        return self._fallback(prompt, mode)

    def _system_prompt(self, mode: AssistantMode) -> str:
        if mode == AssistantMode.CODE:
            return (
                "You are FRIDAY Code Agent. Write precise, runnable code and explain assumptions "
                "briefly. Prefer safe local-first instructions."
            )
        if mode == AssistantMode.ACTION:
            return (
                "You are FRIDAY Action Assistant. Be concise, deterministic, and safety-aware. "
                "When actions are involved, summarize the plan and required approvals."
            )
        return (
            "You are FRIDAY offline assistant. Respond clearly and accurately. "
            "Prefer practical and direct answers."
        )

    def _fallback(self, prompt: str, mode: AssistantMode) -> str:
        text = prompt.strip()
        if mode == AssistantMode.CODE:
            return (
                "Local model is unavailable. I can still help with structure and pseudocode. "
                f"Start from this task: {text}"
            )
        if mode == AssistantMode.ACTION:
            return (
                "I prepared an action plan using local rules. "
                "Approve required steps to execute."
            )
        return f"Offline fallback response: {text}"

