"""
Celery task queue configuration

This module sets up Celery for async task processing.
All tasks are routed through Redis message broker.

Architecture:
- Broker: Redis (reliable, fast, supports priority queues)
- Backend: Redis (stores task results and status)
- Tasks: Auto-discovered from app.tasks module
- Workers: Consume tasks and execute them

Retry Strategy:
- Retryable errors (network timeouts): Exponential backoff
- Permanent errors (invalid input): Fast-fail, no retry
- Hard limit: 30 minutes (task_time_limit)
- Soft limit: 25 minutes (task_soft_time_limit - allows graceful shutdown)
"""
from celery import Celery
from kombu import Queue, Exchange
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Initialize Celery app
celery_app = Celery(
    "imdb_video_gen",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# ============================================================================
# CELERY CONFIGURATION
# ============================================================================

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Timezone
    timezone="UTC",
    enable_utc=True,
    
    # Task execution
    task_track_started=True,
    task_acks_late=True,  # Worker acknowledges task only after completion
    task_reject_on_worker_lost=True,  # Re-queue task if worker dies
    
    # Time limits
    task_time_limit=30 * 60,  # Hard limit: 30 minutes
    task_soft_time_limit=25 * 60,  # Soft limit: 25 minutes
    
    # Result backend
    result_expires=3600,  # Results expire after 1 hour
    result_backend_transport_options={
        "visibility_timeout": 3600,
        "retry_on_timeout": True,
    },
    
    # Broker options
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    
    # Worker pool settings
    worker_prefetch_multiplier=4,  # Prefetch 4 tasks per worker
    worker_max_tasks_per_child=1000,  # Recycle worker after 1000 tasks
    
    # Task routing
    task_routes={
        "app.tasks.metadata_tasks.*": {"queue": "metadata"},
        "app.tasks.script_tasks.*": {"queue": "script"},
        "app.tasks.tts_tasks.*": {"queue": "tts"},
        "app.tasks.asset_tasks.*": {"queue": "assets"},
        "app.tasks.video_tasks.*": {"queue": "video"},
        "app.tasks.export_tasks.*": {"queue": "export"},
    },
)

# ============================================================================
# QUEUE CONFIGURATION
# ============================================================================
# Define task queues with priorities
# Higher priority tasks are consumed first

default_exchange = Exchange("imdb_video", type="direct")

celery_app.conf.task_queues = (
    Queue("metadata", exchange=default_exchange, priority=10, routing_key="metadata"),
    Queue("script", exchange=default_exchange, priority=9, routing_key="script"),
    Queue("tts", exchange=default_exchange, priority=8, routing_key="tts"),
    Queue("assets", exchange=default_exchange, priority=8, routing_key="assets"),
    Queue("video", exchange=default_exchange, priority=7, routing_key="video"),
    Queue("export", exchange=default_exchange, priority=6, routing_key="export"),
    Queue("default", exchange=default_exchange, priority=5, routing_key="default"),
)

# ============================================================================
# AUTO-DISCOVERY OF TASKS
# ============================================================================
# Tasks are auto-discovered from these modules
celery_app.autodiscover_tasks([
    "app.tasks.metadata_tasks",
    "app.tasks.script_tasks",
    "app.tasks.tts_tasks",
    "app.tasks.asset_tasks",
    "app.tasks.video_tasks",
    "app.tasks.export_tasks",
])


# ============================================================================
# SIGNAL HANDLERS
# ============================================================================
from celery.signals import task_prerun, task_postrun, task_failure

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, **kwargs):
    """Log when task starts"""
    logger.info(f"Task started: {task.name} [{task_id}]")


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, **kwargs):
    """Log when task completes"""
    logger.info(f"Task completed: {task.name} [{task_id}]")


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, **kwargs):
    """Log when task fails"""
    logger.error(f"Task failed: {sender.name} [{task_id}] - {str(exception)}")


__all__ = ["celery_app"]
