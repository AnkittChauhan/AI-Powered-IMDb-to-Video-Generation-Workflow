"""
Application configuration
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # API
    API_TITLE: str = "IMDb Video Generator"
    API_VERSION: str = "0.1.0"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # Database
    DATABASE_URL: str = "sqlite:///./imdb_video.db"
    SQLALCHEMY_ECHO: bool = False
    
    # Redis & Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
    # Metadata Cache
    METADATA_CACHE_TTL_SECONDS: int = 2592000  # 30 days
    METADATA_WORKER_CONCURRENCY: int = 2
    ADMIN_TOKEN: str = "secret-admin-token-change-in-prod"
    
    # OpenAI
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_MAX_TOKENS: int = 500
    OPENAI_TTS_MODEL: str = "gpt-4o-mini-tts"
    OPENAI_TTS_VOICE: str = "alloy"

    # TTS provider. Uses "kokoro" for local Docker TTS or "openai" for hosted TTS.
    TTS_PROVIDER: str = "kokoro"
    TTS_MAX_CHARACTERS: int = 2000

    # Kokoro FastAPI (OpenAI-compatible local speech endpoint)
    KOKORO_TTS_BASE_URL: str = "http://kokoro_tts:8880/v1"
    KOKORO_TTS_API_KEY: str = "not-needed"
    KOKORO_TTS_MODEL: str = "kokoro"
    KOKORO_TTS_VOICE: str = "af_sky"
    KOKORO_TTS_FORMAT: str = "mp3"
    KOKORO_TTS_SPEED: float = 1.0

    # OpenRouter (OpenAI-compatible chat completions)
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "openrouter/owl-alpha"
    
    # File Storage
    STORAGE_TYPE: str = "local"  # local or s3
    LOCAL_STORAGE_PATH: str = "/tmp/imdb_video_storage"
    
    # Job Configuration
    JOB_TIMEOUT_SECONDS: int = 3600
    MAX_RETRIES_PER_STAGE: dict = {
        "metadata_extraction": 3,
        "script_generation": 5,
        "tts_subtitles": 3,
        "asset_gathering": 2,
        "video_composition": 1,
        "export": 2,
    }
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


settings = Settings()
