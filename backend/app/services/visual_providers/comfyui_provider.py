"""ComfyUI visual provider for local Stable Diffusion image generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple
import random
import time
import uuid

import requests

from app.config import settings
from app.core.error_handling import RetryableError
from app.services.visual_providers.base import SceneVisualRequest, SceneVisualResult, build_scene_prompt


class ComfyUIVisualProvider:
    """Generate scene images through ComfyUI's HTTP API."""

    source_type = "stable_diffusion_comfyui"

    def __init__(self) -> None:
        self.base_url = settings.COMFYUI_BASE_URL.rstrip("/")
        self.timeout_seconds = settings.COMFYUI_TIMEOUT_SECONDS

    def generate_scene_visual(self, request: SceneVisualRequest) -> SceneVisualResult:
        prompt = build_scene_prompt(request)
        width, height = self._parse_size(settings.AI_IMAGE_SIZE)
        seed = random.randint(1, 2**31 - 1)
        filename_prefix = f"{request.job_id}_scene_{request.scene_number}"
        workflow = self._build_txt2img_workflow(
            prompt=prompt,
            width=width,
            height=height,
            seed=seed,
            filename_prefix=filename_prefix,
        )

        prompt_id = self._queue_prompt(workflow)
        output_info = self._wait_for_output(prompt_id)
        image_path = self._download_output(output_info, request.job_id, request.scene_number)

        return SceneVisualResult(
            path=image_path,
            source_type=self.source_type,
            prompt=prompt,
            provider_metadata={
                "model": settings.AI_IMAGE_MODEL,
                "prompt_id": prompt_id,
                "seed": seed,
                "checkpoint": settings.COMFYUI_CHECKPOINT,
                "size": f"{width}x{height}",
            },
        )

    def _queue_prompt(self, workflow: Dict[str, Any]) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow, "client_id": str(uuid.uuid4())},
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise RetryableError(f"ComfyUI prompt submission failed: {str(e)}")

        prompt_id = response.json().get("prompt_id")
        if not prompt_id:
            raise RetryableError("ComfyUI did not return a prompt_id")
        return str(prompt_id)

    def _wait_for_output(self, prompt_id: str) -> Dict[str, Any]:
        deadline = time.time() + self.timeout_seconds
        last_payload: Dict[str, Any] = {}

        while time.time() < deadline:
            try:
                response = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=10)
                response.raise_for_status()
            except requests.RequestException as e:
                raise RetryableError(f"ComfyUI history polling failed: {str(e)}")

            last_payload = response.json()
            prompt_history = last_payload.get(prompt_id) or {}
            outputs = prompt_history.get("outputs") or {}
            for node_output in outputs.values():
                images = node_output.get("images") or []
                if images:
                    return images[0]

            time.sleep(2)

        raise RetryableError(f"ComfyUI timed out after {self.timeout_seconds}s: {last_payload}")

    def _download_output(self, output_info: Dict[str, Any], job_id: str, scene_number: int) -> str:
        params = {
            "filename": output_info.get("filename"),
            "subfolder": output_info.get("subfolder", ""),
            "type": output_info.get("type", "output"),
        }
        if not params["filename"]:
            raise RetryableError(f"ComfyUI output missing filename: {output_info}")

        try:
            response = requests.get(f"{self.base_url}/view", params=params, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            raise RetryableError(f"ComfyUI image download failed: {str(e)}")

        output_dir = Path(settings.LOCAL_STORAGE_PATH) / "assets" / "ai_images"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{job_id}_scene_{scene_number}.png"
        output_path.write_bytes(response.content)
        return str(output_path)

    @staticmethod
    def _parse_size(size: str) -> Tuple[int, int]:
        try:
            width_text, height_text = size.lower().split("x", 1)
            return int(width_text), int(height_text)
        except Exception as e:
            raise RetryableError(f"Invalid AI_IMAGE_SIZE '{size}', expected WIDTHxHEIGHT: {str(e)}")

    @staticmethod
    def _build_txt2img_workflow(
        *,
        prompt: str,
        width: int,
        height: int,
        seed: int,
        filename_prefix: str,
    ) -> Dict[str, Any]:
        return {
            "3": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": settings.COMFYUI_CHECKPOINT},
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["3", 1]},
            },
            "5": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": settings.COMFYUI_NEGATIVE_PROMPT,
                    "clip": ["3", 1],
                },
            },
            "6": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "7": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": settings.COMFYUI_STEPS,
                    "cfg": settings.COMFYUI_CFG,
                    "sampler_name": settings.COMFYUI_SAMPLER,
                    "scheduler": settings.COMFYUI_SCHEDULER,
                    "denoise": 1.0,
                    "model": ["3", 0],
                    "positive": ["4", 0],
                    "negative": ["5", 0],
                    "latent_image": ["6", 0],
                },
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["7", 0], "vae": ["3", 2]},
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]},
            },
        }
