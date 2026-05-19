# Deployment Architecture

This project is designed as a queue-backed media pipeline, not a single request/response app.
The deployment shape should preserve that separation.

## Runtime Components

| Component | Responsibility | Scaling Unit |
| --- | --- | --- |
| Next.js frontend | Job submission, polling, video preview/download UI | Web replicas |
| FastAPI backend | API contract, validation, job state reads/writes | API replicas |
| Celery workers | Long-running pipeline stages | Worker replicas by queue |
| Redis | Celery broker/result backend | Managed Redis / HA Redis |
| PostgreSQL | Durable job state, metadata cache, execution logs | Managed Postgres |
| Local/S3 storage | Audio, subtitles, draft MP4, final MP4 | Shared object storage |
| Flower | Queue visibility during development/ops | Internal-only tool |

## Request Flow

1. User submits an IMDb URL from the frontend.
2. FastAPI validates the URL, creates a `jobs` row, and enqueues metadata extraction.
3. Celery workers process stages asynchronously:
   - metadata extraction
   - script generation
   - TTS/subtitles
   - asset gathering
   - video composition
   - export
4. Each task updates database state and writes durable artifacts.
5. Frontend polls `GET /api/jobs/{job_id}`.
6. When complete, frontend previews/downloads `GET /api/jobs/{job_id}/video`.

## Local Deployment

```bash
cp .env.example .env
# edit OPENAI_API_KEY, or set LLM_PROVIDER=openrouter and OPENROUTER_API_KEY
# TTS_PROVIDER=kokoro uses the local Kokoro Docker service
docker compose up --build
```

Services:

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Kokoro TTS API: http://localhost:8880/docs
- Flower: http://localhost:5555

## Production Shape

Recommended first production deployment:

- Frontend: Vercel, Cloud Run, ECS, or any Node runtime.
- Backend API: ECS/Fargate, Cloud Run, Fly.io, Render, or Kubernetes.
- Workers: separate service/process from API.
- PostgreSQL: managed database, not a container volume.
- Redis: managed Redis.
- Storage: S3/GCS/Azure Blob instead of local disk.

Local disk is acceptable for the assignment and local dev. It is not enough for multi-worker production because workers may run on different machines and need shared artifact access.

## Scaling Strategy

Scale API and workers separately.

API pressure usually comes from polling and job creation. Worker pressure comes from CPU, network, and media rendering.

Suggested worker split as volume grows:

```bash
celery -A app.tasks.celery_app worker -Q metadata,script,tts,assets --loglevel=info --concurrency=4
celery -A app.tasks.celery_app worker -Q video,export --loglevel=info --concurrency=1
```

Why separate media workers?

- FFmpeg is CPU-heavy.
- Video/export tasks can starve lighter API/AI tasks if all share the same concurrency pool.
- A low media concurrency keeps memory and CPU predictable.

## Storage Migration Path

Current storage is local and centralized through `StorageService`.

Production migration path:

1. Add a storage interface with local and S3 implementations.
2. Keep artifact keys deterministic by job ID.
3. Store object keys/URLs in `metadata.extra_data` and `job.output_video_path`.
4. Make `/video` stream from S3 or redirect to a signed URL.

Do not scatter storage paths across services. That is how S3 migrations become rewrites.

## Health And Readiness

`GET /health` checks:

- database connectivity
- Redis/Celery broker connectivity
- local storage path creation

Production should expose:

- readiness check: dependencies reachable
- liveness check: process is alive

For a small assignment, `/health` is enough. For production, split these because a temporarily degraded dependency should not always restart the container.

## Cost Controls

Initial cost risks:

- OpenAI/OpenRouter script generation
- local Kokoro TTS CPU time
- FFmpeg CPU time
- repeated IMDb scraping
- storing final media artifacts

Controls to add as the system grows:

- per-job cost tracking
- max script length
- max video duration
- cache IMDb metadata
- rate limit job submissions
- retention policy for old artifacts

## Security Checklist

- Never commit `.env` files.
- Require strong `POSTGRES_PASSWORD` outside local dev.
- Restrict CORS to real frontend origins.
- Keep Flower private/internal.
- Validate IMDb URLs at the API boundary.
- Do not expose raw local file paths in public API responses.
- Add auth before allowing arbitrary internet users to create jobs.
- Add rate limits before exposing the service publicly.
- Scan uploaded/downloaded media if user uploads are introduced later.

## Operational Risks

| Risk | Mitigation |
| --- | --- |
| Worker dies mid-render | deterministic output paths and Celery retries |
| Redis outage | job remains in DB; new task dispatch pauses |
| DB outage | API should return degraded/unavailable |
| Local disk fills | retention policy and storage monitoring |
| FFmpeg failure | capture stderr, mark stage failed |
| OpenAI/OpenRouter rate limits | classify as retryable and back off |

## Production Readiness Checklist

- [ ] Replace local storage with S3 or shared object storage.
- [ ] Add Alembic migrations instead of `create_all`.
- [ ] Add authentication and rate limiting.
- [ ] Protect Flower behind VPN/auth or disable it.
- [ ] Add structured logs with request/job IDs.
- [ ] Add metrics for job duration, failure rate, queue depth, and cost.
- [ ] Add artifact retention cleanup.
- [ ] Add CI that runs backend tests and frontend lint/type-check/build.
