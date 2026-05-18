"""
Stage 2: Script Generation Task

Placeholder for now. Will be implemented in Chunk 3 (AIService).

This task will:
1. Fetch metadata
2. Call OpenAI API to generate script
3. Parse script into scenes
4. Store script in database
5. Transition to next stage (TTS)
"""
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    queue="script",
    time_limit=15 * 60,  # 15 minutes hard limit
    soft_time_limit=12 * 60,  # 12 minutes soft limit
)
def generate_script_task(self, job_id: str):
    """
    Placeholder for script generation.
    
    To be implemented in Chunk 3.
    """
    logger.info(f"[{job_id}] Script generation placeholder")
    return {"status": "placeholder", "job_id": job_id}


__all__ = ["generate_script_task"]
