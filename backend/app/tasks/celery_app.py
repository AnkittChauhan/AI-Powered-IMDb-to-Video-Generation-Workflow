"""
Celery task queue configuration
"""
from celery import Celery
from app.config import settings

celery_app = Celery(
    "imdb_video_gen",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes hard limit
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit
)

# Import tasks to register them
from app.tasks import metadata_tasks  # noqa

__all__ = ["celery_app"]
