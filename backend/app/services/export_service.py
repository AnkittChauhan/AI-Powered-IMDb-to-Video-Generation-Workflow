"""Final MP4 export service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import logging
import subprocess

from app.core.error_handling import FFmpegError, PermanentError
from app.services.storage_service import StorageService
from app.utils.constants import AUDIO_BITRATE, AUDIO_CODEC, VIDEO_BITRATE, VIDEO_CODEC, VIDEO_FPS, VIDEO_RESOLUTION

logger = logging.getLogger(__name__)


class ExportService:
    """Normalizes a composed draft video into the final delivery MP4."""

    @staticmethod
    def export_mp4(*, job_id: str, draft_video_path: str) -> Dict[str, Any]:
        draft_path = Path(draft_video_path)
        if not draft_path.exists():
            raise PermanentError(f"Cannot export video: draft file missing: {draft_video_path}")

        final_path = StorageService.final_video_path(job_id)
        codec = "libx264" if VIDEO_CODEC in {"h264", "libx264"} else VIDEO_CODEC
        ExportService._run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(draft_path),
                "-vf",
                f"scale={VIDEO_RESOLUTION}:force_original_aspect_ratio=decrease,"
                f"pad={VIDEO_RESOLUTION}:(ow-iw)/2:(oh-ih)/2,setsar=1",
                "-r",
                str(VIDEO_FPS),
                "-c:v",
                codec,
                "-b:v",
                VIDEO_BITRATE,
                "-c:a",
                AUDIO_CODEC,
                "-b:a",
                AUDIO_BITRATE,
                "-movflags",
                "+faststart",
                str(final_path),
            ]
        )

        return {
            "final_video_path": str(final_path),
            "file_size_bytes": final_path.stat().st_size if final_path.exists() else None,
        }

    @staticmethod
    def _run_ffmpeg(command: list[str]) -> None:
        logger.debug("Running FFmpeg export command", extra={"command": command})
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            raise FFmpegError("ffmpeg binary not found")
        except OSError as e:
            raise FFmpegError(f"Could not start ffmpeg: {str(e)}", is_retryable=True)

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise FFmpegError(stderr or f"ffmpeg exited with code {result.returncode}")


__all__ = ["ExportService"]
