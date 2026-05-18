"""Unit tests for TTS task."""

from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.error_handling import PermanentError, RetryableError
from app.models.job import Job, Metadata
from app.tasks.tts_tasks import generate_tts_task


class TestTTSTask:
    @patch("app.tasks.tts_tasks.SessionLocal")
    @patch("app.tasks.tts_tasks.TTSService.generate_voiceover")
    @patch("app.tasks.tts_tasks.JobCoordinator")
    def test_generate_tts_success(self, mock_coord_cls, mock_tts, mock_session_local):
        db = Mock(spec=Session)
        mock_session_local.return_value = db

        job = Mock(spec=Job)
        job.id = "job-tts-1"
        job.metadata_id = "meta-1"
        job.status = "tts_subtitles"

        metadata = Mock(spec=Metadata)
        metadata.extra_data = {"generated_script": "Scene 1: Intro.\n\nScene 2: End."}

        coordinator = Mock()
        coordinator._get_job.return_value = job
        mock_coord_cls.return_value = coordinator

        db.query.return_value.filter.return_value.first.return_value = metadata
        mock_tts.return_value = {
            "audio_path": "/tmp/audio.mp3",
            "subtitles": [{"index": 1, "start": 0.0, "end": 2.0, "text": "Intro"}],
            "duration_seconds": 2.0,
        }

        result = generate_tts_task.run(job_id="job-tts-1")
        assert result["status"] == "success"
        assert result["subtitle_count"] == 1
        coordinator.transition_to_next_stage.assert_called_once_with("job-tts-1")

    @patch("app.tasks.tts_tasks.SessionLocal")
    @patch("app.tasks.tts_tasks.JobCoordinator")
    def test_generate_tts_missing_script(self, mock_coord_cls, mock_session_local):
        db = Mock(spec=Session)
        mock_session_local.return_value = db

        job = Mock(spec=Job)
        job.id = "job-tts-2"
        job.metadata_id = "meta-2"

        metadata = Mock(spec=Metadata)
        metadata.extra_data = {}

        coordinator = Mock()
        coordinator._get_job.return_value = job
        mock_coord_cls.return_value = coordinator
        db.query.return_value.filter.return_value.first.return_value = metadata

        with pytest.raises(PermanentError):
            generate_tts_task.run(job_id="job-tts-2")

    @patch("app.tasks.tts_tasks.SessionLocal")
    @patch("app.tasks.tts_tasks.TTSService.generate_voiceover")
    @patch("app.tasks.tts_tasks.JobCoordinator")
    def test_generate_tts_retryable_error(self, mock_coord_cls, mock_tts, mock_session_local):
        db = Mock(spec=Session)
        mock_session_local.return_value = db

        job = Mock(spec=Job)
        job.id = "job-tts-3"
        job.metadata_id = "meta-3"

        metadata = Mock(spec=Metadata)
        metadata.extra_data = {"generated_script": "Scene 1: Intro."}

        coordinator = Mock()
        coordinator._get_job.return_value = job
        mock_coord_cls.return_value = coordinator
        db.query.return_value.filter.return_value.first.return_value = metadata
        mock_tts.side_effect = RetryableError("TTS provider timeout")

        with pytest.raises(RetryableError):
            generate_tts_task.run(job_id="job-tts-3")
