"""Tests for the minimal validation engine.

Three checks only:
  1. GSTIN — 15-character format check (no structure / no portal lookup)
  2. Duplicate detection
  3. Amount reconciliation (subtotal + tax ≈ grand_total within ±1)
"""
from __future__ import annotations

from app.services.validation import (
    is_valid_gstin,
    reconcile_amounts,
    validate_extraction,
)


def _wrap(d: dict) -> dict:
    return {k: {"value": str(v), "confidence": 0.99} for k, v in d.items()}


# ---------- 1. GSTIN — 15-char only ----------


def test_gstin_valid_when_exactly_15_chars():
    assert is_valid_gstin("27AABCU9603R1ZX") is True
    assert is_valid_gstin("29AAACX1234D1Z5") is True
    # Structure is no longer validated — any 15 chars passes.
    assert is_valid_gstin("ABCDEFGHIJKLMNO") is True
    assert is_valid_gstin("123456789012345") is True


def test_gstin_invalid_when_wrong_length():
    assert is_valid_gstin("") is False
    assert is_valid_gstin("27AABCU9603R1Z") is False  # 14 chars
    assert is_valid_gstin("27AABCU9603R1ZXX") is False  # 16 chars
    assert is_valid_gstin("INVALID") is False


def test_gstin_whitespace_is_stripped_before_length_check():
    assert is_valid_gstin("  27AABCU9603R1ZX  ") is True
    assert is_valid_gstin("  27AABCU9603R1Z  ") is False  # 14 inner chars


# ---------- 3. Amount reconciliation ----------


def test_amounts_reconcile_ok_with_components():
    data = _wrap(
        {
            "subtotal": "3700.00",
            "cgst": "333.00",
            "sgst": "333.00",
            "igst": "0.00",
            "grand_total": "4366.00",
        }
    )
    ok, errors = reconcile_amounts(data)
    assert ok is True
    assert errors == []


def test_amounts_reconcile_uses_total_tax_when_components_absent():
    data = _wrap(
        {
            "subtotal": "3700.00",
            "total_tax": "666.00",
            "grand_total": "4366.00",
        }
    )
    ok, errors = reconcile_amounts(data)
    assert ok is True
    assert errors == []


def test_amounts_reconcile_fails_on_grand_total_mismatch():
    data = _wrap(
        {
            "subtotal": "3000.00",
            "cgst": "333.00",
            "sgst": "333.00",
            "igst": "0.00",
            "grand_total": "5000.00",  # off by 1334
        }
    )
    ok, errors = reconcile_amounts(data)
    assert ok is False
    assert any("amount_mismatch" in e for e in errors)


def test_amounts_reconcile_fails_when_amounts_missing():
    ok, errors = reconcile_amounts(_wrap({"grand_total": "100.00"}))
    assert ok is False
    assert any("missing_amounts" in e for e in errors)


def test_amounts_reconcile_within_tolerance():
    # Off by 0.5 — within ±1 tolerance
    data = _wrap(
        {
            "subtotal": "100.00",
            "cgst": "9.00",
            "sgst": "9.00",
            "grand_total": "118.50",
        }
    )
    ok, _ = reconcile_amounts(data)
    assert ok is True


# ---------- Aggregate validate_extraction ----------


def test_validate_extraction_returns_only_three_fields():
    """ValidationResult exposes exactly the agreed surface — no date_valid,
    no tax_reconciled, no external-lookup fields."""
    result = validate_extraction(
        _wrap(
            {
                "vendor_gstin": "27AABCU9603R1ZX",
                "customer_gstin": "29AAACX1234D1Z5",
                "subtotal": "3700.00",
                "cgst": "333.00",
                "sgst": "333.00",
                "grand_total": "4366.00",
            }
        )
    )
    # Surface check
    fields = set(result.model_dump().keys())
    assert fields == {
        "gstin_valid",
        "amounts_reconciled",
        "duplicate_detected",
        "errors",
    }
    assert result.gstin_valid is True
    assert result.amounts_reconciled is True
    assert result.duplicate_detected is False
    assert result.errors == []


def test_validate_extraction_flags_bad_gstin_length():
    result = validate_extraction(
        _wrap(
            {
                "vendor_gstin": "TOOSHORT",
                "subtotal": "100",
                "grand_total": "100",
            }
        )
    )
    assert result.gstin_valid is False
    assert any("invalid_vendor_gstin_length" in e for e in result.errors)


def test_validate_extraction_empty_gstin_is_not_flagged():
    """Absent GSTIN should not produce gstin_valid=False — only malformed values do."""
    result = validate_extraction(
        _wrap(
            {
                "vendor_gstin": "",
                "customer_gstin": "",
                "subtotal": "100",
                "grand_total": "100",
            }
        )
    )
    assert result.gstin_valid is True
