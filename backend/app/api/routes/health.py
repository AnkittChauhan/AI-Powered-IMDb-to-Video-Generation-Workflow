"""
Health check endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.connection import get_db

router = APIRouter()


@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint.
    
    Returns status of all critical services:
    - Database
    - Redis/Celery (when implemented)
    - Storage (when implemented)
    """
    try:
        # Check database
        db.execute("SELECT 1")
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {
        "status": "healthy" if db_status == "ok" else "degraded",
        "services": {
            "database": db_status,
            "redis": "ok",  # TODO: Actually check Redis
            "storage": "ok",  # TODO: Actually check storage
        },
    }
