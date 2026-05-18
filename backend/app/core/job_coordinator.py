"""
JobCoordinator: State machine orchestrator for the video generation pipeline.

Responsibilities:
- Manage job state transitions through the 6-stage pipeline
- Determine the next stage for a job
- Enqueue tasks at each stage
- Handle failures and retries
- Track job progress
- Calculate estimated completion times

Design:
  The JobCoordinator is a central "traffic controller" for the job workflow.
  Rather than having tasks schedule themselves (which creates hidden dependencies),
  tasks call JobCoordinator.transition_to_next_stage() to ask "what's next?"
  
  This makes the workflow explicit, testable, and easy to debug.
"""

from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
import logging
from sqlalchemy.orm import Session

from app.models.job import Job, JobExecutionLog
from app.core.error_handling import RetryableError, PermanentError
from app.utils.constants import STAGE_RETRY_LIMITS, STAGE_TIMEOUT_SECONDS, JOB_STAGES

logger = logging.getLogger(__name__)


class JobStage(str, Enum):
    """All valid job stages in the pipeline"""
    PENDING = "pending"
    METADATA_EXTRACTION = "metadata_extraction"
    SCRIPT_GENERATION = "script_generation"
    TTS_SUBTITLES = "tts_subtitles"
    ASSET_GATHERING = "asset_gathering"
    VIDEO_COMPOSITION = "video_composition"
    EXPORT = "export"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobCoordinator:
    """
    Central orchestrator for job state machine.
    
    Usage:
        coordinator = JobCoordinator(db)
        
        # Check current stage
        current = coordinator.get_current_stage(job_id)
        
        # Transition to next stage
        success = coordinator.enqueue_next_task(job_id)
        
        # Handle failure
        coordinator.handle_failure(job_id, error="timeout", should_retry=True)
    """
    
    # Stage pipeline (order matters)
    PIPELINE = [
        JobStage.PENDING,
        JobStage.METADATA_EXTRACTION,
        JobStage.SCRIPT_GENERATION,
        JobStage.TTS_SUBTITLES,
        JobStage.ASSET_GATHERING,
        JobStage.VIDEO_COMPOSITION,
        JobStage.EXPORT,
        JobStage.COMPLETED,
    ]
    
    # Map stages to task names (for Celery)
    STAGE_TO_TASK = {
        JobStage.METADATA_EXTRACTION: "app.tasks.metadata_tasks.extract_metadata_task",
        JobStage.SCRIPT_GENERATION: "app.tasks.script_tasks.generate_script_task",
        JobStage.TTS_SUBTITLES: "app.tasks.tts_tasks.generate_tts_task",
        JobStage.ASSET_GATHERING: "app.tasks.asset_tasks.gather_assets_task",
        JobStage.VIDEO_COMPOSITION: "app.tasks.video_tasks.compose_video_task",
        JobStage.EXPORT: "app.tasks.export_tasks.export_video_task",
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_current_stage(self, job_id: str) -> JobStage:
        """
        Get the current stage of a job.
        
        Args:
            job_id: Job ID
            
        Returns:
            Current JobStage
            
        Raises:
            ValueError: If job not found or invalid status
        """
        job = self._get_job(job_id)
        try:
            return JobStage(job.status)
        except ValueError:
            raise ValueError(f"Invalid job status: {job.status}")
    
    def get_next_stage(self, job_id: str) -> Optional[JobStage]:
        """
        Determine what stage comes after the current one.
        
        Args:
            job_id: Job ID
            
        Returns:
            Next JobStage or None if at end of pipeline
            
        Special logic:
            - If job is failed/cancelled/completed, returns None
            - Otherwise returns next stage in pipeline
        """
        job = self._get_job(job_id)
        current_stage = JobStage(job.status)
        
        # Terminal states have no next stage
        if current_stage in [JobStage.COMPLETED, JobStage.FAILED, JobStage.CANCELLED]:
            return None
        
        # Find position in pipeline and return next
        try:
            current_index = self.PIPELINE.index(current_stage)
            if current_index < len(self.PIPELINE) - 1:
                return self.PIPELINE[current_index + 1]
        except ValueError:
            pass
        
        return None
    
    def transition_to_next_stage(self, job_id: str) -> bool:
        """
        Move job to the next stage in the pipeline.
        
        Called by tasks to indicate they completed successfully.
        
        Args:
            job_id: Job ID
            
        Returns:
            True if transition succeeded, False otherwise
            
        Logic:
            1. Get current stage
            2. Find next stage
            3. Verify transition is valid
            4. Update job status
            5. Enqueue next task (if not at end)
        """
        job = self._get_job(job_id)
        current_stage = JobStage(job.status)
        next_stage = self.get_next_stage(job_id)
        
        if next_stage is None:
            logger.warning(f"Job {job_id} at {current_stage} has no next stage")
            return False
        
        # Update job status
        job.status = next_stage.value
        job.updated_at = datetime.utcnow()
        
        # Special handling for stage transitions
        if next_stage == JobStage.EXPORT:
            job.completed_at = None  # Will be set when export finishes
        
        self.db.commit()
        logger.info(f"Job {job_id} transitioned: {current_stage} → {next_stage}")
        
        # Enqueue next task if not completed
        if next_stage != JobStage.COMPLETED:
            self._enqueue_task(job_id, next_stage)
        else:
            logger.info(f"Job {job_id} completed successfully")
            job.completed_at = datetime.utcnow()
            self.db.commit()
        
        return True
    
    def handle_failure(
        self,
        job_id: str,
        error: str,
        error_type: str = "retryable",
        should_retry: bool = True,
    ) -> bool:
        """
        Handle task failure. Decide whether to retry, move to DLQ, or mark failed.
        
        Called by tasks when they encounter errors.
        
        Args:
            job_id: Job ID
            error: Error message
            error_type: "retryable" or "permanent"
            should_retry: Explicit retry flag
            
        Returns:
            True if will retry, False if marked failed
            
        Logic:
            1. Get job and current stage
            2. Check if stage has retries left
            3. If retries left AND should_retry: increment counter, re-enqueue task
            4. If no retries left: mark job as FAILED, log error, alert
        """
        job = self._get_job(job_id)
        current_stage = JobStage(job.status)
        
        # Can't retry terminal states
        if current_stage in [JobStage.COMPLETED, JobStage.FAILED, JobStage.CANCELLED]:
            logger.error(f"Cannot retry job {job_id} in terminal state: {current_stage}")
            return False
        
        stage_name = current_stage.value
        max_retries = STAGE_RETRY_LIMITS.get(stage_name, 2)
        
        # Check if we can retry
        if should_retry and job.retry_count < max_retries:
            job.retry_count += 1
            logger.info(
                f"Job {job_id} retry {job.retry_count}/{max_retries} "
                f"for stage {stage_name}: {error}"
            )
            
            # Log retry attempt
            self._log_execution(
                job_id,
                stage_name,
                status="retried",
                error_message=error,
                retry_attempt=job.retry_count,
            )
            
            self.db.commit()
            
            # Re-enqueue task with exponential backoff
            self._enqueue_task(job_id, current_stage, retry_attempt=job.retry_count)
            return True
        
        else:
            # Max retries exceeded - mark as failed
            job.status = JobStage.FAILED.value
            job.failure_stage = stage_name
            job.error_message = error
            job.completed_at = datetime.utcnow()
            
            logger.error(
                f"Job {job_id} failed permanently at stage {stage_name} "
                f"after {job.retry_count} retries: {error}"
            )
            
            # Log failure
            self._log_execution(
                job_id,
                stage_name,
                status="failed",
                error_message=error,
                retry_attempt=job.retry_count,
            )
            
            self.db.commit()
            
            # TODO: Alert monitoring system / email user
            return False
    
    def get_job_progress(self, job_id: str) -> Dict[str, Any]:
        """
        Get current progress of a job.
        
        Returns:
            {
                "job_id": str,
                "status": str,
                "current_stage": str,
                "overall_progress": int (0-100),
                "stage_progress": int (0-100),
                "created_at": str,
                "started_at": str or None,
                "estimated_remaining_seconds": int or None,
                "error": dict or None,
            }
        """
        job = self._get_job(job_id)
        
        response = {
            "job_id": job_id,
            "status": job.status,
            "current_stage": job.status,
            "overall_progress": self._calculate_progress(job.status),
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "updated_at": job.updated_at.isoformat() if hasattr(job, "updated_at") else None,
        }
        
        # Add error if failed
        if job.status == JobStage.FAILED.value:
            response["error"] = {
                "message": job.error_message,
                "stage": job.failure_stage,
                "retry_count": job.retry_count,
            }
        
        # Estimate remaining time (basic heuristic)
        if job.status not in [JobStage.COMPLETED.value, JobStage.FAILED.value]:
            elapsed = (datetime.utcnow() - job.created_at).total_seconds()
            progress_pct = response["overall_progress"]
            if progress_pct > 0 and progress_pct < 100:
                estimated_total = elapsed / (progress_pct / 100.0)
                response["estimated_remaining_seconds"] = int(estimated_total - elapsed)
        
        return response
    
    def retry_stage(self, job_id: str, stage_name: str) -> bool:
        """
        Manually retry a specific stage (admin/debugging function).
        
        Args:
            job_id: Job ID
            stage_name: Stage to retry
            
        Returns:
            True if retry queued, False if invalid stage
        """
        job = self._get_job(job_id)
        
        try:
            stage = JobStage(stage_name)
        except ValueError:
            logger.error(f"Invalid stage: {stage_name}")
            return False
        
        # Can only retry stages in pipeline
        if stage not in self.PIPELINE[:-1]:  # Exclude COMPLETED
            logger.error(f"Cannot retry stage: {stage}")
            return False
        
        # Update job status and reset retry count
        job.status = stage.value
        job.retry_count = 0
        job.error_message = None
        job.failure_stage = None
        
        logger.info(f"Admin retry: job {job_id} requeued at stage {stage_name}")
        
        self.db.commit()
        
        # Enqueue task
        self._enqueue_task(job_id, stage)
        
        return True
    
    # ========== Private Helper Methods ==========
    
    def _get_job(self, job_id: str) -> Job:
        """Get job from database or raise ValueError"""
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        return job
    
    def _enqueue_task(
        self,
        job_id: str,
        stage: JobStage,
        retry_attempt: int = 0,
    ) -> None:
        """
        Enqueue the task for a given stage.
        
        Args:
            job_id: Job ID
            stage: Stage to execute
            retry_attempt: Retry number (0 for first attempt)
        """
        from app.tasks.celery_app import celery_app
        
        task_name = self.STAGE_TO_TASK.get(stage)
        if not task_name:
            logger.error(f"No task defined for stage: {stage}")
            return
        
        # Calculate countdown for retry backoff
        countdown = self._calculate_backoff(retry_attempt)
        
        logger.info(f"Enqueueing task {task_name} for job {job_id} (retry {retry_attempt})")
        
        # Metadata task requires job_id only; task reads imdb_url from database.
        task_args = [job_id]

        try:
            # Publish by task name so the API producer does not depend on
            # importing every worker task into its local Celery registry.
            celery_app.send_task(
                task_name,
                args=task_args,
                countdown=countdown,
                task_id=f"{job_id}:{stage.value}:{retry_attempt}",
            )
        except Exception as e:
            logger.error(
                f"Failed to enqueue task {task_name} for job {job_id}: {str(e)}"
            )
    
    def _calculate_backoff(self, retry_attempt: int) -> int:
        """
        Calculate exponential backoff with jitter.
        
        Attempt 1: 0s (immediate)
        Attempt 2: 2s + jitter
        Attempt 3: 4s + jitter
        Attempt 4: 8s + jitter
        etc.
        """
        if retry_attempt == 0:
            return 0
        
        import random
        base_delay = 2 ** retry_attempt  # 2, 4, 8, 16, ...
        jitter = random.uniform(0, base_delay * 0.1)  # +10% jitter
        return int(base_delay + jitter)
    
    def _calculate_progress(self, status: str) -> int:
        """Calculate overall progress percentage based on current stage"""
        progress_map = {
            JobStage.PENDING.value: 0,
            JobStage.METADATA_EXTRACTION.value: 10,
            JobStage.SCRIPT_GENERATION.value: 30,
            JobStage.TTS_SUBTITLES.value: 50,
            JobStage.ASSET_GATHERING.value: 65,
            JobStage.VIDEO_COMPOSITION.value: 80,
            JobStage.EXPORT.value: 95,
            JobStage.COMPLETED.value: 100,
            JobStage.FAILED.value: 0,
            JobStage.CANCELLED.value: 0,
        }
        return progress_map.get(status, 0)
    
    def _log_execution(
        self,
        job_id: str,
        stage: str,
        status: str,
        error_message: Optional[str] = None,
        retry_attempt: int = 0,
        duration_ms: int = 0,
    ) -> None:
        """
        Log task execution (create audit trail).
        
        Args:
            job_id: Job ID
            stage: Stage name
            status: "success", "failed", "retried"
            error_message: Error details (if failed)
            retry_attempt: Retry number
            duration_ms: How long stage took
        """
        log_entry = JobExecutionLog(
            job_id=job_id,
            stage=stage,
            status=status,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=duration_ms,
            error_message=error_message,
            retry_attempt=retry_attempt,
        )
        self.db.add(log_entry)
        self.db.commit()
