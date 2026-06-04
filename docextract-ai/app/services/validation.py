"""Minimal validation engine — NO external API calls, ever.

Three checks only:
  1. GSTIN — basic format (is it 15 characters, ignoring whitespace).
  2. Duplicate invoice detection — does this (tenant, document_number,
     vendor_gstin, document_date) already exist?
  3. Amount reconciliation — does subtotal + (cgst + sgst + igst) ≈ grand_total
     (±1 rupee)?

All other "validation" (date parsing, GSTIN structure, GST-portal lookup, etc.)
has been intentionally removed. We extract whatever the OCR/LLM produces and
return it as-is.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.extraction import Extraction
from app.schemas.extraction import ExtractionData, ValidationResult

GSTIN_LENGTH = 15
AMOUNT_TOLERANCE = Decimal("1.0")


# ---------- 1. GSTIN basic format ----------

def is_valid_gstin(gstin: str) -> bool:
    """Return True iff the GSTIN string is exactly 15 characters after stripping
    surrounding whitespace. No structural / checksum / portal check.
    """
    if not gstin:
        return False
    return len(gstin.strip()) == GSTIN_LENGTH


# ---------- helpers ----------

def _to_decimal(value: str) -> Decimal | None:
    if value is None or value == "":
        return None
    s = str(value).replace(",", "").replace("₹", "").replace("Rs.", "").replace("INR", "")
    s = s.strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _field_value(d: dict[str, Any] | Any, key: str) -> str:
    if isinstance(d, dict):
        node = d.get(key)
        if isinstance(node, dict):
            return str(node.get("value", "") or "")
    return ""


# ---------- 3. Amount reconciliation ----------

def reconcile_amounts(data: dict[str, Any]) -> Tuple[bool, List[str]]:
    """Return (amounts_reconciled, errors).

    Rule: subtotal + (cgst + sgst + igst, OR total_tax if components missing)
    must equal grand_total within ±1.
    """
    errors: List[str] = []
    subtotal = _to_decimal(_field_value(data, "subtotal"))
    cgst = _to_decimal(_field_value(data, "cgst")) or Decimal("0")
    sgst = _to_decimal(_field_value(data, "sgst")) or Decimal("0")
    igst = _to_decimal(_field_value(data, "igst")) or Decimal("0")
    total_tax = _to_decimal(_field_value(data, "total_tax"))
    grand_total = _to_decimal(_field_value(data, "grand_total"))

    components_sum = cgst + sgst + igst
    effective_tax = (
        total_tax if total_tax is not None and components_sum == Decimal("0") else components_sum
    )

    if subtotal is None or grand_total is None:
        errors.append("missing_amounts: subtotal or grand_total absent")
        return False, errors

    expected = subtotal + effective_tax
    if abs(expected - grand_total) > AMOUNT_TOLERANCE:
        errors.append(
            f"amount_mismatch: subtotal+tax={expected} vs grand_total={grand_total}"
        )
        return False, errors

    return True, errors


# ---------- 2. Duplicate detection ----------

def detect_duplicate(
    db: Session,
    tenant_id: str,
    document_number: str,
    vendor_gstin: str,
    document_date: str,
    exclude_extraction_id: str | None = None,
) -> bool:
    if not (document_number and vendor_gstin and document_date):
        return False
    stmt = select(Extraction.id).where(
        Extraction.tenant_id == tenant_id,
        Extraction.document_number == document_number,
        Extraction.vendor_gstin == vendor_gstin,
        Extraction.document_date == document_date,
    )
    if exclude_extraction_id:
        stmt = stmt.where(Extraction.id != exclude_extraction_id)
    return db.execute(stmt.limit(1)).first() is not None


# ---------- Top-level aggregation ----------

def validate_extraction(
    data: dict[str, Any],
    *,
    db: Session | None = None,
    tenant_id: str | None = None,
    exclude_extraction_id: str | None = None,
) -> ValidationResult:
    errors: List[str] = []

    vendor_gstin = _field_value(data, "vendor_gstin")
    customer_gstin = _field_value(data, "customer_gstin")
    gstin_valid = True
    if vendor_gstin and not is_valid_gstin(vendor_gstin):
        gstin_valid = False
        errors.append(f"invalid_vendor_gstin_length: {vendor_gstin}")
    if customer_gstin and not is_valid_gstin(customer_gstin):
        gstin_valid = False
        errors.append(f"invalid_customer_gstin_length: {customer_gstin}")

    amounts_reconciled, amt_errors = reconcile_amounts(data)
    errors.extend(amt_errors)

    duplicate = False
    if db is not None and tenant_id is not None:
        duplicate = detect_duplicate(
            db,
            tenant_id=tenant_id,
            document_number=_field_value(data, "document_number"),
            vendor_gstin=vendor_gstin,
            document_date=_field_value(data, "document_date"),
            exclude_extraction_id=exclude_extraction_id,
        )
        if duplicate:
            errors.append("duplicate_detected")

    return ValidationResult(
        gstin_valid=gstin_valid,
        amounts_reconciled=amounts_reconciled,
        duplicate_detected=duplicate,
        errors=errors,
    )


def is_review_required(
    validation: ValidationResult, overall_confidence: float, threshold: float = 0.85
) -> Tuple[bool, str]:
    reasons: List[str] = []
    if overall_confidence < threshold:
        reasons.append(f"low_confidence:{overall_confidence:.2f}")
    if not validation.amounts_reconciled:
        reasons.append("amounts_not_reconciled")
    if not validation.gstin_valid:
        reasons.append("invalid_gstin")
    if validation.duplicate_detected:
        reasons.append("duplicate")
    return (bool(reasons), ",".join(reasons))


def normalize_extraction(data: dict[str, Any]) -> ExtractionData:
    """Coerce LLM output into ExtractionData; missing keys -> defaults."""
    try:
        return ExtractionData.model_validate(data)
    except Exception:
        return ExtractionData()
