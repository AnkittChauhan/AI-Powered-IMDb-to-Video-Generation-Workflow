"""
Request and response schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class JobSubmitRequest(BaseModel):
    """Request to submit a new job"""
    imdb_url: str = Field(
        ...,
        description="IMDb movie URL (e.g., https://www.imdb.com/title/tt0111161/)"
    )


class JobStatusResponse(BaseModel):
    """Response for job status"""
    job_id: str
    status: str
    created_at: str
    poll_url: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None


class JobProgressResponse(BaseModel):
    """Job progress information"""
    job_id: str
    status: str
    overall_progress: int
    current_stage: str
    created_at: str
    started_at: Optional[str] = None
    error: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
