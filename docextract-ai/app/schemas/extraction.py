from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class FieldValue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    value: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ExtractionItem(BaseModel):
    description: FieldValue = FieldValue()
    hsn: FieldValue = FieldValue()
    qty: FieldValue = FieldValue()
    rate: FieldValue = FieldValue()
    amount: FieldValue = FieldValue()


class ExtractionData(BaseModel):
    vendor_name: FieldValue = FieldValue()
    vendor_gstin: FieldValue = FieldValue()
    customer_name: FieldValue = FieldValue()
    customer_gstin: FieldValue = FieldValue()
    document_number: FieldValue = FieldValue()
    document_date: FieldValue = FieldValue()
    subtotal: FieldValue = FieldValue()
    cgst: FieldValue = FieldValue()
    sgst: FieldValue = FieldValue()
    igst: FieldValue = FieldValue()
    total_tax: FieldValue = FieldValue()
    grand_total: FieldValue = FieldValue()
    items: List[ExtractionItem] = Field(default_factory=list)


class ValidationResult(BaseModel):
    gstin_valid: bool = True
    amounts_reconciled: bool = True
    duplicate_detected: bool = False
    errors: List[str] = Field(default_factory=list)


class ExtractionResponse(BaseModel):
    status: str = "success"
    document_id: str
    document_type: str = "UNKNOWN"
    overall_confidence: float = 0.0
    processing_time_ms: int = 0
    data: ExtractionData = ExtractionData()
    validation: ValidationResult = ValidationResult()
    review_required: bool = False
