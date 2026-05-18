"""Video composition service backed by FFmpeg."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import logging
import shlex
import subprocess

from app.core.error_handling import FFmpegError, PermanentError
from app.services.storage_service import StorageService
from app.services.subtitle_service import SubtitleService
from app.utils.constants import VIDEO_FPS, VIDEO_RESOLUTION

logger = logging.getLogger(__name__)


class VideoService:
    """Composes scene visuals, voiceover, and subtitles into a draft MP4."""

    @staticmethod
    def compose_video(
        *,
        job_id: str,
        scene_backgrounds: List[str],
        audio_path: str,
        subtitles: List[Dict[str, Any]],
        duration_seconds: float,
    ) -> Dict[str, Any]:
        VideoService._validate_inputs(scene_backgrounds, audio_path, subtitles, duration_seconds)

        subtitle_path = SubtitleService.write_srt(subtitles, StorageService.subtitles_path(job_id))
        scene_count = max(1, len(scene_backgrounds))
        scene_duration = max(1.0, float(duration_seconds) / scene_count)

        segment_paths: List[Path] = []
        for index, background_path in enumerate(scene_backgrounds, start=1):
            segment_path = StorageService.scene_segment_path(job_id, index)
            VideoService._render_scene_segment(
                background_path=background_path,
                output_path=segment_path,
                duration_seconds=scene_duration,
                scene_number=index,
            )
            segment_paths.append(segment_path)

        manifest_path = StorageService.concat_manifest_path(job_id)
        VideoService._write_concat_manifest(segment_paths, manifest_path)

        visual_track_path = StorageService.job_dir(job_id) / "visual_track.mp4"
        VideoService._run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(manifest_path),
                "-c",
                "copy",
                str(visual_track_path),
            ]
        )

        draft_path = StorageService.draft_video_path(job_id)
        subtitle_filter = f"subtitles={VideoService._escape_filter_path(subtitle_path)}"
        VideoService._run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(visual_track_path),
                "-i",
                audio_path,
                "-vf",
                subtitle_filter,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-shortest",
                "-movflags",
                "+faststart",
                str(draft_path),
            ]
        )

        return {
            "draft_video_path": str(draft_path),
            "subtitles_path": subtitle_path,
            "duration_seconds": float(duration_seconds),
            "scene_count": scene_count,
        }

    @staticmethod
    def _validate_inputs(
        scene_backgrounds: List[str],
        audio_path: str,
        subtitles: List[Dict[str, Any]],
        duration_seconds: float,
    ) -> None:
        if not scene_backgrounds:
            raise PermanentError("Cannot compose video: no scene backgrounds provided")
        if not audio_path or not Path(audio_path).exists():
            raise PermanentError(f"Cannot compose video: audio file missing: {audio_path}")
        if not subtitles:
            raise PermanentError("Cannot compose video: subtitles missing")
        if duration_seconds <= 0:
            raise PermanentError("Cannot compose video: duration must be greater than zero")

        for path in scene_backgrounds:
            if Path(path).suffix.lower() == ".svg":
                continue
            if not Path(path).exists():
                raise PermanentError(f"Cannot compose video: background file missing: {path}")

    @staticmethod
    def _render_scene_segment(
        *,
        background_path: str,
        output_path: Path,
        duration_seconds: float,
        scene_number: int,
    ) -> None:
        if Path(background_path).suffix.lower() == ".svg":
            source_args = ["-f", "lavfi", "-i", f"color=c=0x101114:s={VIDEO_RESOLUTION}:r={VIDEO_FPS}"]
            filter_args = [
                "-vf",
                (
                    "drawtext=text='Scene "
                    f"{scene_number}':fontcolor=white:fontsize=54:x=(w-text_w)/2:y=(h-text_h)/2"
                ),
            ]
        else:
            source_args = ["-loop", "1", "-i", background_path]
            filter_args = [
                "-vf",
                (
                    f"scale={VIDEO_RESOLUTION}:force_original_aspect_ratio=increase,"
                    f"crop={VIDEO_RESOLUTION},format=yuv420p"
                ),
            ]

        VideoService._run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                *source_args,
                "-t",
                f"{duration_seconds:.3f}",
                *filter_args,
                "-r",
                str(VIDEO_FPS),
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ]
        )

    @staticmethod
    def _write_concat_manifest(segment_paths: List[Path], manifest_path: Path) -> None:
        lines = [f"file {shlex.quote(str(path))}" for path in segment_paths]
        manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _escape_filter_path(path: str) -> str:
        return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    @staticmethod
    def _run_ffmpeg(command: List[str]) -> None:
        logger.debug("Running FFmpeg command", extra={"command": command})
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            raise FFmpegError("ffmpeg binary not found")
        except OSError as e:
            raise FFmpegError(f"Could not start ffmpeg: {str(e)}", is_retryable=True)

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise FFmpegError(stderr or f"ffmpeg exited with code {result.returncode}")


__all__ = ["VideoService"]
