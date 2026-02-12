from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from friday.config import Settings


@dataclass(frozen=True)
class ContextMatch:
    path: str
    score: int
    snippet: str


class CodeContextIndex:
    _allowed_extensions = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".json",
        ".md",
        ".toml",
        ".yml",
        ".yaml",
        ".ps1",
        ".cmd",
        ".txt",
    }
    _skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", "models", "data"}

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.workspace_root.resolve()

    def search(self, query: str) -> list[ContextMatch]:
        tokens = self._tokens(query)
        if not tokens:
            return []

        ranked: list[ContextMatch] = []
        for path in self._iter_files():
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lowered = content.lower()
            score = sum(lowered.count(token) for token in tokens)
            if score <= 0:
                continue
            snippet = self._snippet(content, tokens)
            relative = str(path.relative_to(self.root))
            ranked.append(ContextMatch(path=relative, score=score, snippet=snippet))

        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[: self.settings.code_context_max_files]

    def _iter_files(self) -> list[Path]:
        candidates: list[Path] = []
        if not self.root.exists():
            return candidates

        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in self._allowed_extensions:
                continue
            if any(part in self._skip_dirs for part in path.parts):
                continue
            candidates.append(path)
        return candidates

    def _tokens(self, query: str) -> list[str]:
        parts = re.findall(r"[a-zA-Z0-9_]{3,}", query.lower())
        # Keep order while deduplicating.
        seen: set[str] = set()
        tokens: list[str] = []
        for part in parts:
            if part not in seen:
                seen.add(part)
                tokens.append(part)
        return tokens[:8]

    def _snippet(self, content: str, tokens: list[str]) -> str:
        lowered = content.lower()
        pos = -1
        for token in tokens:
            pos = lowered.find(token)
            if pos >= 0:
                break
        if pos < 0:
            return content[: self.settings.code_context_chars_per_file]
        half = self.settings.code_context_chars_per_file // 2
        start = max(0, pos - half)
        end = start + self.settings.code_context_chars_per_file
        return content[start:end]

