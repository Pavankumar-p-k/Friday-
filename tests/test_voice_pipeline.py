from pathlib import Path

import pytest

from friday.config import Settings
from friday.voice import VoicePipeline


def _pipeline(tmp_path: Path, max_bytes: int) -> VoicePipeline:
    settings = Settings(
        db_path=tmp_path / "voice_pipeline.db",
        voice_input_dir=tmp_path / "voice_in",
        voice_output_dir=tmp_path / "voice_out",
        voice_max_upload_bytes=max_bytes,
    )
    return VoicePipeline(settings)


def test_save_upload_enforces_max_bytes(tmp_path: Path) -> None:
    pipeline = _pipeline(tmp_path, max_bytes=4)
    with pytest.raises(ValueError):
        pipeline.save_upload("clip.wav", b"12345")


def test_save_upload_writes_file(tmp_path: Path) -> None:
    pipeline = _pipeline(tmp_path, max_bytes=8)
    target = pipeline.save_upload("clip.wav", b"1234")
    assert target.exists()
    assert target.read_bytes() == b"1234"
