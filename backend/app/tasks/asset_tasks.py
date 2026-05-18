"""Stage 4: Asset gathering task."""

from datetime import datetime
from celery import shared_task
from celery.utils.log import get_task_logger

from app.core.error_handling import PermanentError, RetryableError
from app.core.job_coordinator import JobCoordinator
from app.database.connection import SessionLocal
from app.models.job import JobExecutionLog, Metadata
from app.services.asset_service import AssetService
from app.utils.constants import STAGE_RETRY_LIMITS

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    queue="assets",
    time_limit=10 * 60,
    soft_time_limit=8 * 60,
    max_retries=STAGE_RETRY_LIMITS.get("asset_gathering", 2),
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def gather_assets_task(self, job_id: str):
    """Gather assets for each storyboard scene."""
    db = SessionLocal()
    started_at = datetime.utcnow()
    try:
        coordinator = JobCoordinator(db)
        try:
            job = coordinator._get_job(job_id)
        except ValueError as e:
            raise PermanentError(str(e))

        if not job.metadata_id:
            raise PermanentError(f"[{job_id}] metadata_id missing before asset stage")

        metadata = db.query(Metadata).filter(Metadata.id == job.metadata_id).first()
        if not metadata:
            raise PermanentError(f"[{job_id}] Metadata row not found for metadata_id={job.metadata_id}")

        extra = metadata.extra_data or {}
        scenes = extra.get("storyboard_scenes") or []
        script = extra.get("generated_script") or ""
        if not scenes and script:
            scenes = [p.strip() for p in script.split("\n\n") if p.strip()]

        movie_metadata = {
            "poster_url": metadata.poster_url,
            "trailer_url": metadata.trailer_url,
            "title": metadata.title,
            "genres": metadata.genres or [],
        }
        assets_output = AssetService.gather_assets(movie_metadata, scenes, job_id)

        metadata.extra_data = {
            **extra,
            "assets": assets_output,
        }
        db.commit()

        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        db.add(
            JobExecutionLog(
                job_id=job_id,
                stage="asset_gathering",
                status="success",
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=duration_ms,
            )
        )
        db.commit()

        coordinator.transition_to_next_stage(job_id)
        logger.info(f"[{job_id}] Asset gathering completed")

        return {
            "status": "success",
            "job_id": job_id,
            "assets_count": len(assets_output.get("scene_backgrounds", [])),
        }
    except PermanentError as e:
        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        db.add(
            JobExecutionLog(
                job_id=job_id,
                stage="asset_gathering",
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
            logger.exception(f"[{job_id}] Failed to mark permanent asset failure")
        raise
    except RetryableError:
        raise
    except Exception as e:
        raise RetryableError(str(e))
    finally:
        db.close()


__all__ = ["gather_assets_task"]
