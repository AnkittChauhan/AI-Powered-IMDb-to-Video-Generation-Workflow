"""
Tests for metadata_tasks.py

Tests task execution with mocked services.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.orm import Session

from app.tasks.metadata_tasks import extract_metadata_task
from app.core.error_handling import RetryableError, PermanentError
from app.models.job import Job


class TestMetadataExtractionTask:
    """Test metadata extraction task execution"""
    
    @patch("app.tasks.metadata_tasks.SessionLocal")
    @patch("app.tasks.metadata_tasks.MetadataService.fetch_imdb")
    @patch("app.tasks.metadata_tasks.JobCoordinator")
    def test_extract_metadata_success(self, mock_coordinator_class, mock_fetch, mock_session_local):
        """Successfully extract and cache metadata"""
        # Setup mocks
        db = Mock(spec=Session)
        mock_session_local.return_value = db
        
        job = Mock(spec=Job)
        job.id = "test-job-id"
        job.status = "pending"
        
        mock_coordinator = Mock()
        mock_coordinator._get_job.return_value = job
        mock_coordinator_class.return_value = mock_coordinator
        
        mock_fetch.return_value = {
            "imdb_id": "tt0111161",
            "title": "The Shawshank Redemption",
            "plot": "Two imprisoned men...",
            "rating": 9.3,
        }
        
        # Execute task
        task = Mock()
        task.request.retries = 0
        task.max_retries = 3
        
        result = extract_metadata_task.run(
            task,
            job_id="test-job-id",
            imdb_url="https://www.imdb.com/title/tt0111161/"
        )
        
        # Assertions
        assert result["status"] == "success"
        assert result["imdb_id"] == "tt0111161"
        assert result["title"] == "The Shawshank Redemption"
        
        # Verify calls
        mock_coordinator._get_job.assert_called_once_with("test-job-id")
        mock_fetch.assert_called_once()
        mock_coordinator.transition_to_next_stage.assert_called_once()
    
    @patch("app.tasks.metadata_tasks.SessionLocal")
    @patch("app.tasks.metadata_tasks.MetadataService.fetch_imdb")
    @patch("app.tasks.metadata_tasks.JobCoordinator")
    def test_extract_metadata_permanent_error_no_retry(self, mock_coordinator_class, mock_fetch, mock_session_local):
        """Permanent error should not retry"""
        db = Mock(spec=Session)
        mock_session_local.return_value = db
        
        job = Mock(spec=Job)
        job.id = "test-job-id"
        
        mock_coordinator = Mock()
        mock_coordinator._get_job.return_value = job
        mock_coordinator_class.return_value = mock_coordinator
        
        # Simulate permanent error
        mock_fetch.side_effect = PermanentError("Invalid IMDb URL")
        
        task = Mock()
        task.request.retries = 0
        task.max_retries = 3
        task.retry.side_effect = Exception("Should not retry")
        
        # Execute - should raise and NOT call retry()
        with pytest.raises(PermanentError):
            extract_metadata_task.run(
                task,
                job_id="test-job-id",
                imdb_url="invalid-url"
            )
        
        # Verify job was marked as failed
        mock_coordinator.handle_failure.assert_called_once()
        # Verify retry was NOT called
        task.retry.assert_not_called()
    
    @patch("app.tasks.metadata_tasks.SessionLocal")
    @patch("app.tasks.metadata_tasks.MetadataService.fetch_imdb")
    @patch("app.tasks.metadata_tasks.JobCoordinator")
    def test_extract_metadata_retryable_error_retries(self, mock_coordinator_class, mock_fetch, mock_session_local):
        """Retryable error should retry with backoff"""
        db = Mock(spec=Session)
        mock_session_local.return_value = db
        
        job = Mock(spec=Job)
        job.id = "test-job-id"
        
        mock_coordinator = Mock()
        mock_coordinator._get_job.return_value = job
        mock_coordinator_class.return_value = mock_coordinator
        
        # Simulate retryable error
        mock_fetch.side_effect = RetryableError("Network timeout")
        
        task = Mock()
        task.request.retries = 0
        task.max_retries = 3
        task.retry.side_effect = RetryableError("Retry called")  # Simulate Celery retry
        
        # Execute - should raise and call retry()
        with pytest.raises(RetryableError):
            extract_metadata_task.run(
                task,
                job_id="test-job-id",
                imdb_url="https://www.imdb.com/title/tt0111161/"
            )
        
        # Verify retry was called
        task.retry.assert_called_once()
    
    @patch("app.tasks.metadata_tasks.SessionLocal")
    @patch("app.tasks.metadata_tasks.JobCoordinator")
    def test_extract_metadata_job_not_found(self, mock_coordinator_class, mock_session_local):
        """Handle job not found error"""
        db = Mock(spec=Session)
        mock_session_local.return_value = db
        
        mock_coordinator = Mock()
        mock_coordinator._get_job.return_value = None  # Job not found
        mock_coordinator_class.return_value = mock_coordinator
        
        task = Mock()
        task.request.retries = 0
        task.max_retries = 3
        
        # Execute - should raise PermanentError
        with pytest.raises(PermanentError) as exc_info:
            extract_metadata_task.run(
                task,
                job_id="nonexistent-job",
                imdb_url="https://www.imdb.com/title/tt0111161/"
            )
        
        assert "Job not found" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
