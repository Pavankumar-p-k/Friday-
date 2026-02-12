from pathlib import Path

from friday.config import Settings
from friday.policy import PolicyEngine
from friday.schemas import PlanStep


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "test.db",
        allowed_apps={"notepad": "notepad.exe"},
    )


def test_open_app_allowlisted(tmp_path: Path) -> None:
    policy = PolicyEngine(_settings(tmp_path))
    step = PlanStep(id="s1", description="Open notepad", tool="open_app", args={"app_name": "notepad"})
    decision = policy.evaluate(step)
    assert decision.allowed is True
    assert decision.needs_approval is False


def test_open_app_blocked_if_not_allowlisted(tmp_path: Path) -> None:
    policy = PolicyEngine(_settings(tmp_path))
    step = PlanStep(id="s1", description="Open cmd", tool="open_app", args={"app_name": "cmd"})
    decision = policy.evaluate(step)
    assert decision.allowed is False
    assert decision.needs_approval is True


def test_safe_shell_requires_allowlisted_prefix(tmp_path: Path) -> None:
    policy = PolicyEngine(_settings(tmp_path))
    step = PlanStep(
        id="s1",
        description="Run command",
        tool="safe_shell",
        args={"command": "Get-Date"},
    )
    decision = policy.evaluate(step)
    assert decision.allowed is True
    assert decision.needs_approval is True


def test_safe_shell_blocks_dangerous_term(tmp_path: Path) -> None:
    policy = PolicyEngine(_settings(tmp_path))
    step = PlanStep(
        id="s1",
        description="Run dangerous command",
        tool="safe_shell",
        args={"command": "echo hi && shutdown /s /t 0"},
    )
    decision = policy.evaluate(step)
    assert decision.allowed is False
