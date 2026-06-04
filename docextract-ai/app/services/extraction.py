"""LLM extraction service — Google Gemini Flash."""
from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

import google.generativeai as genai

from app.core.config import settings
from app.core.logging import get_logger
from app.prompts.extraction import (
    SYSTEM_PROMPT,
    build_correction_prompt,
    build_user_prompt,
    detect_document_type,
)

log = get_logger("extraction")

# Configure the SDK once at import time. ``configure`` is idempotent and reads
# the key from settings (loaded from GEMINI_API_KEY env var).
_API_KEY = settings.gemini_api_key or os.getenv("GEMINI_API_KEY", "")
if _API_KEY:
    genai.configure(api_key=_API_KEY)


class LLMError(Exception):
    """Raised when the LLM call or JSON parsing fails."""


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _strip_json_envelope(text: str) -> str:
    text = text.strip()
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        return fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


class ExtractionService:
    def __init__(self) -> None:
        self.model_name = settings.llm_model

    # ---------- Provider call ----------

    def _build_model(self, system: str) -> genai.GenerativeModel:
        return genai.GenerativeModel(
            self.model_name,
            system_instruction=system,
            generation_config={
                "temperature": 0.0,
                "max_output_tokens": 4096,
                "response_mime_type": "application/json",
            },
        )

    async def _llm_call(self, system: str, user: str) -> str:
        model = self._build_model(system)
        response = await asyncio.to_thread(model.generate_content, user)
        return response.text or ""

    # ---------- Public API ----------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(LLMError),
        reraise=True,
    )
    async def extract(self, ocr_text: str, hints: str = "") -> dict[str, Any]:
        document_type_hint = detect_document_type(ocr_text)
        if document_type_hint != "UNKNOWN":
            log.info("document_type_pre_classified", type=document_type_hint)
        user_prompt = build_user_prompt(
            ocr_text, hints, document_type_hint=document_type_hint
        )
        try:
            raw = await self._llm_call(SYSTEM_PROMPT, user_prompt)
        except Exception as exc:
            log.warning("llm_call_failed", error=str(exc))
            raise LLMError(str(exc)) from exc

        payload = _strip_json_envelope(raw)
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            log.warning("llm_json_parse_failed", error=str(exc), sample=payload[:200])
            raise LLMError(f"invalid_json: {exc}") from exc

        if not isinstance(data, dict):
            raise LLMError("llm_returned_non_object")
        return data

    async def correct(self, ocr_text: str, errors: list[str]) -> dict[str, Any]:
        user_prompt = build_correction_prompt(ocr_text, errors)
        try:
            raw = await self._llm_call(SYSTEM_PROMPT, user_prompt)
        except Exception as exc:
            raise LLMError(str(exc)) from exc
        try:
            return json.loads(_strip_json_envelope(raw))
        except json.JSONDecodeError as exc:
            raise LLMError(f"invalid_json_on_correction: {exc}") from exc


extraction_service = ExtractionService()
