"""Visual asset providers for storyboard scenes."""

from app.services.visual_providers.base import SceneVisualRequest, SceneVisualResult, VisualProvider
from app.services.visual_providers.comfyui_provider import ComfyUIVisualProvider
from app.services.visual_providers.scene_card_provider import SceneCardVisualProvider

__all__ = [
    "ComfyUIVisualProvider",
    "SceneCardVisualProvider",
    "SceneVisualRequest",
    "SceneVisualResult",
    "VisualProvider",
]
