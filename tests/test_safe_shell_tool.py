import asyncio
from pathlib import Path
import subprocess

from friday.config import Settings
from friday.llm import LocalLLMClient
from friday.storage import Storage
from friday.tools.base import ToolContext
from friday.tools.safe_shell import SafeShellTool
import friday.tools.safe_shell as safe_shell_module


def _context(tmp_path: Path) -> ToolContext:
    settings = Settings(db_path=tmp_path / "safe_shell_tool.db")
    return ToolContext(settings=settings, storage=Storage(settings.db_path), llm=LocalLLMClient(settings))


def test_safe_shell_blocks_control_operator(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    tool = SafeShellTool()
    called = {"value": False}

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        called["value"] = True
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(safe_shell_module.subprocess, "run", fake_run)
    result = asyncio.run(tool.execute({"command": "echo hello && whoami"}, context))

    assert result.success is False
    assert called["value"] is False
    assert "control operator" in result.message.lower()


def test_safe_shell_uses_powershell_for_cmdlet(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    tool = SafeShellTool()
    seen: dict[str, object] = {}

    def fake_run(args, shell, capture_output, text, timeout):  # type: ignore[no-untyped-def]
        seen["args"] = args
        seen["shell"] = shell
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(safe_shell_module.subprocess, "run", fake_run)
    result = asyncio.run(tool.execute({"command": "Get-Date"}, context))

    assert result.success is True
    assert seen["shell"] is False
    assert seen["args"] == ["powershell", "-NoProfile", "-Command", "Get-Date"]


def test_safe_shell_blocks_line_break(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    tool = SafeShellTool()
    called = {"value": False}

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        called["value"] = True
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(safe_shell_module.subprocess, "run", fake_run)
    result = asyncio.run(tool.execute({"command": "echo ok\nwhoami"}, context))

    assert result.success is False
    assert called["value"] is False
    assert "line break" in result.message.lower()


def test_safe_shell_rejects_prefix_superset(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    tool = SafeShellTool()
    called = {"value": False}

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        called["value"] = True
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(safe_shell_module.subprocess, "run", fake_run)
    result = asyncio.run(tool.execute({"command": "python --versionx"}, context))

    assert result.success is False
    assert called["value"] is False
    assert "allowlist" in result.message.lower()
