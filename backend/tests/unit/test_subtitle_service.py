"""Unit tests for SubtitleService."""

import pytest

from app.core.error_handling import PermanentError
from app.services.subtitle_service import SubtitleService


def test_format_timestamp():
    assert SubtitleService.format_timestamp(65.432) == "00:01:05,432"


def test_write_srt(tmp_path):
    output = SubtitleService.write_srt(
        [{"index": 1, "start": 0.0, "end": 2.5, "text": "Hello cinematic world"}],
        tmp_path / "captions.srt",
    )

    content = (tmp_path / "captions.srt").read_text(encoding="utf-8")
    assert output.endswith("captions.srt")
    assert "00:00:00,000 --> 00:00:02,500" in content
    assert "Hello cinematic world" in content


def test_write_srt_rejects_invalid_timing(tmp_path):
    with pytest.raises(PermanentError):
        SubtitleService.write_srt(
            [{"index": 1, "start": 3.0, "end": 2.0, "text": "Bad timing"}],
            tmp_path / "bad.srt",
        )
