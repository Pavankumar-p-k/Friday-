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


def _parse_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    return Path(value)


def _parse_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


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
    blocked_shell_terms: tuple[str, ...] = (
        " rm ",
        "del ",
        "format ",
        "shutdown ",
        "restart-computer",
        "stop-computer",
        "rmdir /s",
        "Remove-Item -Recurse",
        "mkfs",
        "diskpart",
        "reg delete",
    )
    workspace_root: Path = Path(".")
    code_context_max_files: int = 6
    code_context_chars_per_file: int = 1200
    reminder_poll_interval_sec: int = 15
    voice_input_dir: Path = Path("data/voice/inbox")
    voice_output_dir: Path = Path("data/voice/out")
    voice_stt_command: str = ""
    voice_tts_command: str = ""
    voice_wake_words: tuple[str, ...] = ("friday", "jarvis")
    jarvis_plugins_dir: Path = Path("plugins")
    allowed_apps: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        base = cls()
        return cls(
            app_name=os.getenv("FRIDAY_APP_NAME", base.app_name),
            ollama_base_url=os.getenv("FRIDAY_OLLAMA_BASE_URL", base.ollama_base_url),
            ollama_model=os.getenv("FRIDAY_OLLAMA_MODEL", base.ollama_model),
            db_path=_parse_path(os.getenv("FRIDAY_DB_PATH"), base.db_path),
            auto_execute_low_risk=_parse_bool(
                os.getenv("FRIDAY_AUTO_EXECUTE_LOW_RISK"),
                base.auto_execute_low_risk,
            ),
            max_plan_steps=_parse_int(os.getenv("FRIDAY_MAX_PLAN_STEPS"), base.max_plan_steps),
            request_timeout_sec=_parse_int(
                os.getenv("FRIDAY_REQUEST_TIMEOUT_SEC"),
                base.request_timeout_sec,
            ),
            allowed_tools=_parse_csv(os.getenv("FRIDAY_ALLOWED_TOOLS"), base.allowed_tools),
            allowed_shell_prefixes=_parse_csv(
                os.getenv("FRIDAY_ALLOWED_SHELL_PREFIXES"),
                base.allowed_shell_prefixes,
            ),
            blocked_shell_terms=_parse_csv(
                os.getenv("FRIDAY_BLOCKED_SHELL_TERMS"),
                base.blocked_shell_terms,
            ),
            workspace_root=_parse_path(os.getenv("FRIDAY_WORKSPACE_ROOT"), base.workspace_root),
            code_context_max_files=_parse_int(
                os.getenv("FRIDAY_CODE_CONTEXT_MAX_FILES"),
                base.code_context_max_files,
            ),
            code_context_chars_per_file=_parse_int(
                os.getenv("FRIDAY_CODE_CONTEXT_CHARS_PER_FILE"),
                base.code_context_chars_per_file,
            ),
            reminder_poll_interval_sec=_parse_int(
                os.getenv("FRIDAY_REMINDER_POLL_INTERVAL_SEC"),
                base.reminder_poll_interval_sec,
            ),
            voice_input_dir=_parse_path(os.getenv("FRIDAY_VOICE_INPUT_DIR"), base.voice_input_dir),
            voice_output_dir=_parse_path(
                os.getenv("FRIDAY_VOICE_OUTPUT_DIR"),
                base.voice_output_dir,
            ),
            voice_stt_command=os.getenv("FRIDAY_VOICE_STT_COMMAND", base.voice_stt_command),
            voice_tts_command=os.getenv("FRIDAY_VOICE_TTS_COMMAND", base.voice_tts_command),
            voice_wake_words=_parse_csv(
                os.getenv("FRIDAY_VOICE_WAKE_WORDS"),
                base.voice_wake_words,
            ),
            jarvis_plugins_dir=_parse_path(
                os.getenv("FRIDAY_JARVIS_PLUGINS_DIR"),
                base.jarvis_plugins_dir,
            ),
            allowed_apps=_parse_allowed_apps(os.getenv("FRIDAY_ALLOWED_APPS")),
        )
