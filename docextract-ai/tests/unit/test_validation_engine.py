from __future__ import annotations

from app.services.validation import (
    is_valid_gstin,
    parse_date,
    reconcile_amounts,
    validate_extraction,
)


def _wrap(d: dict) -> dict:
    return {k: {"value": str(v), "confidence": 0.99} for k, v in d.items()}


def test_gstin_valid_format():
    assert is_valid_gstin("27AABCU9603R1ZX") is True
    assert is_valid_gstin("29AAACX1234D1Z5") is True


def test_gstin_invalid_format():
    assert is_valid_gstin("") is False
    assert is_valid_gstin("INVALID-GSTIN") is False
    assert is_valid_gstin("27AABCU9603R1Z") is False  # too short
    # GSTIN matching is case-insensitive (uppercased before regex)
    assert is_valid_gstin("27aabcu9603r1zx") is True


def test_parse_date_formats():
    assert parse_date("12/01/2026").isoformat() == "2026-01-12"
    assert parse_date("12-01-2026").isoformat() == "2026-01-12"
    assert parse_date("2026-01-12").isoformat() == "2026-01-12"
    assert parse_date("invalid") is None
    assert parse_date("") is None


def test_amounts_reconcile_ok():
    data = _wrap(
        {
            "subtotal": "3700.00",
            "cgst": "333.00",
            "sgst": "333.00",
            "igst": "0.00",
            "total_tax": "666.00",
            "grand_total": "4366.00",
        }
    )
    amounts_ok, tax_ok, errors = reconcile_amounts(data)
    assert amounts_ok is True
    assert tax_ok is True
    assert errors == []


def test_amounts_reconcile_tax_mismatch():
    data = _wrap(
        {
            "subtotal": "3700.00",
            "cgst": "300.00",
            "sgst": "333.00",
            "igst": "0.00",
            "total_tax": "666.00",  # 300 + 333 = 633, not 666
            "grand_total": "4366.00",
        }
    )
    amounts_ok, tax_ok, errors = reconcile_amounts(data)
    assert tax_ok is False
    assert any("tax_mismatch" in e for e in errors)


def test_amounts_reconcile_grand_total_mismatch():
    data = _wrap(
        {
            "subtotal": "3000.00",
            "cgst": "333.00",
            "sgst": "333.00",
            "igst": "0.00",
            "total_tax": "666.00",
            "grand_total": "5000.00",  # off
        }
    )
    amounts_ok, _, errors = reconcile_amounts(data)
    assert amounts_ok is False
    assert any("amount_mismatch" in e for e in errors)


def test_validate_extraction_aggregates():
    data = _wrap(
        {
            "vendor_gstin": "27AABCU9603R1ZX",
            "customer_gstin": "29AAACX1234D1Z5",
            "document_date": "12/01/2026",
            "subtotal": "3700.00",
            "cgst": "333.00",
            "sgst": "333.00",
            "igst": "0.00",
            "total_tax": "666.00",
            "grand_total": "4366.00",
        }
    )
    result = validate_extraction(data)
    assert result.gstin_valid is True
    assert result.date_valid is True
    assert result.amounts_reconciled is True
    assert result.tax_reconciled is True
    assert result.errors == []
