"""Storage path management for generated media artifacts."""

from __future__ import annotations

from pathlib import Path

from app.config import settings


class StorageService:
    """Owns deterministic local paths for job artifacts.

    Keeping path construction here prevents every pipeline stage from inventing
    its own storage layout. That matters for retries now and S3 migration later.
    """

    @staticmethod
    def base_dir() -> Path:
        return Path(settings.LOCAL_STORAGE_PATH)

    @staticmethod
    def job_dir(job_id: str) -> Path:
        path = StorageService.base_dir() / "jobs" / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def audio_path(job_id: str) -> Path:
        return StorageService.job_dir(job_id) / "voiceover.mp3"

    @staticmethod
    def subtitles_path(job_id: str) -> Path:
        return StorageService.job_dir(job_id) / "subtitles.srt"

    @staticmethod
    def scene_segment_path(job_id: str, scene_number: int) -> Path:
        segments_dir = StorageService.job_dir(job_id) / "segments"
        segments_dir.mkdir(parents=True, exist_ok=True)
        return segments_dir / f"scene_{scene_number:02d}.mp4"

    @staticmethod
    def concat_manifest_path(job_id: str) -> Path:
        return StorageService.job_dir(job_id) / "concat.txt"

    @staticmethod
    def draft_video_path(job_id: str) -> Path:
        return StorageService.job_dir(job_id) / "draft.mp4"

    @staticmethod
    def final_video_path(job_id: str) -> Path:
        return StorageService.job_dir(job_id) / "final.mp4"


__all__ = ["StorageService"]
