"""Unit tests for VideoService."""

from pathlib import Path

import pytest

from app.config import settings
from app.core.error_handling import PermanentError
from app.services.video_service import VideoService


def test_compose_video_writes_expected_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"fake-audio")
    background_path = tmp_path / "background.jpg"
    background_path.write_bytes(b"fake-image")

    commands = []

    def fake_run_ffmpeg(command):
        commands.append(command)
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-video")

    monkeypatch.setattr(VideoService, "_run_ffmpeg", fake_run_ffmpeg)

    output = VideoService.compose_video(
        job_id="job-video-1",
        scene_backgrounds=[str(background_path)],
        audio_path=str(audio_path),
        subtitles=[{"index": 1, "start": 0.0, "end": 2.0, "text": "Intro"}],
        duration_seconds=2.0,
    )

    assert Path(output["draft_video_path"]).exists()
    assert Path(output["subtitles_path"]).exists()
    assert output["scene_count"] == 1
    assert len(commands) == 3


def test_compose_video_requires_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))

    with pytest.raises(PermanentError):
        VideoService.compose_video(
            job_id="job-video-2",
            scene_backgrounds=[str(tmp_path / "background.jpg")],
            audio_path=str(tmp_path / "missing.mp3"),
            subtitles=[{"index": 1, "start": 0.0, "end": 2.0, "text": "Intro"}],
            duration_seconds=2.0,
        )
