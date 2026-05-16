"""
Stage 1: Metadata Extraction Task

This task:
1. Fetches movie metadata from IMDb
2. Extracts: title, plot, genre, cast, ratings, poster/images
3. Stores in database cache
4. Transitions job to next stage (SCRIPT_GENERATION)
5. Enqueues script generation task

Error Handling:
- Network timeouts: RetryableError → retry with backoff
- Invalid IMDb URL: PermanentError → fail fast
- Rate limits: RetryableError → retry with backoff
"""
from celery import shared_task
from celery.utils.log import get_task_logger
from app.core.error_handling import RetryableError, PermanentError
from app.utils.constants import STAGE_RETRY_LIMITS

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
def extract_metadata_task(self, job_id: str, imdb_url: str):
    """
    Extract IMDb metadata for a movie.
    
    Args:
        job_id: Unique job identifier
        imdb_url: IMDb movie URL (e.g., https://www.imdb.com/title/tt0111161/)
    
    Returns:
        dict: {"status": "success", "job_id": job_id, "metadata": {...}}
    
    Raises:
        RetryableError: Network errors, rate limits, temporary failures
        PermanentError: Invalid URL, movie not found, auth failures
    """
    logger.info(f"[{job_id}] Starting metadata extraction from {imdb_url}")
    
    try:
        # TODO: Implement in Chunk 2 (MetadataService)
        # from app.services.metadata_service import MetadataService
        # from app.core.job_coordinator import JobCoordinator
        # from app.database.connection import get_db
        #
        # db = next(get_db())
        # coordinator = JobCoordinator(db)
        #
        # # Extract metadata (handles retryable errors)
        # metadata = MetadataService.fetch_imdb(imdb_url)
        #
        # # Store in database
        # coordinator.store_metadata(job_id, metadata)
        #
        # # Transition to next stage
        # coordinator.transition_to_next_stage(job_id)
        #
        # # Enqueue next task
        # from app.tasks.script_tasks import generate_script_task
        # generate_script_task.apply_async(
        #     args=(job_id,),
        #     queue="script"
        # )
        #
        # logger.info(f"[{job_id}] Metadata extraction completed")
        # return {"status": "success", "job_id": job_id, "metadata": metadata}
        
        # Placeholder for now
        logger.info(f"[{job_id}] Metadata extraction placeholder")
        return {"status": "success", "job_id": job_id}
    
    except PermanentError as e:
        logger.error(f"[{job_id}] Permanent error in metadata extraction: {str(e)}")
        # Don't retry permanent errors
        raise
    
    except RetryableError as e:
        logger.warning(
            f"[{job_id}] Retryable error in metadata extraction "
            f"(attempt {self.request.retries}/{self.max_retries}): {str(e)}"
        )
        # Celery will automatically retry with backoff
        raise self.retry(exc=e)
    
    except Exception as e:
        logger.error(f"[{job_id}] Unexpected error in metadata extraction: {str(e)}")
        # Re-raise as retryable to allow recovery
        raise self.retry(exc=RetryableError(str(e)))


__all__ = ["extract_metadata_task"]
