"""Unit tests for webhook HMAC-SHA256 signing + verification."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from app.services.webhook import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    build_signature_header,
    post_webhook,
    verify_signature,
)


def test_sign_and_verify_roundtrip():
    body = b'{"document_id":"abc","grand_total":"1000"}'
    ts = str(int(time.time()))
    # Build a header manually using the same primitive used internally
    from app.services.webhook import _sign_payload

    sig = _sign_payload(ts, body, "whsec_test")
    header = build_signature_header(ts, sig)
    assert verify_signature(body, header, "whsec_test") is True


def test_verify_rejects_wrong_secret():
    body = b'{"a":1}'
    ts = str(int(time.time()))
    from app.services.webhook import _sign_payload

    sig = _sign_payload(ts, body, "whsec_real")
    header = build_signature_header(ts, sig)
    assert verify_signature(body, header, "whsec_wrong") is False


def test_verify_rejects_tampered_body():
    body = b'{"a":1}'
    ts = str(int(time.time()))
    from app.services.webhook import _sign_payload

    sig = _sign_payload(ts, body, "whsec_test")
    header = build_signature_header(ts, sig)
    assert verify_signature(b'{"a":2}', header, "whsec_test") is False


def test_verify_rejects_replay_outside_window():
    body = b'{"a":1}'
    old_ts = str(int(time.time()) - 10_000)  # 10000s in the past
    from app.services.webhook import _sign_payload

    sig = _sign_payload(old_ts, body, "whsec_test")
    header = build_signature_header(old_ts, sig)
    assert verify_signature(body, header, "whsec_test") is False


def test_verify_rejects_malformed_header():
    body = b'{"a":1}'
    assert verify_signature(body, "garbage", "whsec_test") is False
    assert verify_signature(body, "", "whsec_test") is False
    assert verify_signature(body, "t=,v1=", "whsec_test") is False


def test_post_webhook_signs_when_secret_present():
    captured = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, content=None, headers=None):
            captured["url"] = url
            captured["body"] = content
            captured["headers"] = headers
            return FakeResp()

    with patch("app.services.webhook.httpx.Client", FakeClient):
        post_webhook("https://example.test/hook", {"a": 1}, secret="whsec_test")

    assert SIGNATURE_HEADER in captured["headers"]
    assert TIMESTAMP_HEADER in captured["headers"]
    header_val = captured["headers"][SIGNATURE_HEADER]
    assert header_val.startswith("t=")
    assert ",v1=" in header_val
    # And the signature actually verifies
    assert verify_signature(captured["body"], header_val, "whsec_test") is True


def test_post_webhook_omits_signature_when_no_secret():
    captured = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, content=None, headers=None):
            captured["headers"] = headers
            return FakeResp()

    with patch("app.services.webhook.httpx.Client", FakeClient):
        post_webhook("https://example.test/hook", {"a": 1}, secret=None)

    assert SIGNATURE_HEADER not in captured["headers"]
    assert TIMESTAMP_HEADER not in captured["headers"]


# Keep imports used
_ = json, MagicMock, pytest
