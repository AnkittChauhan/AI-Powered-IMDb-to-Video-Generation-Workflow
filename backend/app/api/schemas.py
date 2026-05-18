"""
Request and response schemas with validation
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, Dict, Any
import re


class JobSubmitRequest(BaseModel):
    """Request to submit a new job"""
    imdb_url: str = Field(
        ...,
        description="IMDb movie URL (e.g., https://www.imdb.com/title/tt0111161/)",
        json_schema_extra={"example": "https://www.imdb.com/title/tt0111161/"},
    )
    
    @field_validator("imdb_url")
    @classmethod
    def validate_imdb_url(cls, v: str) -> str:
        """Validate IMDb URL format"""
        pattern = r"https://www\.imdb\.com/title/(tt\d+)/?$"
        if not re.match(pattern, v):
            raise ValueError(
                "Invalid IMDb URL format. Must be: https://www.imdb.com/title/tt<digits>/"
            )
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"imdb_url": "https://www.imdb.com/title/tt0111161/"}
        }
    )


class JobStatusResponse(BaseModel):
    """Response for job submission (201 Accepted)"""
    job_id: str = Field(..., description="Unique job ID for polling")
    status: str = Field(..., description="Current job status (e.g., 'pending')")
    created_at: str = Field(..., description="ISO 8601 timestamp when job was created")
    poll_url: Optional[str] = Field(None, description="URL to poll for job status")
    progress: Optional[Dict[str, Any]] = Field(None, description="Initial progress info")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "pending",
                "created_at": "2024-05-12T23:01:00Z",
                "poll_url": "/api/jobs/550e8400-e29b-41d4-a716-446655440000"
            }
        }
    )


class ProgressDetail(BaseModel):
    """Detailed progress information"""
    current_stage: str = Field(..., description="Current pipeline stage")
    overall_progress: int = Field(..., ge=0, le=100, description="Overall progress (0-100%)")
    stage_progress: Optional[int] = Field(None, ge=0, le=100, description="Current stage progress")
    elapsed_seconds: int = Field(..., description="Seconds elapsed since job start")
    estimated_remaining_seconds: Optional[int] = Field(
        None,
        description="Estimated remaining time (heuristic)"
    )


class ErrorDetail(BaseModel):
    """Error information when job fails"""
    message: str = Field(..., description="Error message")
    stage: Optional[str] = Field(None, description="Stage where error occurred")
    retry_count: Optional[int] = Field(None, description="Number of retry attempts")
    error_code: Optional[str] = Field(None, description="Error classification")


class VideoResultDetail(BaseModel):
    """Result when job completes"""
    video_url: str = Field(..., description="URL to download/stream video")
    display_name: Optional[str] = Field(None, description="Movie title or custom name")
    file_size_mb: Optional[float] = Field(None, description="Output video file size")
    duration_seconds: Optional[int] = Field(None, description="Video duration")


class JobProgressResponse(BaseModel):
    """Response for job status polling"""
    job_id: str = Field(..., description="Job ID")
    status: str = Field(
        ...,
        description="Current status (pending, metadata_extraction, script_generation, tts_subtitles, asset_gathering, video_composition, export, completed, failed)"
    )
    overall_progress: int = Field(..., ge=0, le=100, description="Overall progress (0-100%)")
    current_stage: str = Field(..., description="Current pipeline stage")
    created_at: str = Field(..., description="ISO 8601 timestamp")
    started_at: Optional[str] = Field(None, description="ISO 8601 when processing started")
    updated_at: Optional[str] = Field(None, description="ISO 8601 last update time")
    progress: Optional[ProgressDetail] = Field(None, description="Detailed progress")
    error: Optional[ErrorDetail] = Field(None, description="Error info if failed")
    result: Optional[VideoResultDetail] = Field(None, description="Result if completed")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "script_generation",
                "overall_progress": 30,
                "current_stage": "script_generation",
                "created_at": "2024-05-12T23:01:00Z",
                "started_at": "2024-05-12T23:01:30Z",
                "progress": {
                    "current_stage": "script_generation",
                    "overall_progress": 30,
                    "elapsed_seconds": 90,
                    "estimated_remaining_seconds": 210
                }
            }
        }
    )


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Overall health status (healthy, degraded, unhealthy)")
    services: Dict[str, str] = Field(..., description="Individual service health status")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "services": {
                    "database": "ok",
                    "redis": "ok",
                    "storage": "ok"
                }
            }
        }
    )


class ErrorResponse(BaseModel):
    """Error response for all endpoints"""
    error_code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    retry_after_seconds: Optional[int] = Field(None, description="Retry-After hint (if applicable)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error_code": "invalid_input",
                "message": "Invalid IMDb URL format",
                "details": {
                    "field": "imdb_url",
                    "reason": "Must match https://www.imdb.com/title/tt<digits>/"
                }
            }
        }
    )
