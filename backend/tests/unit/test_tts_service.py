"""Unit tests for TTSService."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.core.error_handling import PermanentError
from app.services.tts_service import TTSService


class TestTTSService:
    def test_generate_subtitles(self):
        script = "Scene one text.\n\nScene two text."
        subtitles = TTSService.generate_subtitles(script)
        assert len(subtitles) == 2
        assert subtitles[0]["index"] == 1
        assert subtitles[1]["start"] >= subtitles[0]["end"]

    @patch("app.services.tts_service.TTSService._call_openai_tts")
    @patch("app.services.tts_service.settings")
    def test_generate_voiceover_success(self, mock_settings, mock_call):
        mock_settings.LOCAL_STORAGE_PATH = "/tmp/imdb_video_storage_test"
        mock_call.return_value = b"fake-audio"
        output = TTSService.generate_voiceover("Narration text for testing.", "job-tts-1")
        assert output["audio_path"].endswith("job-tts-1_voiceover.mp3")
        assert Path(output["audio_path"]).exists()
        assert len(output["subtitles"]) >= 1
        Path(output["audio_path"]).unlink(missing_ok=True)

    def test_generate_voiceover_empty_script(self):
        with pytest.raises(PermanentError):
            TTSService.generate_voiceover("", "job-tts-2")
