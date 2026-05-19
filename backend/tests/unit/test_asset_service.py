"""Unit tests for AssetService."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.core.error_handling import PermanentError, RetryableError
from app.services.asset_service import AssetService


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
        out = AssetService.gather_assets(
            {"poster_url": None, "trailer_url": None},
            ["scene1", "scene2"],
            "job-assets-1",
        )
        assert len(out["scene_backgrounds"]) == 2
        assert out["scene_backgrounds"][0].endswith(".svg")
        assert out["visual_strategy"] == "generated_scene_cards"
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
        mock_download.return_value = "/tmp/poster.jpg"

        out = AssetService.gather_assets(
            {"poster_url": "https://example.com/poster.jpg", "trailer_url": None, "title": "Test Movie"},
            ["first scene", "second scene"],
            "job-assets-2",
        )

        assert out["poster_path"] == "/tmp/poster.jpg"
        assert out["scene_backgrounds"] == [
            "/tmp/imdb_video_storage_test/assets/placeholders/job-assets-2_scene_1.svg",
            "/tmp/imdb_video_storage_test/assets/placeholders/job-assets-2_scene_2.svg",
        ]
        assert all(asset["reference_poster_path"] == "/tmp/poster.jpg" for asset in out["scene_assets"])
