"""Unit tests for StorageService."""

from app.config import settings
from app.services.storage_service import StorageService


def test_storage_paths_are_job_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))

    job_dir = StorageService.job_dir("job-1")

    assert job_dir.exists()
    assert StorageService.audio_path("job-1").name == "voiceover.mp3"
    assert StorageService.subtitles_path("job-1").name == "subtitles.srt"
    assert StorageService.draft_video_path("job-1").name == "draft.mp4"
    assert StorageService.final_video_path("job-1").name == "final.mp4"
    assert "job-1" in str(StorageService.scene_segment_path("job-1", 2))
