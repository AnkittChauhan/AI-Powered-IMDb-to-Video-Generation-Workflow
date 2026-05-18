"""Unit tests for video composition task."""

from unittest.mock import Mock, patch

from sqlalchemy.orm import Session

from app.models.job import Job, Metadata
from app.tasks.video_tasks import compose_video_task


class TestVideoTask:
    @patch("app.tasks.video_tasks.SessionLocal")
    @patch("app.tasks.video_tasks.VideoService.compose_video")
    @patch("app.tasks.video_tasks.JobCoordinator")
    def test_compose_video_success(self, mock_coord_cls, mock_compose, mock_session_local):
        db = Mock(spec=Session)
        mock_session_local.return_value = db

        job = Mock(spec=Job)
        job.id = "job-video-task-1"
        job.metadata_id = "meta-1"

        metadata = Mock(spec=Metadata)
        metadata.extra_data = {
            "voiceover": {"audio_path": "/tmp/audio.mp3", "duration_seconds": 4.0},
            "subtitles": [{"index": 1, "start": 0.0, "end": 4.0, "text": "Intro"}],
            "assets": {"scene_backgrounds": ["/tmp/bg.jpg"]},
        }

        coordinator = Mock()
        coordinator._get_job.return_value = job
        mock_coord_cls.return_value = coordinator
        db.query.return_value.filter.return_value.first.return_value = metadata
        mock_compose.return_value = {
            "draft_video_path": "/tmp/draft.mp4",
            "subtitles_path": "/tmp/subtitles.srt",
            "duration_seconds": 4.0,
            "scene_count": 1,
        }

        result = compose_video_task.run(job_id="job-video-task-1")

        assert result["status"] == "success"
        assert metadata.extra_data["composition"]["draft_video_path"] == "/tmp/draft.mp4"
        coordinator.transition_to_next_stage.assert_called_once_with("job-video-task-1")
