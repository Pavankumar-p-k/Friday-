import asyncio
from pathlib import Path

from friday.config import Settings
from friday.llm import LocalLLMClient
from friday.storage import Storage
from friday.tools.base import ToolContext
from friday.tools.code_agent import CodeAgentTool


def _context(tmp_path: Path, workspace_root: Path) -> ToolContext:
    settings = Settings(
        db_path=tmp_path / "code_agent_tool.db",
        workspace_root=workspace_root,
    )
    return ToolContext(settings=settings, storage=Storage(settings.db_path), llm=LocalLLMClient(settings))


def test_code_agent_blocks_path_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("secret-value", encoding="utf-8")

    context = _context(tmp_path, workspace_root=workspace)
    tool = CodeAgentTool()
    result = asyncio.run(tool.execute({"task": "summarize file", "path": str(outside)}, context))

    assert result.success is True
    assert result.data.get("citations") == []


def test_code_agent_allows_path_within_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace2"
    workspace.mkdir(parents=True, exist_ok=True)
    source = workspace / "sample.py"
    source.write_text("print('ok')", encoding="utf-8")

    context = _context(tmp_path, workspace_root=workspace)
    tool = CodeAgentTool()
    result = asyncio.run(tool.execute({"task": "summarize file", "path": str(source)}, context))

    assert result.success is True
    citations = result.data.get("citations")
    assert isinstance(citations, list)
    assert any(str(item).endswith("sample.py") for item in citations)
