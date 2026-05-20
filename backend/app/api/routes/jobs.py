"""
Job management API routes
"""
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from uuid import uuid4
import logging
from datetime import datetime
from pathlib import Path

from app.database.connection import get_db
from app.models.job import Job
from app.core.job_coordinator import JobCoordinator, JobStage
from app.core.error_handling import (
    InputValidator,
    InvalidInputError,
)
from app.api.schemas import (
    JobSubmitRequest,
    JobStatusResponse,
    JobProgressResponse,
    ErrorResponse,
)
from app.utils.constants import STAGE_PROGRESS_MAP

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/jobs",
    response_model=JobStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
async def submit_job(
    request: JobSubmitRequest,
    db: Session = Depends(get_db)
):
    """
    Submit a new job for video generation.
    
    Takes an IMDb movie URL and creates an async job that processes the video
    generation pipeline. Returns immediately with a job ID for polling.
    
    Response:
    - 202 Accepted: Job created successfully
    - 400 Bad Request: Invalid input
    - 500 Internal Server Error: Database or service error
    
    Examples:
        POST /api/jobs
        {
            "imdb_url": "https://www.imdb.com/title/tt0111161/"
        }
        
        Returns (202):
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "pending",
            "created_at": "2024-05-12T23:01:00Z",
            "poll_url": "/api/jobs/550e8400-e29b-41d4-a716-446655440000"
        }
    """
    
    # ===== Step 1: Validate input =====
    try:
        InputValidator.validate_imdb_url(request.imdb_url)
    except InvalidInputError as e:
        logger.warning(f"Invalid IMDb URL: {request.imdb_url}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "invalid_imdb_url",
                "message": str(e),
            }
        )
    
    # ===== Step 2: Create job in database =====
    job_id = str(uuid4())
    try:
        job = Job(
            id=job_id,
            imdb_url=request.imdb_url,
            status=JobStage.PENDING.value,
            created_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        
        logger.info(
            f"Job created",
            extra={
                "job_id": job_id,
                "imdb_url": request.imdb_url,
                "action": "job_created",
            }
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create job: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "database_error",
                "message": "Failed to create job in database",
            }
        )
    
    # ===== Step 3: Enqueue first task =====
    try:
        coordinator = JobCoordinator(db)
        coordinator.transition_to_next_stage(job_id)
        logger.info(f"Job {job_id} enqueued for processing")
    except Exception as e:
        logger.error(f"Failed to enqueue task for job {job_id}: {str(e)}")
        job.status = JobStage.FAILED.value
        job.failure_stage = JobStage.PENDING.value
        job.error_message = "Failed to enqueue job for processing. Check Redis/Celery worker configuration."
        job.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "queue_unavailable",
                "message": "Job could not be queued for processing",
            }
        )
    
    # ===== Step 4: Return response =====
    return JobStatusResponse(
        job_id=job_id,
        status=JobStage.PENDING.value,
        created_at=job.created_at.isoformat(),
        poll_url=f"/api/jobs/{job_id}",
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobProgressResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
async def get_job_status(
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Poll job status.
    
    Client calls this repeatedly to get progress information. Response includes
    current stage, overall progress percentage, and error details (if failed).
    
    Response:
    - 200 OK: Job status returned
    - 404 Not Found: Job ID doesn't exist
    - 500 Internal Server Error: Server error
    
    Examples:
        GET /api/jobs/550e8400-e29b-41d4-a716-446655440000
        
        Returns (200):
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "script_generation",
            "overall_progress": 30,
            "current_stage": "script_generation",
            "created_at": "2024-05-12T23:01:00Z",
            "progress": {
                "current_stage": "script_generation",
                "overall_progress": 30,
                "elapsed_seconds": 90,
                "estimated_remaining_seconds": 210
            }
        }
    """
    
    try:
        # ===== Fetch job from database =====
        job = db.query(Job).filter(Job.id == job_id).first()
        
        if not job:
            logger.warning(f"Job not found: {job_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error_code": "job_not_found",
                    "message": f"Job {job_id} not found",
                }
            )
        
        # ===== Build response =====
        coordinator = JobCoordinator(db)
        progress = coordinator.get_job_progress(job_id)
        
        response = JobProgressResponse(
            job_id=job_id,
            status=job.status,
            overall_progress=STAGE_PROGRESS_MAP.get(job.status, 0),
            current_stage=job.status,
            created_at=job.created_at.isoformat(),
            started_at=job.started_at.isoformat() if job.started_at else None,
            updated_at=progress.get("updated_at"),
            progress={
                "current_stage": job.status,
                "overall_progress": progress.get("overall_progress", 0),
                "elapsed_seconds": int((datetime.utcnow() - job.created_at).total_seconds()),
                "estimated_remaining_seconds": progress.get("estimated_remaining_seconds"),
            },
        )
        
        # Add error if job failed
        if job.status == JobStage.FAILED.value:
            response.error = {
                "message": job.error_message,
                "stage": job.failure_stage,
                "retry_count": job.retry_count,
            }
        
        # Add result if completed
        if job.status == JobStage.COMPLETED.value:
            response.result = {
                "video_url": f"/api/jobs/{job_id}/video",
                "display_name": job.display_name,
            }
        
        logger.info(
            f"Job status retrieved",
            extra={
                "job_id": job_id,
                "status": job.status,
            }
        )
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status for {job_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "server_error",
                "message": "Failed to retrieve job status",
            }
        )


@router.get(
    "/jobs/{job_id}/video",
    responses={
        400: {"description": "Job not completed"},
        404: {"model": ErrorResponse, "description": "Job or video not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
async def download_video(
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Download completed video.
    
    Returns the final MP4 video file if job has completed successfully.
    
    Response:
    - 200 OK: Video stream or redirect (Content-Type: video/mp4)
    - 400 Bad Request: Job not completed
    - 404 Not Found: Job or video not found
    - 500 Internal Server Error: Server error
    
    This endpoint only succeeds when both the job and final MP4 artifact exist.
    """
    
    try:
        # ===== Fetch job =====
        job = db.query(Job).filter(Job.id == job_id).first()
        
        if not job:
            logger.warning(f"Job not found: {job_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error_code": "job_not_found",
                    "message": f"Job {job_id} not found",
                }
            )
        
        # ===== Check job is completed =====
        if job.status != JobStage.COMPLETED.value:
            logger.warning(f"Job {job_id} not completed: {job.status}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "job_not_completed",
                    "message": f"Job not completed. Current status: {job.status}",
                }
            )
        
        # ===== Check video exists =====
        if not job.output_video_path:
            logger.error(f"Video path not found for completed job {job_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error_code": "video_not_found",
                    "message": "Video file path not found",
                }
            )
        
        video_path = Path(job.output_video_path)
        if not video_path.exists() or not video_path.is_file():
            logger.error(f"Video file missing for completed job {job_id}: {job.output_video_path}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error_code": "video_file_missing",
                    "message": "Video file is missing from storage",
                },
            )

        logger.info(f"Video download requested for job {job_id}")
        safe_name = (job.display_name or job_id).replace("/", "-").strip()
        return FileResponse(
            path=str(video_path),
            media_type="video/mp4",
            filename=f"{safe_name}.mp4",
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading video for {job_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "server_error",
                "message": "Failed to download video",
            }
        )
