"""
Metadata extraction tasks (Stage 1)
"""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def extract_metadata_task(self, job_id: str, imdb_url: str):
    """
    Stage 1: Extract IMDb metadata.
    
    This task:
    1. Fetches movie data from IMDb
    2. Caches it in the database
    3. Enqueues the next task (script generation)
    """
    logger.info(f"Extracting metadata for job {job_id} from {imdb_url}")
    
    try:
        # TODO: Implement metadata extraction logic
        # from app.services.metadata_service import MetadataService
        # from app.core.job_coordinator import JobCoordinator
        # 
        # coordinator = JobCoordinator(db)
        # coordinator.transition_to_stage(job_id, JobStage.METADATA_EXTRACTION)
        # 
        # metadata = MetadataService.fetch_imdb(imdb_url)
        # coordinator.enqueue_next_task(job_id)
        
        return {"status": "success", "job_id": job_id}
    
    except Exception as e:
        logger.error(f"Metadata extraction failed for {job_id}: {str(e)}")
        raise self.retry(exc=e, countdown=5)
