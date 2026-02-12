from __future__ import annotations

from pathlib import Path
from typing import Any

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
        if path:
            candidate = Path(path)
            if candidate.exists() and candidate.is_file():
                try:
                    context_snippet = candidate.read_text(encoding="utf-8")[:2000]
                except Exception:
                    context_snippet = ""

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
            data={"task": task, "language": language, "output": answer},
        )

