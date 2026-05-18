"""Stage 6: Final MP4 export task."""

from datetime import datetime

from celery import shared_task
from celery.utils.log import get_task_logger

from app.core.error_handling import PermanentError, RetryableError
from app.core.job_coordinator import JobCoordinator
from app.database.connection import SessionLocal
from app.models.job import JobExecutionLog, Metadata
from app.services.export_service import ExportService
from app.utils.constants import STAGE_RETRY_LIMITS

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    queue="export",
    time_limit=10 * 60,
    soft_time_limit=8 * 60,
    max_retries=STAGE_RETRY_LIMITS.get("export", 2),
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def export_video_task(self, job_id: str):
    """Export the composed draft video into the final MP4 artifact."""
    db = SessionLocal()
    started_at = datetime.utcnow()
    try:
        coordinator = JobCoordinator(db)
        try:
            job = coordinator._get_job(job_id)
        except ValueError as e:
            raise PermanentError(str(e))

        if not job.metadata_id:
            raise PermanentError(f"[{job_id}] metadata_id missing before export")

        metadata = db.query(Metadata).filter(Metadata.id == job.metadata_id).first()
        if not metadata:
            raise PermanentError(f"[{job_id}] Metadata row not found for metadata_id={job.metadata_id}")

        extra = metadata.extra_data or {}
        composition = extra.get("composition") or {}
        draft_video_path = composition.get("draft_video_path")
        if not draft_video_path:
            raise PermanentError(f"[{job_id}] draft_video_path missing before export")

        export_output = ExportService.export_mp4(job_id=job_id, draft_video_path=draft_video_path)
        job.output_video_path = export_output["final_video_path"]
        metadata.extra_data = {
            **extra,
            "export": {
                **export_output,
                "generated_at": datetime.utcnow().isoformat(),
            },
        }
        db.commit()

        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        db.add(
            JobExecutionLog(
                job_id=job_id,
                stage="export",
                status="success",
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=duration_ms,
            )
        )
        db.commit()

        coordinator.transition_to_next_stage(job_id)
        logger.info(f"[{job_id}] Export completed")
        return {
            "status": "success",
            "job_id": job_id,
            "final_video_path": export_output["final_video_path"],
        }

    except PermanentError as e:
        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        db.add(
            JobExecutionLog(
                job_id=job_id,
                stage="export",
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
            logger.exception(f"[{job_id}] Failed to mark permanent export failure")
        raise
    except RetryableError:
        raise
    except Exception as e:
        raise RetryableError(str(e))
    finally:
        db.close()


__all__ = ["export_video_task"]
