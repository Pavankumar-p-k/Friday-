from __future__ import annotations

from pathlib import Path
from typing import Any

from friday.code_context import CodeContextIndex
from friday.schemas import AssistantMode, ToolExecutionResult
from friday.tools.base import Tool, ToolContext


class CodeAgentTool(Tool):
    name = "code_agent"
    description = "Generate code suggestions and technical explanations."
    input_schema = {
        "type": "object",
        "properties": {
            "task": {"type": "string"},
            "language": {"type": "string"},
            "path": {"type": "string"},
            "write_files": {"type": "boolean"},
            "run_shell": {"type": "boolean"},
        },
        "required": ["task"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        task = str(args.get("task", "")).strip()
        language = str(args.get("language", "text")).strip()
        path = str(args.get("path", "")).strip()

        if not task:
            return ToolExecutionResult(success=False, message="Missing task.")

        context_snippet = ""
        citations: list[str] = []
        if path:
            candidate = self._resolve_candidate(path, context.settings.workspace_root)
            if candidate is not None and candidate.exists() and candidate.is_file():
                try:
                    context_snippet = candidate.read_text(encoding="utf-8")[:2000]
                    try:
                        citations = [str(candidate.resolve().relative_to(context.settings.workspace_root.resolve()))]
                    except Exception:
                        citations = [str(candidate)]
                except Exception:
                    context_snippet = ""
                    citations = []
        else:
            index = CodeContextIndex(context.settings)
            matches = index.search(task)
            if matches:
                citations = [match.path for match in matches]
                joined = []
                for match in matches:
                    joined.append(f"FILE: {match.path}\n{match.snippet}")
                context_snippet = "\n\n".join(joined)

        prompt = (
            f"Task:\n{task}\n\n"
            f"Language: {language}\n\n"
            "Return practical code with short explanation. "
            "Do not assume internet. Keep it runnable locally."
        )
        if context_snippet:
            prompt += f"\n\nFile context:\n{context_snippet}"

        answer = await context.llm.generate(prompt, mode=AssistantMode.CODE, max_tokens=700)
        return ToolExecutionResult(
            success=True,
            message="Code guidance generated.",
            data={
                "task": task,
                "language": language,
                "output": answer,
                "citations": citations,
            },
        )

    def _resolve_candidate(self, path: str, workspace_root: Path) -> Path | None:
        root = workspace_root.resolve()
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate
