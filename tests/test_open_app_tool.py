import asyncio
from pathlib import Path

from friday.config import Settings
from friday.llm import LocalLLMClient
from friday.storage import Storage
from friday.tools.base import ToolContext
from friday.tools.open_app import OpenAppTool
import friday.tools.open_app as open_app_module


def _context(tmp_path: Path, allowed_apps: dict[str, str]) -> ToolContext:
    settings = Settings(
        db_path=tmp_path / "open_app_tool.db",
        allowed_apps=allowed_apps,
    )
    return ToolContext(settings=settings, storage=Storage(settings.db_path), llm=LocalLLMClient(settings))


def test_open_app_uses_shell_false_and_split_args(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path, allowed_apps={"notepad": "notepad.exe /A"})
    tool = OpenAppTool()
    seen: dict[str, object] = {}

    def fake_popen(args, shell):  # type: ignore[no-untyped-def]
        seen["args"] = args
        seen["shell"] = shell
        return object()

    monkeypatch.setattr(open_app_module.subprocess, "Popen", fake_popen)
    result = asyncio.run(tool.execute({"app_name": "notepad"}, context))

    assert result.success is True
    assert seen["shell"] is False
    assert seen["args"] == ["notepad.exe", "/A"]


def test_open_app_rejects_invalid_command_format(tmp_path: Path) -> None:
    context = _context(tmp_path, allowed_apps={"badapp": '"unterminated'})
    tool = OpenAppTool()
    result = asyncio.run(tool.execute({"app_name": "badapp"}, context))
    assert result.success is False
    assert "invalid app command" in result.message.lower()
