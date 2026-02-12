from __future__ import annotations

from typing import Any

import httpx

from friday.config import Settings


class ModelManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def list_models(self) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_sec) as client:
                response = await client.get(f"{self.settings.ollama_base_url}/api/tags")
            response.raise_for_status()
            payload = response.json()
            models = payload.get("models", [])
            result: list[dict[str, Any]] = []
            for model in models:
                result.append(
                    {
                        "name": str(model.get("name", "")),
                        "size": int(model.get("size", 0)),
                        "modified_at": str(model.get("modified_at", "")),
                        "digest": str(model.get("digest", "")),
                    }
                )
            return result
        except Exception:
            return []

    async def pull_model(self, model_name: str) -> dict[str, Any]:
        model_name = model_name.strip()
        if not model_name:
            return {"ok": False, "message": "model name is required"}

        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_sec * 6) as client:
                response = await client.post(
                    f"{self.settings.ollama_base_url}/api/pull",
                    json={"name": model_name, "stream": False},
                )
            response.raise_for_status()
            payload = response.json()
            return {
                "ok": True,
                "message": str(payload.get("status", "pull completed")),
                "model": model_name,
            }
        except Exception as exc:
            return {
                "ok": False,
                "message": f"pull failed: {exc}",
                "model": model_name,
            }

    async def show_model(self, model_name: str) -> dict[str, Any]:
        model_name = model_name.strip()
        if not model_name:
            return {"ok": False, "message": "model name is required"}

        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_sec) as client:
                response = await client.post(
                    f"{self.settings.ollama_base_url}/api/show",
                    json={"name": model_name},
                )
            response.raise_for_status()
            payload = response.json()
            return {"ok": True, "model": model_name, "info": payload}
        except Exception as exc:
            return {"ok": False, "model": model_name, "message": f"show failed: {exc}"}

