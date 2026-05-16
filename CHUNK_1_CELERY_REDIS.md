# CHUNK 1: Celery + Redis Infrastructure

## What's Included

This chunk sets up the async task processing backbone for the video generation pipeline.

## Files Modified/Created

- `backend/app/tasks/celery_app.py` - Enhanced Celery configuration
- `backend/worker.py` - Worker entry point
- `backend/app/tasks/__init__.py` - Task module organization
- `backend/app/tasks/metadata_tasks.py` - Stage 1 task template
- `backend/app/tasks/script_tasks.py` through `export_tasks.py` - Placeholder files

## How to Run

```bash
# Start everything with Docker
docker-compose up -d

# Monitor tasks
open http://localhost:5555

# Submit a job
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"imdb_url": "https://www.imdb.com/title/tt0111161/"}'
```

## Architecture

Queue-per-stage model:
- metadata queue (priority 10)
- script queue (priority 9)
- video queue (priority 7)
- export queue (priority 6)

Task retry strategy:
- RetryableError: Exponential backoff (2, 4, 8, 16s) with jitter
- PermanentError: Fail fast, no retry
- Max retries per stage: Configurable per stage

## Next: Chunk 2

Implement MetadataService for IMDb scraping with caching.
