from __future__ import annotations

from pathlib import Path

from friday.code_context import CodeContextIndex
from friday.config import Settings
from friday.llm import LocalLLMClient


class CodeWorkflow:
    def __init__(self, settings: Settings, llm: LocalLLMClient) -> None:
        self.settings = settings
        self.llm = llm
        self.index = CodeContextIndex(settings)

    async def propose_patch(self, task: str, path: str | None = None) -> dict[str, object]:
        task = task.strip()
        if not task:
            return {"ok": False, "message": "task is required", "proposal": "", "citations": []}

        citations: list[str] = []
        context_parts: list[str] = []

        if path:
            candidate = Path(path)
            if candidate.exists() and candidate.is_file():
                content = candidate.read_text(encoding="utf-8", errors="ignore")
                citations.append(str(candidate))
                context_parts.append(f"FILE: {candidate}\n{content[:4000]}")
        else:
            matches = self.index.search(task)
            for match in matches:
                citations.append(match.path)
                context_parts.append(f"FILE: {match.path}\n{match.snippet}")

        context_blob = "\n\n".join(context_parts) if context_parts else "(no local context)"
        prompt = (
            "You are a code patch generator.\n"
            "Return a unified diff only.\n"
            "Task:\n"
            f"{task}\n\n"
            "Repository context:\n"
            f"{context_blob}\n\n"
            "Rules:\n"
            "- Use git unified diff format.\n"
            "- Keep changes minimal and safe.\n"
            "- If uncertain, include TODO comments in patch.\n"
        )
        proposal = await self.llm.generate(prompt, max_tokens=900)
        return {
            "ok": True,
            "proposal": proposal,
            "citations": citations,
        }

