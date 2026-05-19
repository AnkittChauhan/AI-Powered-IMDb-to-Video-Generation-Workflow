"""TTSService for voiceover + subtitle generation."""

from __future__ import annotations

from typing import Any, Dict, List
import re

from openai import OpenAI

from app.config import settings
from app.core.error_handling import PermanentError, RetryableError
from app.services.storage_service import StorageService


class TTSService:
    """Generate speech audio and lightweight subtitle timeline."""

    @staticmethod
    def generate_voiceover(script_text: str, job_id: str) -> Dict[str, Any]:
        text = (script_text or "").strip()
        if not text:
            raise PermanentError("Cannot generate TTS: script is empty")
        if len(text) > settings.TTS_MAX_CHARACTERS:
            text = text[: settings.TTS_MAX_CHARACTERS]

        audio_bytes = TTSService._call_tts(text)
        audio_path = StorageService.audio_path(job_id)
        audio_path.write_bytes(audio_bytes)

        subtitles = TTSService.generate_subtitles(text)
        return {
            "audio_path": str(audio_path),
            "subtitles": subtitles,
            "duration_seconds": subtitles[-1]["end"] if subtitles else 0.0,
        }

    @staticmethod
    def generate_subtitles(script_text: str, words_per_second: float = 2.8) -> List[Dict[str, Any]]:
        lines = [line.strip() for line in re.split(r"\n\s*\n", script_text) if line.strip()]
        if not lines:
            lines = [script_text.strip()]

        subtitles: List[Dict[str, Any]] = []
        cursor = 0.0
        for idx, line in enumerate(lines, start=1):
            word_count = max(1, len(line.split()))
            duration = max(1.2, word_count / words_per_second)
            start = round(cursor, 2)
            end = round(cursor + duration, 2)
            subtitles.append(
                {
                    "index": idx,
                    "start": start,
                    "end": end,
                    "text": line,
                }
            )
            cursor = end
        return subtitles

    @staticmethod
    def _call_tts(text: str) -> bytes:
        provider = (settings.TTS_PROVIDER or "kokoro").lower()
        if provider == "kokoro":
            return TTSService._call_openai_compatible_tts(
                text=text,
                provider="Kokoro",
                api_key=settings.KOKORO_TTS_API_KEY or "not-needed",
                base_url=settings.KOKORO_TTS_BASE_URL,
                model=settings.KOKORO_TTS_MODEL,
                voice=settings.KOKORO_TTS_VOICE,
                response_format=settings.KOKORO_TTS_FORMAT,
                speed=settings.KOKORO_TTS_SPEED,
            )
        if provider == "openai":
            return TTSService._call_openai_tts(text)
        raise PermanentError(f"Unsupported TTS_PROVIDER: {provider}")

    @staticmethod
    def _call_openai_tts(text: str) -> bytes:
        if not settings.OPENAI_API_KEY:
            raise PermanentError("OPENAI_API_KEY is not configured")

        return TTSService._call_openai_compatible_tts(
            text=text,
            provider="OpenAI",
            api_key=settings.OPENAI_API_KEY,
            base_url=None,
            model=settings.OPENAI_TTS_MODEL,
            voice=settings.OPENAI_TTS_VOICE,
            response_format="mp3",
            speed=1.0,
        )

    @staticmethod
    def _call_openai_compatible_tts(
        *,
        text: str,
        provider: str,
        api_key: str,
        base_url: str | None,
        model: str,
        voice: str,
        response_format: str,
        speed: float,
    ) -> bytes:
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url.rstrip("/")

        client = OpenAI(**client_kwargs)
        try:
            response = client.audio.speech.create(
                model=model,
                voice=voice,
                input=text,
                response_format=response_format,
                speed=speed,
            )
        except Exception as e:
            status_code = getattr(e, "status_code", None)
            message = str(e)
            if "insufficient_quota" in message:
                raise PermanentError(f"{provider} TTS quota exhausted: {message}")
            if status_code in (400, 401, 403, 404):
                raise PermanentError(f"{provider} TTS request failed: {message}")
            if status_code in (408, 409, 429, 500, 502, 503, 504):
                raise RetryableError(f"{provider} TTS temporary failure: {message}")
            lowered = message.lower()
            if "timeout" in lowered or "timed out" in lowered or "connection" in lowered:
                raise RetryableError(f"{provider} TTS connectivity issue: {message}")
            raise RetryableError(f"{provider} TTS request failed: {message}")

        if hasattr(response, "content") and response.content:
            return response.content
        if hasattr(response, "read"):
            return response.read()
        if hasattr(response, "to_bytes"):
            return response.to_bytes()
        raise PermanentError(f"{provider} TTS returned unsupported response format")


__all__ = ["TTSService"]
