"""AssetService for visual asset gathering."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse
import logging

import requests

from app.config import settings
from app.core.error_handling import PermanentError, RetryableError
from app.services.visual_providers.base import (
    SceneVisualRequest,
    compact_scene_text,
    scene_metadata,
)
from app.services.visual_providers.comfyui_provider import ComfyUIVisualProvider
from app.services.visual_providers.scene_card_provider import SceneCardVisualProvider

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10


class AssetService:
    """Collect poster and scene backgrounds for video composition."""

    @staticmethod
    def gather_assets(movie_metadata: Dict[str, Any], scenes: List[str], job_id: str) -> Dict[str, Any]:
        """Gather poster/trailer references and scene-specific background paths."""
        poster_url = movie_metadata.get("poster_url")
        trailer_url = movie_metadata.get("trailer_url")

        poster_path = None
        if poster_url:
            try:
                poster_path = AssetService._download_image(poster_url, f"{job_id}_poster")
            except Exception as e:
                logger.warning(f"[{job_id}] Poster download failed, falling back to placeholder: {str(e)}")

        scene_backgrounds: List[str] = []
        scene_assets: List[Dict[str, Any]] = []
        visual_provider = AssetService._select_visual_provider()
        fallback_provider = SceneCardVisualProvider()
        visual_strategy = visual_provider.source_type

        for i, scene in enumerate(scenes or [], start=1):
            request = SceneVisualRequest(
                job_id=job_id,
                scene_number=i,
                scene_text=compact_scene_text(scene),
                movie_metadata=movie_metadata,
                poster_path=poster_path,
            )
            try:
                visual_result = visual_provider.generate_scene_visual(request)
            except Exception as e:
                logger.warning(
                    f"[{job_id}] Scene visual generation failed for scene {i}; using scene-card fallback: {str(e)}"
                )
                visual_result = fallback_provider.generate_scene_visual(request)
                visual_strategy = f"{visual_provider.source_type}_with_scene_card_fallback"

            background_path = visual_result.path
            scene_backgrounds.append(background_path)
            scene_assets.append(scene_metadata(scene_number=i, result=visual_result, poster_path=poster_path))

        if not scene_backgrounds:
            request = SceneVisualRequest(
                job_id=job_id,
                scene_number=1,
                scene_text="A cinematic opening frame for the movie recap.",
                movie_metadata=movie_metadata,
                poster_path=poster_path,
            )
            visual_result = fallback_provider.generate_scene_visual(request)
            scene_backgrounds.append(visual_result.path)
            scene_assets.append(scene_metadata(scene_number=1, result=visual_result, poster_path=poster_path))

        return {
            "poster_url": poster_url,
            "poster_path": poster_path,
            "trailer_url": trailer_url,
            "scene_backgrounds": scene_backgrounds,
            "scene_assets": scene_assets,
            "visual_strategy": visual_strategy,
        }

    @staticmethod
    def _select_visual_provider():
        provider = (settings.VISUAL_PROVIDER or "scene_card").lower()
        image_provider = (settings.AI_IMAGE_PROVIDER or "").lower()
        if provider == "ai_image" and image_provider in {"local_comfyui", "comfyui", "stable_diffusion"}:
            return ComfyUIVisualProvider()
        if provider not in {"scene_card", "ai_image"}:
            logger.warning(f"Unsupported VISUAL_PROVIDER={provider}; falling back to scene cards")
        elif provider == "ai_image":
            logger.warning(f"Unsupported AI_IMAGE_PROVIDER={image_provider}; falling back to scene cards")
        return SceneCardVisualProvider()

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
        provider = SceneCardVisualProvider()
        request = SceneVisualRequest(
            job_id=job_id,
            scene_number=scene_number,
            scene_text=f"Scene {scene_number}",
            movie_metadata={"title": "Movie Recap", "genres": []},
        )
        return provider.generate_scene_visual(request).path


__all__ = ["AssetService"]
