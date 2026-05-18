"""Stage 3: TTS + subtitle generation task."""

from datetime import datetime
from celery import shared_task
from celery.utils.log import get_task_logger

from app.core.error_handling import PermanentError, RetryableError
from app.core.job_coordinator import JobCoordinator
from app.database.connection import SessionLocal
from app.models.job import JobExecutionLog, Metadata
from app.services.tts_service import TTSService
from app.utils.constants import STAGE_RETRY_LIMITS

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    queue="tts",
    time_limit=10 * 60,
    soft_time_limit=8 * 60,
    max_retries=STAGE_RETRY_LIMITS.get("tts_subtitles", 3),
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def generate_tts_task(self, job_id: str):
    """Generate voiceover audio and subtitle timeline from script."""
    db = SessionLocal()
    started_at = datetime.utcnow()
    try:
        coordinator = JobCoordinator(db)
        try:
            job = coordinator._get_job(job_id)
        except ValueError as e:
            raise PermanentError(str(e))

        if not job.metadata_id:
            raise PermanentError(f"[{job_id}] metadata_id missing before TTS stage")

        metadata = db.query(Metadata).filter(Metadata.id == job.metadata_id).first()
        if not metadata:
            raise PermanentError(f"[{job_id}] Metadata row not found for metadata_id={job.metadata_id}")

        script = ((metadata.extra_data or {}).get("generated_script") or "").strip()
        if not script:
            raise PermanentError(f"[{job_id}] Missing generated_script before TTS stage")

        tts_output = TTSService.generate_voiceover(script, job_id)

        existing_extra = metadata.extra_data or {}
        metadata.extra_data = {
            **existing_extra,
            "voiceover": {
                "audio_path": tts_output["audio_path"],
                "duration_seconds": tts_output["duration_seconds"],
            },
            "subtitles": tts_output["subtitles"],
        }
        db.commit()

        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        db.add(
            JobExecutionLog(
                job_id=job_id,
                stage="tts_subtitles",
                status="success",
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=duration_ms,
            )
        )
        db.commit()

        coordinator.transition_to_next_stage(job_id)
        logger.info(f"[{job_id}] TTS generation completed")
        return {
            "status": "success",
            "job_id": job_id,
            "audio_path": tts_output["audio_path"],
            "subtitle_count": len(tts_output["subtitles"]),
        }
    except PermanentError as e:
        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        db.add(
            JobExecutionLog(
                job_id=job_id,
                stage="tts_subtitles",
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
            logger.exception(f"[{job_id}] Failed to mark permanent TTS failure")
        raise
    except RetryableError:
        raise
    except Exception as e:
        raise RetryableError(str(e))
    finally:
        db.close()


__all__ = ["generate_tts_task"]
