"""Stage 5: Video composition task."""

from datetime import datetime

from celery import shared_task
from celery.utils.log import get_task_logger

from app.core.error_handling import PermanentError, RetryableError
from app.core.job_coordinator import JobCoordinator
from app.database.connection import SessionLocal
from app.models.job import JobExecutionLog, Metadata
from app.services.video_service import VideoService
from app.utils.constants import STAGE_RETRY_LIMITS

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    queue="video",
    time_limit=20 * 60,
    soft_time_limit=18 * 60,
    max_retries=STAGE_RETRY_LIMITS.get("video_composition", 1),
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def compose_video_task(self, job_id: str):
    """Compose visuals, subtitles, and voiceover into a draft MP4."""
    db = SessionLocal()
    started_at = datetime.utcnow()
    try:
        coordinator = JobCoordinator(db)
        try:
            job = coordinator._get_job(job_id)
        except ValueError as e:
            raise PermanentError(str(e))

        if not job.metadata_id:
            raise PermanentError(f"[{job_id}] metadata_id missing before video composition")

        metadata = db.query(Metadata).filter(Metadata.id == job.metadata_id).first()
        if not metadata:
            raise PermanentError(f"[{job_id}] Metadata row not found for metadata_id={job.metadata_id}")

        extra = metadata.extra_data or {}
        voiceover = extra.get("voiceover") or {}
        assets = extra.get("assets") or {}
        subtitles = extra.get("subtitles") or []

        audio_path = voiceover.get("audio_path")
        duration_seconds = float(voiceover.get("duration_seconds") or 0)
        if duration_seconds <= 0 and subtitles:
            duration_seconds = float(subtitles[-1].get("end") or 0)

        composition_output = VideoService.compose_video(
            job_id=job_id,
            scene_backgrounds=assets.get("scene_backgrounds") or [],
            audio_path=audio_path,
            subtitles=subtitles,
            duration_seconds=duration_seconds,
        )

        metadata.extra_data = {
            **extra,
            "composition": {
                **composition_output,
                "generated_at": datetime.utcnow().isoformat(),
            },
        }
        db.commit()

        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        db.add(
            JobExecutionLog(
                job_id=job_id,
                stage="video_composition",
                status="success",
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=duration_ms,
            )
        )
        db.commit()

        coordinator.transition_to_next_stage(job_id)
        logger.info(f"[{job_id}] Video composition completed")
        return {
            "status": "success",
            "job_id": job_id,
            "draft_video_path": composition_output["draft_video_path"],
        }

    except PermanentError as e:
        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        db.add(
            JobExecutionLog(
                job_id=job_id,
                stage="video_composition",
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
            logger.exception(f"[{job_id}] Failed to mark permanent video failure")
        raise
    except RetryableError:
        raise
    except Exception as e:
        raise RetryableError(str(e))
    finally:
        db.close()


__all__ = ["compose_video_task"]
