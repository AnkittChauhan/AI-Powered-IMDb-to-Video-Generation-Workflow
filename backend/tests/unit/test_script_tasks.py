"""Unit tests for script generation task."""

from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.error_handling import PermanentError, RetryableError
from app.models.job import Job, Metadata
from app.tasks.script_tasks import generate_script_task


class TestScriptTask:
    @patch("app.tasks.script_tasks.SessionLocal")
    @patch("app.tasks.script_tasks.AIService.generate_script")
    @patch("app.tasks.script_tasks.JobCoordinator")
    def test_generate_script_success(self, mock_coord_cls, mock_generate, mock_session_local):
        db = Mock(spec=Session)
        mock_session_local.return_value = db

        job = Mock(spec=Job)
        job.id = "job-1"
        job.metadata_id = "meta-1"
        job.status = "script_generation"

        metadata = Mock(spec=Metadata)
        metadata.title = "Demo"
        metadata.plot = "Some plot"
        metadata.genres = ["Drama"]
        metadata.cast = ["Actor A"]
        metadata.runtime_minutes = 120
        metadata.extra_data = {}

        coordinator = Mock()
        coordinator._get_job.return_value = job
        mock_coord_cls.return_value = coordinator

        db.query.return_value.filter.return_value.first.return_value = metadata
        mock_generate.return_value = {
            "script_text": "Scene 1: Intro",
            "scenes": ["Intro"],
            "usage": {"total_tokens": 300},
            "cost_usd": 0.0006,
        }

        result = generate_script_task.run(job_id="job-1")
        assert result["status"] == "success"
        assert result["scenes"] == 1
        coordinator.transition_to_next_stage.assert_called_once_with("job-1")

    @patch("app.tasks.script_tasks.SessionLocal")
    @patch("app.tasks.script_tasks.JobCoordinator")
    def test_generate_script_missing_metadata_id(self, mock_coord_cls, mock_session_local):
        db = Mock(spec=Session)
        mock_session_local.return_value = db

        job = Mock(spec=Job)
        job.id = "job-1"
        job.metadata_id = None

        coordinator = Mock()
        coordinator._get_job.return_value = job
        mock_coord_cls.return_value = coordinator

        with pytest.raises(PermanentError):
            generate_script_task.run(job_id="job-1")

    @patch("app.tasks.script_tasks.SessionLocal")
    @patch("app.tasks.script_tasks.AIService.generate_script")
    @patch("app.tasks.script_tasks.JobCoordinator")
    def test_generate_script_retryable_error(self, mock_coord_cls, mock_generate, mock_session_local):
        db = Mock(spec=Session)
        mock_session_local.return_value = db

        job = Mock(spec=Job)
        job.id = "job-1"
        job.metadata_id = "meta-1"

        metadata = Mock(spec=Metadata)
        metadata.title = "Demo"
        metadata.plot = "Plot"
        metadata.genres = []
        metadata.cast = []
        metadata.runtime_minutes = 100
        metadata.extra_data = {}

        coordinator = Mock()
        coordinator._get_job.return_value = job
        mock_coord_cls.return_value = coordinator
        db.query.return_value.filter.return_value.first.return_value = metadata

        mock_generate.side_effect = RetryableError("OpenAI timeout")
        with pytest.raises(RetryableError):
            generate_script_task.run(job_id="job-1")
