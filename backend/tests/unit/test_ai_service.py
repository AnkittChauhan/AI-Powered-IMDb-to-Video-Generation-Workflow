"""Unit tests for AIService."""

from unittest.mock import patch

import pytest

from app.core.error_handling import PermanentError
from app.services.ai_service import AIService


class TestAIService:
    def test_generate_script_requires_title(self):
        with pytest.raises(PermanentError):
            AIService.generate_script({"plot": "Some plot text"})

    def test_generate_script_requires_plot(self):
        with pytest.raises(PermanentError):
            AIService.generate_script({"title": "Movie"})

    @patch("app.services.ai_service.AIService._call_openai")
    def test_generate_script_success(self, mock_call):
        mock_call.return_value = (
            "Scene 1: Opening.\n\nScene 2: Conflict.\n\nScene 3: Resolution.",
            {"prompt_tokens": 100, "completion_tokens": 250, "total_tokens": 350},
        )
        output = AIService.generate_script(
            {
                "title": "Demo Movie",
                "plot": "A long story about growth and sacrifice.",
                "genres": ["Drama"],
                "cast": ["Actor A", "Actor B"],
                "runtime_minutes": 120,
            }
        )
        assert output["script_text"]
        assert len(output["scenes"]) >= 1
        assert output["usage"]["total_tokens"] == 350
        assert output["cost_usd"] > 0

    def test_split_script_into_scenes_with_scene_headers(self):
        script = "Scene 1: A\n\nScene 2: B\n\nScene 3: C"
        scenes = AIService.split_script_into_scenes(script, target_scenes=8)
        assert scenes == ["A", "B", "C"]

    def test_split_script_into_scenes_with_paragraphs(self):
        script = "Para 1.\n\nPara 2.\n\nPara 3."
        scenes = AIService.split_script_into_scenes(script, target_scenes=8)
        assert len(scenes) == 3

    def test_calculate_cost(self):
        assert AIService.calculate_cost(0) == 0.0
        assert AIService.calculate_cost(1000) > 0.0
