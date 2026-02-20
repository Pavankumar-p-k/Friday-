from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class EngineConfig:
    wake_words: tuple[str, ...] = ("friday", "jarvis")
    require_wake_word: bool = True
    queue_max_size: int = 128
    log_level: str = "INFO"

    stt_emit_partials: bool = True
    stt_min_partial_chars: int = 8

    cloud_llm_enabled: bool = False
    cloud_llm_base_url: str = "https://api.openai.com/v1/chat/completions"
    cloud_llm_model: str = "gpt-4o-mini"
    cloud_llm_api_key: str = ""
    cloud_timeout_sec: int = 30

    tts_output_dir: Path = Path("data/voice/out")

    @classmethod
    def from_env(cls) -> "EngineConfig":
        base = cls()
        wake_raw = os.getenv("FRIDAY_ENGINE_WAKE_WORDS")
        wake_words = base.wake_words
        if wake_raw:
            items = tuple(
                token.strip().lower() for token in wake_raw.split(",") if token.strip()
            )
            if items:
                wake_words = items

        return cls(
            wake_words=wake_words,
            require_wake_word=_bool_env(
                "FRIDAY_ENGINE_REQUIRE_WAKE_WORD",
                base.require_wake_word,
            ),
            queue_max_size=max(8, _int_env("FRIDAY_ENGINE_QUEUE_MAX_SIZE", base.queue_max_size)),
            log_level=os.getenv("FRIDAY_ENGINE_LOG_LEVEL", base.log_level),
            stt_emit_partials=_bool_env("FRIDAY_ENGINE_STT_EMIT_PARTIALS", base.stt_emit_partials),
            stt_min_partial_chars=max(
                1,
                _int_env("FRIDAY_ENGINE_STT_MIN_PARTIAL_CHARS", base.stt_min_partial_chars),
            ),
            cloud_llm_enabled=_bool_env("FRIDAY_ENGINE_CLOUD_LLM_ENABLED", base.cloud_llm_enabled),
            cloud_llm_base_url=os.getenv(
                "FRIDAY_ENGINE_CLOUD_LLM_BASE_URL",
                base.cloud_llm_base_url,
            ),
            cloud_llm_model=os.getenv("FRIDAY_ENGINE_CLOUD_LLM_MODEL", base.cloud_llm_model),
            cloud_llm_api_key=os.getenv("FRIDAY_ENGINE_CLOUD_LLM_API_KEY", base.cloud_llm_api_key),
            cloud_timeout_sec=max(
                5,
                _int_env("FRIDAY_ENGINE_CLOUD_TIMEOUT_SEC", base.cloud_timeout_sec),
            ),
            tts_output_dir=Path(os.getenv("FRIDAY_ENGINE_TTS_OUTPUT_DIR", str(base.tts_output_dir))),
        )
