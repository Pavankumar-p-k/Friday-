from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    items = [item.strip() for item in value.split(",")]
    filtered = tuple(item for item in items if item)
    return filtered or default


def _parse_allowed_apps(value: str | None) -> dict[str, str]:
    default = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "vscode": "code",
        "chrome": "chrome",
        "edge": "msedge",
    }
    if not value:
        return default

    mapping: dict[str, str] = {}
    pairs = [item.strip() for item in value.split(";") if item.strip()]
    for pair in pairs:
        if "=" not in pair:
            continue
        name, command = pair.split("=", 1)
        if name.strip() and command.strip():
            mapping[name.strip().lower()] = command.strip()
    return mapping or default


@dataclass(frozen=True)
class Settings:
    app_name: str = "FRIDAY Offline"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    db_path: Path = Path("data/sqlite/friday.db")
    auto_execute_low_risk: bool = True
    max_plan_steps: int = 6
    request_timeout_sec: int = 45
    allowed_tools: tuple[str, ...] = (
        "open_app",
        "media_control",
        "reminder",
        "code_agent",
        "safe_shell",
    )
    allowed_shell_prefixes: tuple[str, ...] = (
        "echo",
        "dir",
        "Get-Process",
        "Get-Date",
        "python --version",
    )
    allowed_apps: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        base = cls()
        return cls(
            app_name=os.getenv("FRIDAY_APP_NAME", base.app_name),
            ollama_base_url=os.getenv("FRIDAY_OLLAMA_BASE_URL", base.ollama_base_url),
            ollama_model=os.getenv("FRIDAY_OLLAMA_MODEL", base.ollama_model),
            db_path=Path(os.getenv("FRIDAY_DB_PATH", str(base.db_path))),
            auto_execute_low_risk=_parse_bool(
                os.getenv("FRIDAY_AUTO_EXECUTE_LOW_RISK"),
                base.auto_execute_low_risk,
            ),
            max_plan_steps=int(os.getenv("FRIDAY_MAX_PLAN_STEPS", str(base.max_plan_steps))),
            request_timeout_sec=int(
                os.getenv("FRIDAY_REQUEST_TIMEOUT_SEC", str(base.request_timeout_sec))
            ),
            allowed_tools=_parse_csv(os.getenv("FRIDAY_ALLOWED_TOOLS"), base.allowed_tools),
            allowed_shell_prefixes=_parse_csv(
                os.getenv("FRIDAY_ALLOWED_SHELL_PREFIXES"),
                base.allowed_shell_prefixes,
            ),
            allowed_apps=_parse_allowed_apps(os.getenv("FRIDAY_ALLOWED_APPS")),
        )
