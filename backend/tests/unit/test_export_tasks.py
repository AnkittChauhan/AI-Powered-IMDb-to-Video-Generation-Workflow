"""Unit tests for final export task."""

from unittest.mock import Mock, patch

from sqlalchemy.orm import Session

from app.models.job import Job, Metadata
from app.tasks.export_tasks import export_video_task


class TestExportTask:
    @patch("app.tasks.export_tasks.SessionLocal")
    @patch("app.tasks.export_tasks.ExportService.export_mp4")
    @patch("app.tasks.export_tasks.JobCoordinator")
    def test_export_video_success(self, mock_coord_cls, mock_export, mock_session_local):
        db = Mock(spec=Session)
        mock_session_local.return_value = db

        job = Mock(spec=Job)
        job.id = "job-export-task-1"
        job.metadata_id = "meta-1"
        job.output_video_path = None

        metadata = Mock(spec=Metadata)
        metadata.extra_data = {
            "composition": {"draft_video_path": "/tmp/draft.mp4"},
        }

        coordinator = Mock()
        coordinator._get_job.return_value = job
        mock_coord_cls.return_value = coordinator
        db.query.return_value.filter.return_value.first.return_value = metadata
        mock_export.return_value = {
            "final_video_path": "/tmp/final.mp4",
            "file_size_bytes": 123,
        }

        result = export_video_task.run(job_id="job-export-task-1")

        assert result["status"] == "success"
        assert job.output_video_path == "/tmp/final.mp4"
        assert metadata.extra_data["export"]["file_size_bytes"] == 123
        coordinator.transition_to_next_stage.assert_called_once_with("job-export-task-1")
