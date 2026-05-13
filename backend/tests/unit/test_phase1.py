"""
Unit tests for Phase 1: Core API & Job Management

Tests cover:
1. JobCoordinator state machine transitions
2. Error handling and retry logic
3. API route validation and error responses
4. Input validation
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from unittest.mock import Mock, patch

# Database setup for testing (in-memory SQLite)
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    """Provide a test database session"""
    from app.models.job import Base
    
    Base.metadata.create_all(bind=engine)
    db_session = TestingSessionLocal()
    yield db_session
    db_session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def coordinator(db):
    """Provide a JobCoordinator instance"""
    from app.core.job_coordinator import JobCoordinator
    return JobCoordinator(db)


@pytest.fixture
def sample_job(db):
    """Create a sample job in database"""
    from app.models.job import Job
    from app.core.job_coordinator import JobStage
    
    job = Job(
        id="test-job-1",
        imdb_url="https://www.imdb.com/title/tt0111161/",
        status=JobStage.PENDING.value,
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    return job


# ===== JobCoordinator Tests =====

class TestJobCoordinator:
    """Tests for JobCoordinator state machine"""
    
    def test_get_current_stage(self, coordinator, sample_job):
        """Test getting current stage of a job"""
        from app.core.job_coordinator import JobStage
        
        stage = coordinator.get_current_stage(sample_job.id)
        assert stage == JobStage.PENDING
    
    def test_get_next_stage(self, coordinator, sample_job, db):
        """Test determining the next stage"""
        from app.core.job_coordinator import JobStage
        from app.models.job import Job
        
        # From pending, next should be metadata_extraction
        next_stage = coordinator.get_next_stage(sample_job.id)
        assert next_stage == JobStage.METADATA_EXTRACTION
        
        # Update job to script_generation
        job = db.query(Job).filter(Job.id == sample_job.id).first()
        job.status = JobStage.SCRIPT_GENERATION.value
        db.commit()
        
        # Next should be tts_subtitles
        next_stage = coordinator.get_next_stage(sample_job.id)
        assert next_stage == JobStage.TTS_SUBTITLES
    
    def test_no_next_stage_when_completed(self, coordinator, sample_job, db):
        """Test that completed jobs have no next stage"""
        from app.core.job_coordinator import JobStage
        from app.models.job import Job
        
        # Mark job as completed
        job = db.query(Job).filter(Job.id == sample_job.id).first()
        job.status = JobStage.COMPLETED.value
        db.commit()
        
        next_stage = coordinator.get_next_stage(sample_job.id)
        assert next_stage is None
    
    def test_transition_to_next_stage(self, coordinator, sample_job, db):
        """Test transitioning to next stage"""
        from app.core.job_coordinator import JobStage
        from app.models.job import Job
        
        success = coordinator.transition_to_next_stage(sample_job.id)
        assert success is True
        
        # Verify job was updated
        job = db.query(Job).filter(Job.id == sample_job.id).first()
        assert job.status == JobStage.METADATA_EXTRACTION.value
    
    def test_job_not_found(self, coordinator):
        """Test error when job doesn't exist"""
        with pytest.raises(ValueError):
            coordinator.get_current_stage("nonexistent-job")
    
    def test_get_job_progress(self, coordinator, sample_job):
        """Test getting job progress"""
        progress = coordinator.get_job_progress(sample_job.id)
        
        assert progress["job_id"] == sample_job.id
        assert progress["status"] == "pending"
        assert progress["overall_progress"] == 0
        assert progress["current_stage"] == "pending"
    
    def test_progress_calculation(self, coordinator, sample_job, db):
        """Test progress percentage calculation"""
        from app.models.job import Job
        
        test_cases = [
            ("pending", 0),
            ("metadata_extraction", 10),
            ("script_generation", 30),
            ("tts_subtitles", 50),
            ("asset_gathering", 65),
            ("video_composition", 80),
            ("export", 95),
            ("completed", 100),
        ]
        
        for status, expected_progress in test_cases:
            job = db.query(Job).filter(Job.id == sample_job.id).first()
            job.status = status
            db.commit()
            
            progress = coordinator.get_job_progress(sample_job.id)
            assert progress["overall_progress"] == expected_progress


# ===== Error Handling Tests =====

