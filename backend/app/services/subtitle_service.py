"""Subtitle artifact helpers."""

from __future__ import annotations

from pathlib import Path
from textwrap import wrap
from typing import Any, Dict, Iterable, List

from app.core.error_handling import PermanentError


class SubtitleService:
    """Converts subtitle timeline data into durable SRT files."""

    @staticmethod
    def write_srt(subtitles: Iterable[Dict[str, Any]], output_path: str | Path) -> str:
        items = list(subtitles)
        if not items:
            raise PermanentError("Cannot write subtitles: subtitle list is empty")

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        blocks: List[str] = []

        for fallback_index, item in enumerate(items, start=1):
            start = float(item.get("start", 0))
            end = float(item.get("end", 0))
            text = str(item.get("text", "")).strip()
            index = int(item.get("index") or fallback_index)

            if end <= start:
                raise PermanentError(f"Invalid subtitle timing at index {index}")
            if not text:
                raise PermanentError(f"Missing subtitle text at index {index}")

            wrapped_text = "\n".join(wrap(text, width=48)) or text
            blocks.append(
                "\n".join(
                    [
                        str(index),
                        f"{SubtitleService.format_timestamp(start)} --> {SubtitleService.format_timestamp(end)}",
                        wrapped_text,
                    ]
                )
            )

        path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
        return str(path)

    @staticmethod
    def format_timestamp(seconds: float) -> str:
        total_ms = max(0, int(round(seconds * 1000)))
        hours, remainder = divmod(total_ms, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, millis = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


__all__ = ["SubtitleService"]
