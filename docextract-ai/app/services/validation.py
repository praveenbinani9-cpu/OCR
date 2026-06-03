"""GSTIN / date / amount validation for Indian GST documents."""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.extraction import Extraction
from app.schemas.extraction import ExtractionData, ValidationResult

GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")

_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y")

AMOUNT_TOLERANCE = Decimal("1.0")


def is_valid_gstin(gstin: str) -> bool:
    if not gstin:
        return False
    return bool(GSTIN_REGEX.match(gstin.strip().upper()))


def parse_date(value: str) -> date | None:
    if not value:
        return None
    value = value.strip()
    # ISO first
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


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


def reconcile_amounts(data: dict[str, Any]) -> Tuple[bool, bool, List[str]]:
    errors: List[str] = []
    subtotal = _to_decimal(_field_value(data, "subtotal"))
    cgst = _to_decimal(_field_value(data, "cgst")) or Decimal("0")
    sgst = _to_decimal(_field_value(data, "sgst")) or Decimal("0")
    igst = _to_decimal(_field_value(data, "igst")) or Decimal("0")
    total_tax = _to_decimal(_field_value(data, "total_tax"))
    grand_total = _to_decimal(_field_value(data, "grand_total"))

    tax_reconciled = True
    computed_tax = cgst + sgst + igst
    if total_tax is not None and computed_tax != Decimal("0"):
        if abs(total_tax - computed_tax) > AMOUNT_TOLERANCE:
            tax_reconciled = False
            errors.append(
                f"tax_mismatch: cgst+sgst+igst={computed_tax} vs total_tax={total_tax}"
            )

    amounts_reconciled = True
    effective_tax = total_tax if total_tax is not None else computed_tax
    if subtotal is not None and grand_total is not None:
        expected = subtotal + (effective_tax or Decimal("0"))
        if abs(expected - grand_total) > AMOUNT_TOLERANCE:
            amounts_reconciled = False
            errors.append(
                f"amount_mismatch: subtotal+tax={expected} vs grand_total={grand_total}"
            )
    elif subtotal is None or grand_total is None:
        amounts_reconciled = False
        errors.append("missing_amounts: subtotal or grand_total absent")

    return amounts_reconciled, tax_reconciled, errors


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
        errors.append(f"invalid_vendor_gstin: {vendor_gstin}")
    if customer_gstin and not is_valid_gstin(customer_gstin):
        gstin_valid = False
        errors.append(f"invalid_customer_gstin: {customer_gstin}")

    document_date_str = _field_value(data, "document_date")
    parsed_date = parse_date(document_date_str) if document_date_str else None
    date_valid = bool(parsed_date) if document_date_str else True
    if document_date_str and not parsed_date:
        errors.append(f"invalid_date: {document_date_str}")

    amounts_reconciled, tax_reconciled, amt_errors = reconcile_amounts(data)
    errors.extend(amt_errors)

    duplicate = False
    if db is not None and tenant_id is not None:
        duplicate = detect_duplicate(
            db,
            tenant_id=tenant_id,
            document_number=_field_value(data, "document_number"),
            vendor_gstin=vendor_gstin,
            document_date=document_date_str,
            exclude_extraction_id=exclude_extraction_id,
        )
        if duplicate:
            errors.append("duplicate_detected")

    return ValidationResult(
        gstin_valid=gstin_valid,
        date_valid=date_valid,
        amounts_reconciled=amounts_reconciled,
        tax_reconciled=tax_reconciled,
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
    if not validation.tax_reconciled:
        reasons.append("tax_not_reconciled")
    if not validation.gstin_valid:
        reasons.append("invalid_gstin")
    if not validation.date_valid:
        reasons.append("invalid_date")
    if validation.duplicate_detected:
        reasons.append("duplicate")
    return (bool(reasons), ",".join(reasons))


def normalize_extraction(data: dict[str, Any]) -> ExtractionData:
    """Coerce LLM output into ExtractionData; missing keys -> defaults."""
    try:
        return ExtractionData.model_validate(data)
    except Exception:
        # Build defensively
        return ExtractionData()
