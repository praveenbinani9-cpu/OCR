from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class FieldValue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    value: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ExtractionItem(BaseModel):
    description: FieldValue = FieldValue()
    hsn: FieldValue = FieldValue()
    qty: FieldValue = FieldValue()
    unit_measure: FieldValue = FieldValue()
    rate: FieldValue = FieldValue()
    amount: FieldValue = FieldValue()
    tax_rate: FieldValue = FieldValue()
    tax_amount: FieldValue = FieldValue()


class TaxItem(BaseModel):
    rate: str = ""
    base: str = ""
    amount: str = ""


class AddressField(BaseModel):
    address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = ""


class BankDetails(BaseModel):
    account_number: str = ""
    ifsc: str = ""
    iban: str = ""


class TransporterDetails(BaseModel):
    name: str = ""
    id: str = ""
    mode: str = ""
    vehicle_number: str = ""


class ExtractionData(BaseModel):
    model_config = ConfigDict(extra="allow")
    vendor_name: FieldValue = FieldValue()
    vendor_gstin: FieldValue = FieldValue()
    vendor_email: FieldValue = FieldValue()
    vendor_phone: FieldValue = FieldValue()
    vendor_address: AddressField = AddressField()
    vendor_bank: BankDetails = BankDetails()
    customer_name: FieldValue = FieldValue()
    customer_gstin: FieldValue = FieldValue()
    customer_address: AddressField = AddressField()
    billing_address: AddressField = AddressField()
    shipping_address: AddressField = AddressField()
    document_number: FieldValue = FieldValue()
    document_date: FieldValue = FieldValue()
    due_date: FieldValue = FieldValue()
    po_number: FieldValue = FieldValue()
    subtotal: FieldValue = FieldValue()
    cgst: FieldValue = FieldValue()
    sgst: FieldValue = FieldValue()
    igst: FieldValue = FieldValue()
    total_tax: FieldValue = FieldValue()
    grand_total: FieldValue = FieldValue()
    discount: FieldValue = FieldValue()
    taxes: List[TaxItem] = Field(default_factory=list)
    transporter: TransporterDetails = TransporterDetails()
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
