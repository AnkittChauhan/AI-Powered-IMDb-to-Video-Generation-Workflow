# AI-Powered IMDb-to-Video Generation Workflow

A production-grade system that converts IMDb movie URLs into 2-minute cinematic video summaries using AI.

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│  Next.js Frontend (3000)                        │
│  - Job submission form                          │
│  - Real-time progress tracking                  │
│  - Video preview & download                     │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  FastAPI Backend (8000)                         │
│  - Job submission API                           │
│  - Status polling                               │
│  - Video download                               │
└──────────────────┬──────────────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    │              │              │
    ▼              ▼              ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│ Celery  │  │ Redis   │  │PostgreSQL
│Worker 1 │  │(Queue)  │  │(DB)
│Worker 2 │  │         │  │
│Worker 3 │  │         │  │
└─────────┘  └─────────┘  └─────────┘
```

## 6-Stage Video Generation Pipeline

1. **Metadata Extraction** - Scrape IMDb for movie data
2. **Script Generation** - Use OpenAI to create 2-min narration
3. **TTS & Subtitles** - Generate audio narration + SRT subtitles
4. **Asset Gathering** - Download images, extract trailer frames
5. **Video Composition** - FFmpeg orchestration (compose video)
6. **Export** - Optimize & export final MP4

## Getting Started

### Prerequisites

- Docker & Docker Compose
- OpenAI API key
- Python 3.11+ (for local development)
- Node.js 18+ (for frontend development)

### Quick Start with Docker Compose

```bash
# Clone repository
git clone <repo-url>
cd Movie2Video\ AI

# Create .env file
cp backend/.env.example backend/.env
# Edit backend/.env and add your OPENAI_API_KEY

# Start full stack
docker-compose up

# Services will be available at:
# - API: http://localhost:8000
# - API Docs: http://localhost:8000/docs
# - Frontend: http://localhost:3000
# - Celery Flower (monitoring): http://localhost:5555
# - Database: localhost:5432
```

### Local Development

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt

# Run FastAPI
uvicorn app.main:app --reload

# Run Celery worker (in another terminal)
celery -A app.tasks.celery_app worker --loglevel=info
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## API Endpoints

### POST /api/jobs
Submit a job for video generation.

```json
{
  "imdb_url": "https://www.imdb.com/title/tt0111161/"
}
```

Response:
```json
{
  "job_id": "uuid-here",
  "status": "pending",
  "created_at": "2026-05-13T10:00:00",
  "poll_url": "/api/jobs/uuid-here"
}
```

### GET /api/jobs/{job_id}
Poll job status and progress.

Response:
```json
{
  "job_id": "uuid",
  "status": "processing_2",
  "progress": {
    "current_stage": "script_generation",
    "overall_progress": 30
  },
  "created_at": "...",
  "error": null
}
```

### GET /api/jobs/{job_id}/video
Download completed video (when status is "completed").

### GET /health
Health check endpoint.

## Project Structure

```
Movie2Video AI/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── jobs.py
│   │   │   │   └── health.py
│   │   │   └── schemas.py
│   │   ├── core/
│   │   ├── database/
│   │   ├── models/
│   │   ├── services/
│   │   ├── tasks/
│   │   ├── main.py
│   │   └── config.py
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   ├── package.json
│   ├── next.config.js
│   ├── tsconfig.json
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

## Configuration

### Environment Variables

See `backend/.env.example` for all available options.

**Critical variables:**
- `OPENAI_API_KEY` - Your OpenAI API key (required)
- `DATABASE_URL` - Database connection string (defaults to SQLite)
- `REDIS_URL` - Redis connection string

### Database

**Development:** SQLite (file-based, included in repo)
**Production:** PostgreSQL (configure via `DATABASE_URL`)

Migrations are handled automatically on startup via SQLAlchemy.

## Development Guide

### Adding a New Task

1. Define the task in `backend/app/tasks/new_tasks.py`
2. Add to `JobCoordinator` in `backend/app/core/job_coordinator.py`
3. Update state machine if needed
4. Test with Celery worker

### Adding a New API Route

1. Create route in `backend/app/api/routes/new_routes.py`
2. Define schemas in `backend/app/api/schemas.py`
3. Include in `backend/app/main.py`
4. Test with `GET http://localhost:8000/docs`

### Database Migrations

**Note:** Initial setup uses SQLAlchemy auto-migration. For production, use Alembic:

```bash
# Generate migration
alembic revision --autogenerate -m "Add new table"

# Apply migration
alembic upgrade head
```

## Monitoring

### Celery Tasks
Visit Flower dashboard: http://localhost:5555

Shows:
- Active tasks
- Task history
- Worker status
- Queue depth
- Task success/failure rates

### Logs
```bash
# Backend logs
docker logs imdb_video_backend

# Celery worker logs
docker logs imdb_video_celery_worker

# Database logs
docker logs imdb_video_postgres
```

## Performance & Cost

### Cost Optimization
- IMDb metadata cached 30 days (80% cache hit rate)
- OpenAI tokens budgeted per job
- Selective AI image generation
- H.264 video codec (good quality, small size)

### Typical Job Duration
- Metadata extraction: 5-10s
- Script generation: 10-20s
- TTS: 10-15s
- Asset gathering: 5-10s
- Video composition: 30-60s
- Export: 10-20s
- **Total: 1-3 minutes**

### Typical Costs
- OpenAI API: $0.10-0.20 per job
- Storage: $0.01 per job
- **Total: ~$0.15 per job**

## Scaling Strategy

### Horizontal Scaling
1. **FastAPI**: Add multiple API instances behind load balancer
2. **Celery**: Increase worker count independently
3. **Database**: Use RDS with read replicas
4. **Redis**: Use ElastiCache or Redis Cluster
5. **Storage**: Migrate to S3

### From 1x to 100x Jobs/Day
- Add 2-3 more Celery workers
- Switch database to PostgreSQL RDS
- Switch Redis to ElastiCache
- Add nginx load balancer
- ~$50-100/month additional cost

## Testing

```bash
# Unit tests
pytest backend/tests/unit

# Integration tests
pytest backend/tests/integration

# Coverage
pytest --cov=app backend/tests
```

## Troubleshooting

### Redis connection errors
```bash
# Check Redis is running
docker logs imdb_video_redis

# Connect to Redis
redis-cli -h localhost ping
```

### Database connection errors
```bash
# Check PostgreSQL is running
docker logs imdb_video_postgres

# Reset database
rm imdb_video.db  # if using SQLite
```

### Celery worker not picking up tasks
```bash
# Restart worker
docker restart imdb_video_celery_worker

# Check Flower for task queue depth
http://localhost:5555
```

## Production Deployment

For the detailed deployment architecture, scaling strategy, storage migration path,
and production readiness checklist, see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

### Pre-deployment Checklist
- [ ] Set `OPENAI_API_KEY` environment variable
- [ ] Switch to PostgreSQL database
- [ ] Use Redis Cluster/Sentinel
- [ ] Add SSL certificates
- [ ] Configure backup strategy
- [ ] Set up monitoring/alerting
- [ ] Load test (simulate peak load)

### Docker Production Build
```bash
# Use docker-compose for production-like environment
docker-compose -f docker-compose.yml up

# Or deploy to Kubernetes/ECS/etc.
```

## Contributing

1. Create a feature branch
2. Make changes
3. Run tests: `pytest`
4. Run linter: `black . && flake8`
5. Submit PR

## License

MIT

## Support

For issues and questions:
1. Check troubleshooting section
2. Review logs in Flower/Docker
3. Open an issue on GitHub
