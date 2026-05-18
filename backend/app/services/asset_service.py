"""AssetService for visual asset gathering."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse
import logging

import requests

from app.config import settings
from app.core.error_handling import PermanentError, RetryableError

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10


class AssetService:
    """Collect poster and scene backgrounds for video composition."""

    @staticmethod
    def gather_assets(movie_metadata: Dict[str, Any], scenes: List[str], job_id: str) -> Dict[str, Any]:
        """Gather poster/trailer references and scene background paths."""
        poster_url = movie_metadata.get("poster_url")
        trailer_url = movie_metadata.get("trailer_url")

        poster_path = None
        if poster_url:
            try:
                poster_path = AssetService._download_image(poster_url, f"{job_id}_poster")
            except Exception as e:
                logger.warning(f"[{job_id}] Poster download failed, falling back to placeholder: {str(e)}")

        scene_backgrounds: List[str] = []
        for i, _ in enumerate(scenes or [], start=1):
            if poster_path:
                scene_backgrounds.append(poster_path)
            else:
                scene_backgrounds.append(AssetService._create_placeholder(job_id, i))

        if not scene_backgrounds:
            scene_backgrounds.append(AssetService._create_placeholder(job_id, 1))

        return {
            "poster_url": poster_url,
            "poster_path": poster_path,
            "trailer_url": trailer_url,
            "scene_backgrounds": scene_backgrounds,
        }

    @staticmethod
    def _download_image(url: str, file_stem: str) -> str:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise PermanentError(f"Invalid image URL: {url}")

        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.Timeout as e:
            raise RetryableError(f"Asset download timed out: {str(e)}")
        except requests.ConnectionError as e:
            raise RetryableError(f"Asset connection error: {str(e)}")
        except requests.RequestException as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code in (429, 500, 502, 503, 504):
                raise RetryableError(f"Transient asset download failure ({status_code}): {str(e)}")
            raise PermanentError(f"Asset download failed: {str(e)}")

        content_type = response.headers.get("content-type", "").lower()
        if "image" not in content_type:
            raise PermanentError(f"URL did not return image content: {content_type}")

        output_dir = Path(settings.LOCAL_STORAGE_PATH) / "assets"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{file_stem}.jpg"
        output_path.write_bytes(response.content)
        return str(output_path)

    @staticmethod
    def _create_placeholder(job_id: str, scene_number: int) -> str:
        output_dir = Path(settings.LOCAL_STORAGE_PATH) / "assets" / "placeholders"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{job_id}_scene_{scene_number}.svg"
        output_path.write_text(
            (
                '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080">'
                '<rect width="100%" height="100%" fill="#1f2937"/>'
                '<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" '
                'fill="#e5e7eb" font-size="54" font-family="Arial">'
                f"Scene {scene_number}"
                "</text></svg>"
            ),
            encoding="utf-8",
        )
        return str(output_path)


__all__ = ["AssetService"]
