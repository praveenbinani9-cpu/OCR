from __future__ import annotations

import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_api_key,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("Secret!123")
    assert verify_password("Secret!123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_jwt_create_and_decode():
    token = create_access_token(subject="user-1", tenant_id="tenant-1", role="admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-1"
    assert payload["tenant_id"] == "tenant-1"
    assert payload["role"] == "admin"
    assert "exp" in payload


def test_jwt_invalid_raises():
    with pytest.raises(ValueError):
        decode_access_token("not-a-jwt")


def test_api_key_format_and_verify():
    key = generate_api_key()
    assert key.startswith("dx_")
    hashed = hash_api_key(key)
    assert verify_api_key(key, hashed) is True
    assert verify_api_key("dx_wrong", hashed) is False
