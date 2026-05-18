"""
Stage 1: Metadata Extraction Task

This task:
1. Validates IMDb URL
2. Fetches metadata from IMDb (or cache)
3. Stores in database
4. Transitions job to next stage (SCRIPT_GENERATION)
5. Enqueues script generation task

Error Handling:
- Network timeouts: RetryableError → retry with backoff
- Invalid IMDb URL: PermanentError → fail fast
- Rate limits: RetryableError → retry with backoff
- Movie not found: PermanentError → fail fast

Retry Strategy:
- Max retries: 3 (configured in constants)
- Exponential backoff: 2^attempt with jitter
- Only retries on RetryableError (network, timeouts, rate limits)
"""
from celery import shared_task
from celery.utils.log import get_task_logger

from app.core.error_handling import RetryableError, PermanentError
from app.core.job_coordinator import JobCoordinator
from app.services.metadata_service import MetadataService
from app.database.connection import SessionLocal
from app.utils.constants import STAGE_RETRY_LIMITS
from app.models.job import Metadata

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    queue="metadata",
    time_limit=5 * 60,  # 5 minutes hard limit
    soft_time_limit=4 * 60,  # 4 minutes soft limit
    max_retries=STAGE_RETRY_LIMITS.get("metadata_extraction", 3),
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_backoff_max=600,  # Max backoff 10 minutes
    retry_jitter=True,
)
def extract_metadata_task(self, job_id: str):
    """
    Extract IMDb metadata for a movie.
    
    Args:
        job_id: Unique job identifier
    
    Returns:
        dict: {
            "status": "success",
            "job_id": job_id,
            "imdb_id": "tt0111161",
            "title": "The Shawshank Redemption",
            ...
        }
    
    Raises:
        RetryableError: Network errors, rate limits, temporary failures
        PermanentError: Invalid URL, movie not found, auth failures
    """
    db = SessionLocal()
    try:
        logger.info(f"[{job_id}] Starting metadata extraction")
        
        # Get job from database
        coordinator = JobCoordinator(db)
        try:
            job = coordinator._get_job(job_id)
        except ValueError as e:
            raise PermanentError(str(e))

        imdb_url = job.imdb_url
        logger.info(f"[{job_id}] IMDb URL: {imdb_url}")
        
        logger.info(f"[{job_id}] Job found, status: {job.status}")
        
        # Fetch metadata (handles caching, error classification)
        try:
            metadata = MetadataService.fetch_imdb(imdb_url, db)
            logger.info(f"[{job_id}] Metadata fetched: {metadata['title']}")
        except PermanentError as e:
            logger.error(f"[{job_id}] Permanent error: {str(e)}")
            raise
        except RetryableError as e:
            logger.warning(f"[{job_id}] Retryable error: {str(e)}")
            raise
        
        # Update job with metadata reference
        imdb_id = metadata["imdb_id"]
        cached_metadata = db.query(Metadata).filter(Metadata.imdb_id == imdb_id).first()
        if cached_metadata:
            job.metadata_id = cached_metadata.id
        job.display_name = metadata["title"]
        db.commit()
        logger.info(f"[{job_id}] Job updated with metadata reference")
        
        # Transition to next stage (enqueues next task through coordinator)
        coordinator.transition_to_next_stage(job_id)
        logger.info(f"[{job_id}] Transitioned to next stage: {job.status}")
        
        return {
            "status": "success",
            "job_id": job_id,
            "imdb_id": imdb_id,
            "title": metadata["title"],
            "message": f"Metadata extracted for {metadata['title']}"
        }
    
    except PermanentError as e:
        # Permanent errors should not retry
        logger.error(f"[{job_id}] Permanent error in metadata extraction: {str(e)}")
        # Mark job as failed
        try:
            coordinator = JobCoordinator(db)
            coordinator.handle_failure(job_id, str(e), should_retry=False)
        except Exception as cleanup_error:
            logger.error(f"[{job_id}] Error marking job failed: {str(cleanup_error)}")
        raise
    
    except RetryableError as e:
        # Retryable errors - Celery will handle retry logic
        logger.warning(
            f"[{job_id}] Retryable error in metadata extraction "
            f"(attempt {self.request.retries}/{self.max_retries}): {str(e)}"
        )
        raise
    
    except Exception as e:
        logger.error(f"[{job_id}] Unexpected error in metadata extraction: {str(e)}")
        # Convert to retryable to allow recovery
        raise RetryableError(str(e))
    
    finally:
        db.close()


__all__ = ["extract_metadata_task"]
