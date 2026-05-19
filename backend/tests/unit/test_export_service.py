"""Unit tests for ExportService."""

from pathlib import Path

import pytest

from app.config import settings
from app.core.error_handling import PermanentError
from app.services.export_service import ExportService


def test_export_mp4_writes_final_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    draft_path = tmp_path / "draft.mp4"
    draft_path.write_bytes(b"draft")
    commands = []

    def fake_run_ffmpeg(command):
        commands.append(command)
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"final-video")

    monkeypatch.setattr(ExportService, "_run_ffmpeg", fake_run_ffmpeg)

    output = ExportService.export_mp4(job_id="job-export-1", draft_video_path=str(draft_path))

    assert Path(output["final_video_path"]).exists()
    assert output["file_size_bytes"] == len(b"final-video")
    export_filter = commands[0][commands[0].index("-vf") + 1]
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in export_filter
    assert "pad=1920:1080:(ow-iw)/2:(oh-ih)/2" in export_filter


def test_export_mp4_requires_draft_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))

    with pytest.raises(PermanentError):
        ExportService.export_mp4(job_id="job-export-2", draft_video_path=str(tmp_path / "missing.mp4"))
