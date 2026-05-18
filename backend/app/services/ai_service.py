"""AIService for narration script generation using OpenAI."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
import logging
import re

from openai import OpenAI

from app.config import settings
from app.core.error_handling import PermanentError, RetryableError
from app.utils.constants import (
    OPENAI_CHAT_MODEL,
    OPENAI_TEXT_PRICE_PER_1K_TOKENS,
    SCRIPT_GENERATION_MAX_TOKENS,
    SCRIPT_GENERATION_PROMPT_TOKENS_BUDGET,
)

logger = logging.getLogger(__name__)


class AIService:
    """Generates cinematic 2-minute narration scripts from movie metadata."""

    @staticmethod
    def generate_script(movie_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Generate narration script + storyboard scenes + token/cost data."""
        title = (movie_metadata.get("title") or "").strip()
        plot = (movie_metadata.get("plot") or "").strip()
        genres = movie_metadata.get("genres") or []
        cast = movie_metadata.get("cast") or []
        runtime = movie_metadata.get("runtime_minutes")

        if not title:
            raise PermanentError("Missing required metadata: title")
        if not plot:
            raise PermanentError("Missing required metadata: plot")

        trimmed_plot = AIService._trim_plot_for_budget(plot)
        prompt = AIService._build_prompt(
            title=title,
            plot=trimmed_plot,
            genres=genres,
            cast=cast,
            runtime_minutes=runtime,
        )

        script_text, usage = AIService._call_openai(prompt)
        normalized_script = AIService._normalize_script(script_text)
        scenes = AIService.split_script_into_scenes(normalized_script)
        cost_usd = AIService.calculate_cost(usage.get("total_tokens", 0))

        return {
            "script_text": normalized_script,
            "scenes": scenes,
            "usage": usage,
            "cost_usd": cost_usd,
        }

    @staticmethod
    def split_script_into_scenes(script_text: str, target_scenes: int = 8) -> List[str]:
        """Split script into storyboard scenes."""
        scene_pattern = re.compile(r"(?im)^scene\s+\d+[:\-]?\s*")
        if scene_pattern.search(script_text):
            chunks = [c.strip() for c in re.split(scene_pattern, script_text) if c.strip()]
            return chunks[:target_scenes]

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", script_text) if p.strip()]
        if len(paragraphs) >= 3:
            return paragraphs[:target_scenes]

        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", script_text) if s.strip()]
        if not sentences:
            return [script_text.strip()]

        bucket_size = max(1, len(sentences) // target_scenes)
        scenes: List[str] = []
        for i in range(0, len(sentences), bucket_size):
            scenes.append(" ".join(sentences[i : i + bucket_size]))
        return scenes[:target_scenes]

    @staticmethod
    def calculate_cost(total_tokens: int) -> float:
        """Estimate generation cost in USD from token usage."""
        if total_tokens <= 0:
            return 0.0
        return round((total_tokens / 1000.0) * OPENAI_TEXT_PRICE_PER_1K_TOKENS, 6)

    @staticmethod
    def _build_prompt(
        *,
        title: str,
        plot: str,
        genres: List[str],
        cast: List[str],
        runtime_minutes: Any,
    ) -> str:
        genres_text = ", ".join(genres[:5]) if genres else "Unknown"
        cast_text = ", ".join(cast[:6]) if cast else "Unknown"
        runtime_text = str(runtime_minutes) if runtime_minutes else "Unknown"

        return (
            "You are a cinematic script writer for a 2-minute narrated movie recap video.\n"
            "Write a compelling narration script in 8 short scenes.\n"
            "Each scene should be vivid, concise, and video-friendly.\n"
            "Output plain text with scene headers like 'Scene 1:' ... 'Scene 8:'.\n\n"
            f"Movie title: {title}\n"
            f"Genres: {genres_text}\n"
            f"Cast: {cast_text}\n"
            f"Runtime: {runtime_text} minutes\n\n"
            f"Plot:\n{plot}\n"
        )

    @staticmethod
    def _trim_plot_for_budget(plot: str) -> str:
        estimated_tokens = AIService._estimate_tokens(plot)
        if estimated_tokens <= SCRIPT_GENERATION_PROMPT_TOKENS_BUDGET:
            return plot

        # Conservative truncation to stay under prompt budget.
        char_budget = int(len(plot) * (SCRIPT_GENERATION_PROMPT_TOKENS_BUDGET / estimated_tokens))
        return plot[: max(500, char_budget)].strip()

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        # Approximation: ~1.3 tokens per word for English text.
        words = max(1, len(text.split()))
        return int(words * 1.3)

    @staticmethod
    def _normalize_script(text: str) -> str:
        cleaned = text.replace("\r\n", "\n").strip()
        if not cleaned:
            raise PermanentError("OpenAI returned empty script")
        return cleaned

    @staticmethod
    def _call_openai(prompt: str) -> Tuple[str, Dict[str, int]]:
        if not settings.OPENAI_API_KEY:
            raise PermanentError("OPENAI_API_KEY is not configured")

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        try:
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL or OPENAI_CHAT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You write concise, cinematic narration scripts.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=min(settings.OPENAI_MAX_TOKENS, SCRIPT_GENERATION_MAX_TOKENS),
            )
        except Exception as e:  # OpenAI SDK errors vary by version.
            status_code = getattr(e, "status_code", None)
            message = str(e)
            if status_code in (400, 401, 403, 404):
                raise PermanentError(f"OpenAI request failed: {message}")
            if status_code in (408, 409, 429, 500, 502, 503, 504):
                raise RetryableError(f"OpenAI temporary failure: {message}")
            lowered = message.lower()
            if "timeout" in lowered or "timed out" in lowered or "connection" in lowered:
                raise RetryableError(f"OpenAI connectivity issue: {message}")
            raise RetryableError(f"OpenAI request failed: {message}")

        if not response.choices or not response.choices[0].message:
            raise PermanentError("OpenAI returned no choices")

        content = response.choices[0].message.content or ""
        usage_obj = getattr(response, "usage", None)
        usage = {
            "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage_obj, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage_obj, "total_tokens", 0) or 0,
        }
        logger.info("OpenAI script generation complete", extra={"usage": usage})
        return content, usage


__all__ = ["AIService"]
