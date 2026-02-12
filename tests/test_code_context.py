from pathlib import Path

from friday.code_context import CodeContextIndex
from friday.config import Settings


def test_code_context_finds_relevant_files(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text("def fibonacci(n): return n", encoding="utf-8")
    (root / "notes.md").write_text("project planning notes", encoding="utf-8")

    settings = Settings(
        workspace_root=root,
        db_path=tmp_path / "db.sqlite",
        code_context_max_files=3,
        code_context_chars_per_file=400,
    )
    index = CodeContextIndex(settings)
    matches = index.search("fibonacci python function")
    assert matches
    assert any(match.path.endswith("main.py") for match in matches)

