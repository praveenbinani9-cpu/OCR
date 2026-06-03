from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.extraction import ExtractionService, LLMError, _strip_json_envelope
from tests.fixtures.sample_invoice import SAMPLE_INVOICE_EXTRACTED, SAMPLE_INVOICE_OCR_TEXT


def test_strip_json_envelope_handles_markdown_fence():
    raw = '```json\n{"a":1}\n```'
    assert _strip_json_envelope(raw) == '{"a":1}'


def test_strip_json_envelope_handles_plain_object():
    raw = 'noise {"a":1} trailing'
    assert _strip_json_envelope(raw) == '{"a":1}'


def test_extraction_parses_clean_json():
    svc = ExtractionService()
    with patch.object(svc, "_llm_call", new=AsyncMock(return_value=json.dumps(SAMPLE_INVOICE_EXTRACTED))):
        result = asyncio.run(svc.extract(SAMPLE_INVOICE_OCR_TEXT))
    assert result["document_type"] == "TAX_INVOICE"
    assert result["data"]["vendor_gstin"]["value"] == "27AABCU9603R1ZX"


def test_extraction_retries_on_invalid_json():
    svc = ExtractionService()
    calls = {"n": 0}

    async def flaky(_sys, _user):
        calls["n"] += 1
        if calls["n"] < 2:
            return "not-json"
        return json.dumps(SAMPLE_INVOICE_EXTRACTED)

    with patch.object(svc, "_llm_call", new=flaky):
        result = asyncio.run(svc.extract(SAMPLE_INVOICE_OCR_TEXT))
    assert calls["n"] == 2
    assert result["data"]["grand_total"]["value"] == "4366.00"


def test_extraction_raises_after_max_retries():
    svc = ExtractionService()
    with patch.object(svc, "_llm_call", new=AsyncMock(return_value="garbage-not-json")):
        with pytest.raises(LLMError):
            asyncio.run(svc.extract(SAMPLE_INVOICE_OCR_TEXT))
