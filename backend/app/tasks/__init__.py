"""
Tasks module - Async task definitions for Celery

Structure:
  metadata_tasks.py - Stage 1: Extract IMDb metadata
  script_tasks.py - Stage 2: Generate script via OpenAI
  tts_tasks.py - Stage 3: Generate voiceover (TTS)
  asset_tasks.py - Stage 4: Gather visual assets
  video_tasks.py - Stage 5: Compose video with FFmpeg
  export_tasks.py - Stage 6: Export final MP4

Each task:
  ✓ Maps to one pipeline stage
  ✓ Handles errors (retryable vs permanent)
  ✓ Logs to ExecutionLog
  ✓ Calls JobCoordinator.transition_to_next_stage()
  ✓ Enqueues next task on success
"""

from app.tasks.celery_app import celery_app

__all__ = ["celery_app"]
