"""
Celery Worker Entry Point

This is the entry point for running Celery workers. Use:
    celery -A worker worker --loglevel=info
"""
import logging
from app.tasks.celery_app import celery_app

# Configure logging
logging.basicConfig(
    level="INFO",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("🚀 Starting Celery Worker")
    celery_app.worker_main([
        "worker",
        "--loglevel=info",
        "--concurrency=4",
    ])
