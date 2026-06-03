"""LLM extraction service. Supports Emergent Universal LLM Key and direct Anthropic SDK."""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger
from app.prompts.extraction import (
    SYSTEM_PROMPT,
    build_correction_prompt,
    build_user_prompt,
)

log = get_logger("extraction")


class LLMError(Exception):
    """Raised when the LLM call or JSON parsing fails."""


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _strip_json_envelope(text: str) -> str:
    text = text.strip()
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        return fence.group(1)
    # Greedy slice between first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


class ExtractionService:
    def __init__(self) -> None:
        self.provider = settings.llm_provider.lower()
        self.model = settings.llm_model

    # ---------- Provider calls ----------

    async def _call_emergent(self, system: str, user: str) -> str:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # lazy

        chat = LlmChat(
            api_key=settings.emergent_llm_key,
            session_id=f"docextract-{uuid.uuid4()}",
            system_message=system,
        ).with_model("anthropic", self.model)
        # Force deterministic JSON
        try:
            chat = chat.with_params(temperature=0.0, max_tokens=4096)
        except Exception:
            pass
        response = await chat.send_message(UserMessage(text=user))
        return str(response)

    async def _call_anthropic(self, system: str, user: str) -> str:
        from anthropic import Anthropic  # lazy

        client = Anthropic(api_key=settings.anthropic_api_key)
        # SDK is sync; run in thread.
        def _do() -> str:
            resp = client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0.0,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
            return "".join(parts)

        return await asyncio.to_thread(_do)

    async def _llm_call(self, system: str, user: str) -> str:
        if self.provider == "anthropic" and settings.anthropic_api_key:
            return await self._call_anthropic(system, user)
        return await self._call_emergent(system, user)

    # ---------- Public API ----------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(LLMError),
        reraise=True,
    )
    async def extract(self, ocr_text: str, hints: str = "") -> dict[str, Any]:
        user_prompt = build_user_prompt(ocr_text, hints)
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
