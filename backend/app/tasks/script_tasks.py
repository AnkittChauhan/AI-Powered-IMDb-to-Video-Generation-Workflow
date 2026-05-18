"""Stage 2: Script generation task using AIService."""

from datetime import datetime
from celery import shared_task
from celery.utils.log import get_task_logger

from app.core.error_handling import PermanentError, RetryableError
from app.core.job_coordinator import JobCoordinator
from app.database.connection import SessionLocal
from app.models.job import JobExecutionLog, Metadata
from app.services.ai_service import AIService
from app.utils.constants import STAGE_RETRY_LIMITS

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    queue="script",
    time_limit=15 * 60,  # 15 minutes hard limit
    soft_time_limit=12 * 60,  # 12 minutes soft limit
    max_retries=STAGE_RETRY_LIMITS.get("script_generation", 5),
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def generate_script_task(self, job_id: str):
    """Generate narration script from cached metadata."""
    db = SessionLocal()
    started_at = datetime.utcnow()
    try:
        coordinator = JobCoordinator(db)
        try:
            job = coordinator._get_job(job_id)
        except ValueError as e:
            raise PermanentError(str(e))

        if not job.metadata_id:
            raise PermanentError(f"[{job_id}] metadata_id missing before script generation")

        metadata = db.query(Metadata).filter(Metadata.id == job.metadata_id).first()
        if not metadata:
            raise PermanentError(f"[{job_id}] Metadata row not found for metadata_id={job.metadata_id}")

        metadata_payload = {
            "title": metadata.title,
            "plot": metadata.plot,
            "genres": metadata.genres or [],
            "cast": metadata.cast or [],
            "runtime_minutes": metadata.runtime_minutes,
        }
        ai_output = AIService.generate_script(metadata_payload)

        existing_extra = metadata.extra_data or {}
        metadata.extra_data = {
            **existing_extra,
            "generated_script": ai_output["script_text"],
            "storyboard_scenes": ai_output["scenes"],
            "script_generation": {
                "model": "openai",
                "usage": ai_output["usage"],
                "cost_usd": ai_output["cost_usd"],
                "generated_at": datetime.utcnow().isoformat(),
            },
        }
        db.commit()

        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        db.add(
            JobExecutionLog(
                job_id=job_id,
                stage="script_generation",
                status="success",
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=duration_ms,
                tokens_used=ai_output["usage"].get("total_tokens"),
                api_call_cost_usd=ai_output["cost_usd"],
            )
        )
        db.commit()

        coordinator.transition_to_next_stage(job_id)
        logger.info(f"[{job_id}] Script generation completed")

        return {
            "status": "success",
            "job_id": job_id,
            "scenes": len(ai_output["scenes"]),
            "tokens_used": ai_output["usage"].get("total_tokens", 0),
            "cost_usd": ai_output["cost_usd"],
        }
    except PermanentError as e:
        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        db.add(
            JobExecutionLog(
                job_id=job_id,
                stage="script_generation",
                status="failed",
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=duration_ms,
                error_message=str(e),
            )
        )
        db.commit()
        try:
            JobCoordinator(db).handle_failure(job_id, str(e), should_retry=False)
        except Exception:
            logger.exception(f"[{job_id}] Failed to mark permanent script failure")
        raise
    except RetryableError:
        raise
    except Exception as e:
        raise RetryableError(str(e))
    finally:
        db.close()


__all__ = ["generate_script_task"]
