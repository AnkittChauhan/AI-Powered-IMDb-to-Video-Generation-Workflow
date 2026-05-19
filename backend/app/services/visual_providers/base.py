"""Shared contracts for scene visual providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol


@dataclass(frozen=True)
class SceneVisualRequest:
    """Input required to generate one scene visual."""

    job_id: str
    scene_number: int
    scene_text: str
    movie_metadata: Dict[str, Any]
    poster_path: str | None = None


@dataclass(frozen=True)
class SceneVisualResult:
    """Output produced by a scene visual provider."""

    path: str
    source_type: str
    prompt: str | None = None
    provider_metadata: Dict[str, Any] | None = None


class VisualProvider(Protocol):
    """Provider interface for generating storyboard scene visuals."""

    source_type: str

    def generate_scene_visual(self, request: SceneVisualRequest) -> SceneVisualResult:
        """Generate a local visual asset for a scene."""
        ...


def compact_scene_text(scene: Any) -> str:
    """Normalize scene data from strings or future structured storyboard objects."""
    if isinstance(scene, dict):
        return str(scene.get("visual_prompt") or scene.get("summary") or scene.get("text") or "")
    return str(scene or "")


def build_scene_prompt(request: SceneVisualRequest) -> str:
    """Build a safe, cinematic prompt without asking for actor likenesses."""
    title = str(request.movie_metadata.get("title") or "the film").strip()
    genres = request.movie_metadata.get("genres") or []
    genres_text = ", ".join(genres[:3]) if genres else "cinematic drama"
    scene_text = request.scene_text.strip()

    return (
        "Create a cinematic movie-recap storyboard frame. "
        "Do not depict real actors or exact copyrighted character likenesses. "
        "Use original, generic characters and focus on mood, setting, lighting, and composition. "
        f"Movie title reference: {title}. "
        f"Genre tone: {genres_text}. "
        f"Scene {request.scene_number}: {scene_text}. "
        "Wide cinematic frame, dramatic lighting, high detail, no text, no logos, no captions."
    )


def scene_metadata(
    *,
    scene_number: int,
    result: SceneVisualResult,
    poster_path: str | None,
) -> Dict[str, Any]:
    """Build serializable metadata for a generated scene asset."""
    return {
        "scene_number": scene_number,
        "path": result.path,
        "source_type": result.source_type,
        "prompt": result.prompt,
        "reference_poster_path": poster_path,
        "provider_metadata": result.provider_metadata or {},
    }


def paths_from_results(results: List[SceneVisualResult]) -> List[str]:
    return [result.path for result in results]
