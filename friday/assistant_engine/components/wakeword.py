from __future__ import annotations

import re

from friday.assistant_engine.interfaces import WakeWordDetector


class KeywordWakeWordDetector(WakeWordDetector):
    def __init__(self, wake_words: tuple[str, ...]) -> None:
        filtered = [item.strip().lower() for item in wake_words if item.strip()]
        self._wake_words = tuple(filtered)
        pattern = "|".join(re.escape(word) for word in self._wake_words) if self._wake_words else ""
        self._regex = (
            re.compile(
                rf"^\s*(?:hey|ok|okay)?\s*(?:{pattern})\b[\s,:\-]*(?P<command>.*)$",
                flags=re.IGNORECASE,
            )
            if pattern
            else None
        )

    def detect(self, text: str) -> tuple[bool, str]:
        trimmed = text.strip()
        if not trimmed:
            return False, ""
        if self._regex is None:
            return True, trimmed

        match = self._regex.match(trimmed)
        if match is None:
            return False, trimmed
        return True, match.group("command").strip()
