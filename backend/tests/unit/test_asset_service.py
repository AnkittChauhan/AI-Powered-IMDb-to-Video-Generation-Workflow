"""Unit tests for AssetService."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.core.error_handling import PermanentError, RetryableError
from app.services.asset_service import AssetService
from app.services.visual_providers.base import SceneVisualResult


class TestAssetService:
    @patch("app.services.asset_service.requests.get")
    @patch("app.services.asset_service.settings")
    def test_download_image_success(self, mock_settings, mock_get):
        mock_settings.LOCAL_STORAGE_PATH = "/tmp/imdb_video_storage_test"
        response = Mock()
        response.headers = {"content-type": "image/jpeg"}
        response.content = b"image-bytes"
        response.raise_for_status = Mock()
        mock_get.return_value = response

        path = AssetService._download_image("https://example.com/poster.jpg", "poster_test")
        assert path.endswith("poster_test.jpg")
        assert Path(path).exists()
        Path(path).unlink(missing_ok=True)

    @patch("app.services.asset_service.requests.get")
    def test_download_image_invalid_content_type(self, mock_get):
        response = Mock()
        response.headers = {"content-type": "text/html"}
        response.content = b"html"
        response.raise_for_status = Mock()
        mock_get.return_value = response

        with pytest.raises(PermanentError):
            AssetService._download_image("https://example.com/page", "bad_content")

    @patch("app.services.asset_service.requests.get")
    def test_download_image_timeout(self, mock_get):
        import requests

        mock_get.side_effect = requests.Timeout("timeout")
        with pytest.raises(RetryableError):
            AssetService._download_image("https://example.com/poster.jpg", "timeout")

    @patch("app.services.asset_service.settings")
    def test_gather_assets_with_placeholder(self, mock_settings):
        mock_settings.LOCAL_STORAGE_PATH = "/tmp/imdb_video_storage_test"
        mock_settings.VISUAL_PROVIDER = "scene_card"
        mock_settings.AI_IMAGE_PROVIDER = "local_comfyui"
        out = AssetService.gather_assets(
            {"poster_url": None, "trailer_url": None},
            ["scene1", "scene2"],
            "job-assets-1",
        )
        assert len(out["scene_backgrounds"]) == 2
        assert out["scene_backgrounds"][0].endswith(".svg")
        assert out["visual_strategy"] == "generated_scene_card"
        assert len(set(out["scene_backgrounds"])) == 2
        assert all(asset["source_type"] == "generated_scene_card" for asset in out["scene_assets"])

    @patch("app.services.asset_service.settings")
    @patch("app.services.asset_service.AssetService._download_image")
    def test_gather_assets_uses_poster_as_reference_not_repeated_background(
        self,
        mock_download,
        mock_settings,
    ):
        mock_settings.LOCAL_STORAGE_PATH = "/tmp/imdb_video_storage_test"
        mock_settings.VISUAL_PROVIDER = "scene_card"
        mock_settings.AI_IMAGE_PROVIDER = "local_comfyui"
        mock_download.return_value = "/tmp/poster.jpg"

        out = AssetService.gather_assets(
            {"poster_url": "https://example.com/poster.jpg", "trailer_url": None, "title": "Test Movie"},
            ["first scene", "second scene"],
            "job-assets-2",
        )

        assert out["poster_path"] == "/tmp/poster.jpg"
        assert out["scene_backgrounds"][0].endswith("job-assets-2_scene_1.svg")
        assert out["scene_backgrounds"][1].endswith("job-assets-2_scene_2.svg")
        assert len(set(out["scene_backgrounds"])) == 2
        assert all(asset["reference_poster_path"] == "/tmp/poster.jpg" for asset in out["scene_assets"])

    @patch("app.services.asset_service.settings")
    @patch("app.services.asset_service.ComfyUIVisualProvider")
    def test_gather_assets_can_use_local_comfyui_provider(self, mock_provider_cls, mock_settings):
        mock_settings.LOCAL_STORAGE_PATH = "/tmp/imdb_video_storage_test"
        mock_settings.VISUAL_PROVIDER = "ai_image"
        mock_settings.AI_IMAGE_PROVIDER = "local_comfyui"
        provider = Mock()
        provider.source_type = "stable_diffusion_comfyui"
        provider.generate_scene_visual.side_effect = [
            SceneVisualResult(path="/tmp/scene-1.png", source_type="stable_diffusion_comfyui", prompt="p1"),
            SceneVisualResult(path="/tmp/scene-2.png", source_type="stable_diffusion_comfyui", prompt="p2"),
        ]
        mock_provider_cls.return_value = provider

        out = AssetService.gather_assets(
            {"poster_url": None, "trailer_url": None, "title": "Test Movie"},
            ["first scene", "second scene"],
            "job-assets-3",
        )

        assert out["visual_strategy"] == "stable_diffusion_comfyui"
        assert out["scene_backgrounds"] == ["/tmp/scene-1.png", "/tmp/scene-2.png"]
        assert all(asset["source_type"] == "stable_diffusion_comfyui" for asset in out["scene_assets"])

    @patch("app.services.asset_service.settings")
    @patch("app.services.asset_service.ComfyUIVisualProvider")
    def test_gather_assets_falls_back_when_comfyui_fails(self, mock_provider_cls, mock_settings):
        mock_settings.LOCAL_STORAGE_PATH = "/tmp/imdb_video_storage_test"
        mock_settings.VISUAL_PROVIDER = "ai_image"
        mock_settings.AI_IMAGE_PROVIDER = "local_comfyui"
        provider = Mock()
        provider.source_type = "stable_diffusion_comfyui"
        provider.generate_scene_visual.side_effect = RetryableError("comfyui unavailable")
        mock_provider_cls.return_value = provider

        out = AssetService.gather_assets(
            {"poster_url": None, "trailer_url": None, "title": "Test Movie"},
            ["first scene"],
            "job-assets-4",
        )

        assert out["visual_strategy"] == "stable_diffusion_comfyui_with_scene_card_fallback"
        assert out["scene_backgrounds"][0].endswith(".svg")
        assert out["scene_assets"][0]["source_type"] == "generated_scene_card"
