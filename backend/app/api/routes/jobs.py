"""
Job management API routes
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from uuid import uuid4
import logging

from app.database.connection import get_db
from app.models.job import Job
from app.tasks.celery_app import celery_app
from app.tasks.metadata_tasks import extract_metadata_task
from app.api.schemas import JobSubmitRequest, JobStatusResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/jobs", response_model=JobStatusResponse)
async def submit_job(
    request: JobSubmitRequest,
    db: Session = Depends(get_db)
):
    """
    Submit a new job for video generation.
    
    Takes an IMDb movie URL and returns a job ID for polling.
    """
    try:
        # Validate IMDb URL
        if not request.imdb_url.startswith("https://www.imdb.com/title/"):
            raise HTTPException(
                status_code=400,
                detail="Invalid IMDb URL. Must be in format: https://www.imdb.com/title/tt..."
            )
        
        # Create job in database
        job_id = str(uuid4())
        job = Job(
            id=job_id,
            imdb_url=request.imdb_url,
            status="pending",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        
        logger.info(f"Job created: {job_id} for URL: {request.imdb_url}")
        
        # Enqueue first task (metadata extraction)
        extract_metadata_task.delay(job_id, request.imdb_url)
        logger.info(f"Metadata extraction task queued for job: {job_id}")
        
        return {
            "job_id": job_id,
            "status": job.status,
            "created_at": job.created_at.isoformat(),
            "poll_url": f"/api/jobs/{job_id}",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting job: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit job: {str(e)}"
        )


@router.get("/jobs/{job_id}", response_model=dict)
async def get_job_status(
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Poll job status.
    
    Client calls this repeatedly to get progress information.
    """
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        
        if not job:
            raise HTTPException(
                status_code=404,
                detail=f"Job {job_id} not found"
            )
        
        response = {
            "job_id": job_id,
            "status": job.status,
            "progress": {
                "current_stage": job.status,
                "overall_progress": _calculate_progress(job.status),
            },
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
        }
        
        # Add result if completed
        if job.status == "completed":
            response["result"] = {
                "video_url": f"/api/jobs/{job_id}/video",
                "display_name": job.display_name,
            }
        
        # Add error if failed
        if job.status == "failed":
            response["error"] = {
                "message": job.error_message,
                "stage": job.failure_stage,
                "retry_count": job.retry_count,
            }
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get job status"
        )


@router.get("/jobs/{job_id}/video")
async def download_video(
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Download completed video.
    
    TODO: Stream video file or return download URL
    """
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job.status != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Job not completed. Status: {job.status}"
            )
        
        if not job.output_video_path:
            raise HTTPException(
                status_code=500,
                detail="Video path not found"
            )
        
        # TODO: Implement video streaming or S3 redirect
        return {
            "message": "Video download not yet implemented",
            "video_path": job.output_video_path,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading video: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to download video"
        )


def _calculate_progress(status: str) -> int:
    """Calculate overall progress percentage based on current stage"""
    progress_map = {
        "pending": 0,
        "metadata_extraction": 10,
        "script_generation": 30,
        "tts_subtitles": 50,
        "asset_gathering": 65,
        "video_composition": 80,
        "export": 95,
        "completed": 100,
        "failed": 0,
    }
    return progress_map.get(status, 0)
