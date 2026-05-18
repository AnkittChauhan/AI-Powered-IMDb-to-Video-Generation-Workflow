"""
Health check endpoints
"""
import os

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.config import settings

router = APIRouter()


@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint.
    
    Returns status of all critical services:
    - Database
    - Redis/Celery broker
    - Local storage path
    """
    services = {}

    try:
        db.execute(text("SELECT 1"))
        services["database"] = "ok"
    except Exception as e:
        services["database"] = f"error: {str(e)}"

    try:
        from app.tasks.celery_app import celery_app

        with celery_app.connection_for_read() as conn:
            conn.ensure_connection(max_retries=1)
        services["redis"] = "ok"
    except Exception as e:
        services["redis"] = f"error: {str(e)}"

    try:
        os.makedirs(settings.LOCAL_STORAGE_PATH, exist_ok=True)
        services["storage"] = "ok"
    except Exception as e:
        services["storage"] = f"error: {str(e)}"

    overall_status = "healthy" if all(value == "ok" for value in services.values()) else "degraded"

    return {
        "status": overall_status,
        "services": services,
    }
