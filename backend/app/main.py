"""
IMDb Video Generation Backend
FastAPI application entry point
"""
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.config import settings
from app.api.routes import health, jobs
from app.database.connection import init_db

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and clean up application resources."""
    logger.info("🚀 Starting IMDb Video Generator API")
    init_db()
    logger.info("✓ Database initialized")
    yield
    logger.info("🛑 Shutting down IMDb Video Generator API")


# Initialize FastAPI app
app = FastAPI(
    title="IMDb Video Generator",
    description="AI-powered video generation from IMDb movie URLs",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# Routes
app.include_router(health.router, tags=["Health"])
app.include_router(jobs.router, prefix="/api", tags=["Jobs"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "IMDb Video Generator API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