class TestErrorHandling:
    """Tests for error handling and retry logic"""
    
    def test_retryable_error_classification(self):
        """Test classification of retryable errors"""
        from app.core.error_handling import (
            RetryableError,
            PermanentError,
            NetworkTimeoutError,
            RateLimitError,
        )
        
        # Retryable errors
        error1 = NetworkTimeoutError("Request timed out")
        assert isinstance(error1, RetryableError)
        
        error2 = RateLimitError("OpenAI", retry_after_seconds=60)
        assert isinstance(error2, RetryableError)
        assert error2.retry_after_seconds == 60
    
    def test_permanent_error_classification(self):
        """Test classification of permanent errors"""
        from app.core.error_handling import (
            PermanentError,
            InvalidInputError,
            FileNotFoundError,
        )
        
        # Permanent errors
        error1 = InvalidInputError("url", "Invalid format")
        assert isinstance(error1, PermanentError)
        
        error2 = FileNotFoundError("/path/to/file")
        assert isinstance(error2, PermanentError)
    
    def test_input_validator_imdb_url(self):
        """Test IMDb URL validation"""
        from app.core.error_handling import InputValidator, InvalidInputError
        
        # Valid URLs
        assert InputValidator.validate_imdb_url("https://www.imdb.com/title/tt0111161/")
        assert InputValidator.validate_imdb_url("https://www.imdb.com/title/tt0111161")
        
        # Invalid URLs
        with pytest.raises(InvalidInputError):
            InputValidator.validate_imdb_url("https://www.imdb.com/invalid")
        
        with pytest.raises(InvalidInputError):
            InputValidator.validate_imdb_url("http://www.imdb.com/title/tt0111161/")
    
    def test_extract_imdb_id(self):
        """Test extracting IMDb ID from URL"""
        from app.core.error_handling import InputValidator
        
        imdb_id = InputValidator.extract_imdb_id("https://www.imdb.com/title/tt0111161/")
        assert imdb_id == "tt0111161"
    
    def test_handle_failure_with_retry(self, coordinator, sample_job, db):
        """Test failure handling with retry"""
        from app.models.job import Job
        
        # First failure - should retry
        success = coordinator.handle_failure(
            sample_job.id,
            "Temporary error",
            should_retry=True,
        )
        assert success is True  # Will retry
        
        # Check retry count incremented
        job = db.query(Job).filter(Job.id == sample_job.id).first()
        assert job.retry_count == 1
    
    def test_handle_failure_max_retries(self, coordinator, sample_job, db):
        """Test failure handling when max retries exceeded"""
        from app.models.job import Job
        from app.core.job_coordinator import JobStage
        
        # Simulate max retries
        job = db.query(Job).filter(Job.id == sample_job.id).first()
        job.retry_count = 3  # Max for metadata_extraction
        db.commit()
        
        # This failure should mark job as failed
        success = coordinator.handle_failure(
            sample_job.id,
            "Max retries exceeded",
            should_retry=True,
        )
        assert success is False  # Won't retry
        
        # Check job marked as failed
        job = db.query(Job).filter(Job.id == sample_job.id).first()
        assert job.status == JobStage.FAILED.value


# ===== API Route Tests =====

class TestJobRoutes:
    """Tests for API routes"""
    
    @pytest.fixture
    def client(self):
        """Provide FastAPI test client"""
        from fastapi.testclient import TestClient
        from app.main import app
        
        # Override database dependency
        def override_get_db():
            db_session = TestingSessionLocal()
            try:
                yield db_session
            finally:
                db_session.close()
        
        from app.database.connection import get_db
        app.dependency_overrides[get_db] = override_get_db
        
        return TestClient(app)
    
    def test_submit_valid_job(self, client):
        """Test submitting a valid job"""
        response = client.post(
            "/api/jobs",
            json={"imdb_url": "https://www.imdb.com/title/tt0111161/"}
        )
        
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert "poll_url" in data
    
    def test_submit_invalid_url(self, client):
        """Test submitting invalid IMDb URL"""
        response = client.post(
            "/api/jobs",
            json={"imdb_url": "https://invalid.com"}
        )
        
        assert response.status_code == 400
    
    def test_submit_job_without_url(self, client):
        """Test submitting job without URL"""
        response = client.post(
            "/api/jobs",
            json={}
        )
        
        assert response.status_code in (400, 422)
    
    def test_get_nonexistent_job(self, client):
        """Test getting status for nonexistent job"""
        response = client.get("/api/jobs/nonexistent-job-id")
        assert response.status_code == 404
    
    def test_get_job_status(self, client, sample_job):
        """Test getting job status"""
        response = client.get(f"/api/jobs/{sample_job.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == sample_job.id
        assert data["status"] == "pending"
        assert "progress" in data
    
    def test_download_incomplete_job(self, client, sample_job):
        """Test downloading video for incomplete job"""
        response = client.get(f"/api/jobs/{sample_job.id}/video")
        
        assert response.status_code == 400
    
    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "services" in data


# ===== Integration Tests =====

class TestJobWorkflow:
    """End-to-end job workflow tests"""
    
    def test_job_creation_and_polling(self, db, coordinator):
        """Test creating job and polling status"""
        from app.models.job import Job
        from app.core.job_coordinator import JobStage
        
        # Create job
        job = Job(
            id="e2e-test-1",
            imdb_url="https://www.imdb.com/title/tt0111161/",
            status=JobStage.PENDING.value,
            created_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        
        # Get progress (should be pending)
        progress = coordinator.get_job_progress(job.id)
        assert progress["overall_progress"] == 0
        
        # Transition to next stage
        coordinator.transition_to_next_stage(job.id)
        
        # Get progress again (should be 10%)
        progress = coordinator.get_job_progress(job.id)
        assert progress["overall_progress"] == 10
        assert progress["status"] == JobStage.METADATA_EXTRACTION.value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
