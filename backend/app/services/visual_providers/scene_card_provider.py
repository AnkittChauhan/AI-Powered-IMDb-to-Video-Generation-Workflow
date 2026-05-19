"""Local SVG fallback provider for storyboard scene visuals."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Dict, List
import re
import textwrap

from app.config import settings
from app.services.visual_providers.base import SceneVisualRequest, SceneVisualResult
from app.utils.constants import VIDEO_HEIGHT, VIDEO_WIDTH

SCENE_CARD_PALETTES = [
    ("#101114", "#1f3a5f", "#e8eef8"),
    ("#12100f", "#7a2e2e", "#fff1dd"),
    ("#071712", "#19634f", "#ecfff7"),
    ("#171421", "#51427c", "#f2edff"),
    ("#14130f", "#74612f", "#fff7d6"),
    ("#0e1724", "#2c5871", "#e9f7ff"),
    ("#1a1117", "#713b62", "#fff0fa"),
    ("#111827", "#374151", "#f9fafb"),
]


class SceneCardVisualProvider:
    """Generate local SVG scene cards when richer image providers are unavailable."""

    source_type = "generated_scene_card"

    def generate_scene_visual(self, request: SceneVisualRequest) -> SceneVisualResult:
        output_path = self._create_scene_card(
            job_id=request.job_id,
            scene_number=request.scene_number,
            scene_text=request.scene_text,
            movie_metadata=request.movie_metadata,
        )
        return SceneVisualResult(
            path=output_path,
            source_type=self.source_type,
            prompt=request.scene_text,
        )

    @staticmethod
    def _create_scene_card(
        *,
        job_id: str,
        scene_number: int,
        scene_text: str,
        movie_metadata: Dict[str, Any],
    ) -> str:
        output_dir = Path(settings.LOCAL_STORAGE_PATH) / "assets" / "placeholders"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{job_id}_scene_{scene_number}.svg"

        base_color, accent_color, text_color = SCENE_CARD_PALETTES[(scene_number - 1) % len(SCENE_CARD_PALETTES)]
        title = escape(str(movie_metadata.get("title") or "Movie Recap"))
        genre_text = escape(", ".join((movie_metadata.get("genres") or [])[:3]) or "Cinematic Summary")
        scene_lines = SceneCardVisualProvider._wrap_svg_lines(scene_text)
        line_nodes = "\n".join(
            (
                f'<text x="150" y="{520 + (idx * 62)}" fill="{text_color}" '
                'font-size="42" font-family="Arial, Helvetica, sans-serif">'
                f"{escape(line)}</text>"
            )
            for idx, line in enumerate(scene_lines)
        )

        output_path.write_text(
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{VIDEO_WIDTH}" height="{VIDEO_HEIGHT}" '
                f'viewBox="0 0 {VIDEO_WIDTH} {VIDEO_HEIGHT}">'
                "<defs>"
                '<linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">'
                f'<stop offset="0%" stop-color="{base_color}"/>'
                f'<stop offset="100%" stop-color="{accent_color}"/>'
                "</linearGradient>"
                "</defs>"
                '<rect width="100%" height="100%" fill="url(#bg)"/>'
                '<rect x="0" y="0" width="100%" height="100%" fill="#000000" opacity="0.18"/>'
                f'<circle cx="1550" cy="180" r="260" fill="{text_color}" opacity="0.08"/>'
                f'<circle cx="240" cy="900" r="330" fill="{text_color}" opacity="0.06"/>'
                f'<rect x="96" y="96" width="1728" height="888" rx="38" fill="#000000" opacity="0.30"/>'
                f'<text x="150" y="190" fill="{text_color}" opacity="0.72" '
                'font-size="30" font-family="Arial, Helvetica, sans-serif" letter-spacing="3">'
                f"{genre_text.upper()}</text>"
                f'<text x="150" y="280" fill="{text_color}" font-size="74" '
                'font-family="Arial, Helvetica, sans-serif" font-weight="700">'
                f"{title}</text>"
                f'<text x="150" y="405" fill="{text_color}" opacity="0.82" '
                'font-size="44" font-family="Arial, Helvetica, sans-serif">'
                f"Scene {scene_number:02d}</text>"
                f"{line_nodes}"
                f'<rect x="150" y="890" width="480" height="4" fill="{text_color}" opacity="0.42"/>'
                f'<text x="150" y="945" fill="{text_color}" opacity="0.64" '
                'font-size="28" font-family="Arial, Helvetica, sans-serif">'
                "Generated storyboard visual</text>"
                "</svg>"
            ),
            encoding="utf-8",
        )
        return str(output_path)

    @staticmethod
    def _wrap_svg_lines(scene_text: str) -> List[str]:
        cleaned = re.sub(r"\s+", " ", scene_text).strip()
        cleaned = re.sub(r"(?i)^scene\s+\d+[:\-]?\s*", "", cleaned).strip()
        if not cleaned:
            cleaned = "A cinematic beat from the movie recap."
        return textwrap.wrap(cleaned, width=58, max_lines=4, placeholder="...")
