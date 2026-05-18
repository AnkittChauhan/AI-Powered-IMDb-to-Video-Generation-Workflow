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
