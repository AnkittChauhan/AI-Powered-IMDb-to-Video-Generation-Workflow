"""
Application constants and configuration values.

This file contains magic numbers, timeouts, retry limits, and other
configuration that should be easily tunable.
"""

# ========== Job Stage Configuration ==========

JOB_STAGES = [
    "pending",
    "metadata_extraction",
    "script_generation",
    "tts_subtitles",
    "asset_gathering",
    "video_composition",
    "export",
    "completed",
    "failed",
    "cancelled",
]

# Maximum retries per stage (adaptive based on reliability)
STAGE_RETRY_LIMITS = {
    "metadata_extraction": 3,   # Rate-limited IMDb scraping
    "script_generation": 5,     # OpenAI sometimes rate-limits
    "tts_subtitles": 3,        # TTS API calls
    "asset_gathering": 2,      # Can fail gracefully (use placeholders)
    "video_composition": 1,    # FFmpeg usually fails for immutable reasons
    "export": 2,               # Final MP4 export
}

# Timeout per stage (seconds)
STAGE_TIMEOUT_SECONDS = {
    "metadata_extraction": 60,      # IMDb scraping
    "script_generation": 120,       # OpenAI API calls
    "tts_subtitles": 90,           # TTS generation
    "asset_gathering": 120,        # Download images/videos
    "video_composition": 600,      # FFmpeg (can be slow)
    "export": 300,                 # Final MP4 export
}

# ========== API Configuration ==========

API_PREFIX = "/api"
API_VERSION = "v1"

# Response codes
HTTP_ACCEPTED = 202
HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_INTERNAL_ERROR = 500

# ========== Job Progress Milestones ==========

# Progress percentage at each stage
STAGE_PROGRESS_MAP = {
    "pending": 0,
    "metadata_extraction": 10,
    "script_generation": 30,
    "tts_subtitles": 50,
    "asset_gathering": 65,
    "video_composition": 80,
    "export": 95,
    "completed": 100,
    "failed": 0,
    "cancelled": 0,
}

# ========== Storage Configuration ==========

# Default storage paths (relative to project root)
STORAGE_BASE_PATH = "/tmp/movie2video"
VIDEO_OUTPUT_PATH = f"{STORAGE_BASE_PATH}/videos"
TEMP_PATH = f"{STORAGE_BASE_PATH}/temp"
CACHE_PATH = f"{STORAGE_BASE_PATH}/cache"

# Maximum file sizes
MAX_VIDEO_SIZE_MB = 500
MAX_IMAGE_SIZE_MB = 50

# Video output format
VIDEO_CODEC = "h264"  # H.264 for compatibility
AUDIO_CODEC = "aac"
VIDEO_BITRATE = "2500k"  # 2500 kbps
AUDIO_BITRATE = "128k"
VIDEO_FPS = 30
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_RESOLUTION = f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}"
VIDEO_FILTER_RESOLUTION = f"{VIDEO_WIDTH}:{VIDEO_HEIGHT}"

# ========== Metadata Cache Configuration ==========

# How long to cache IMDb metadata (seconds)
METADATA_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days

# Re-fetch metadata if older than this
METADATA_REFRESH_THRESHOLD_SECONDS = 7 * 24 * 60 * 60  # 7 days

# ========== AI/OpenAI Configuration ==========

# Token budgeting
SCRIPT_GENERATION_MAX_TOKENS = 2000
SCRIPT_GENERATION_PROMPT_TOKENS_BUDGET = 500
TTS_MAX_CHARACTERS = 2000

# Cost limits
MAX_COST_PER_JOB_USD = 10.00
OPENAI_TEXT_PRICE_PER_1K_TOKENS = 0.002  # gpt-3.5-turbo (approximate)

# OpenAI model versions
OPENAI_CHAT_MODEL = "gpt-3.5-turbo"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_TTS_MODEL = "tts-1"
OPENAI_TTS_VOICE = "alloy"

# ========== Celery Task Configuration ==========

# Queue names
CELERY_QUEUE_HIGH_PRIORITY = "high"
CELERY_QUEUE_DEFAULT = "default"
CELERY_QUEUE_LOW_PRIORITY = "low"

# Task routing (which tasks go to which queues)
CELERY_TASK_ROUTING = {
    "app.tasks.metadata_tasks.extract_metadata_task": {"queue": "default"},
    "app.tasks.script_tasks.generate_script_task": {"queue": "high"},
    "app.tasks.tts_tasks.generate_tts_task": {"queue": "default"},
    "app.tasks.asset_tasks.gather_assets_task": {"queue": "default"},
    "app.tasks.video_tasks.compose_video_task": {"queue": "low"},  # CPU-intensive
    "app.tasks.export_tasks.export_video_task": {"queue": "low"},   # CPU-intensive
}

# Celery retry configuration
CELERY_RETRY_BACKOFF_MAX = 600  # 10 minutes max backoff
CELERY_RETRY_BACKOFF_BASE = 2  # Exponential base

# ========== Rate Limiting Configuration ==========

# Jobs per IP address per minute
RATE_LIMIT_JOBS_PER_IP = 10

# API request timeout
API_REQUEST_TIMEOUT_SECONDS = 30

# ========== IMDb Configuration ==========

# IMDb scraper settings
IMDB_REQUEST_TIMEOUT = 30
IMDB_RETRY_ATTEMPTS = 3
IMDB_BACKOFF_FACTOR = 1.5
IMDB_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# ========== Logging Configuration ==========

LOG_LEVEL = "INFO"

# Structured logging field names
LOG_FIELD_JOB_ID = "job_id"
LOG_FIELD_STAGE = "stage"
LOG_FIELD_STATUS = "status"
LOG_FIELD_ERROR = "error"
LOG_FIELD_DURATION_MS = "duration_ms"

# ========== Email/Alert Configuration ==========

# Email alerts for permanent failures
ALERT_ON_PERMANENT_FAILURE = True
ALERT_EMAIL_FROM = "noreply@movie2video.local"

# ========== Feature Flags ==========

# Enable/disable features
FEATURE_METADATA_CACHE = True
FEATURE_GPU_ACCELERATION = False  # NVIDIA NVENC support
FEATURE_WEBHOOK_NOTIFICATIONS = False  # For future WebSocket/Webhook support
FEATURE_COST_TRACKING = True
FEATURE_AUDIT_LOGGING = True

# ========== Debugging Configuration ==========

DEBUG_MODE = False
DEBUG_SKIP_EXTERNAL_CALLS = False  # For testing without calling real APIs
DEBUG_MOCK_VIDEO_PATH = None  # Use a mock video instead of generating
