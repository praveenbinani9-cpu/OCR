"""Unit tests for per-document-type prompt specialization."""
from __future__ import annotations

from app.prompts.extraction import (
    DELIVERY_CHALLAN_HINT,
    EWAY_BILL_HINT,
    TAX_INVOICE_HINT,
    build_user_prompt,
    detect_document_type,
)


EWAY_OCR = """
GOVT OF INDIA - GOODS AND SERVICES TAX
E-Way Bill
EWB No: 181234567890
GSTIN of Generator: 27AABCU9603R1ZX
From: ABC Industries
To GSTIN: 29AAACX1234D1Z5
Place of Delivery: Bangalore
Invoice Value: 125000.00
Valid Upto: 15/02/2026 23:59
Vehicle Number: KA01AB1234
"""

DC_OCR = """
DELIVERY CHALLAN
Challan No: DC-2026-0041
Date: 12/01/2026
From: ABC Industries
GSTIN: 27AABCU9603R1ZX
To: XYZ Job Workers
GSTIN: 29AAACX1234D1Z5
Despatched through: Lorry
Reason for Transportation: Job Work
Description    HSN    Qty    Rate    Amount
Steel Rods     7228   500    50.00   25000.00
Total Value: 25000.00
"""

INVOICE_OCR = """
TAX INVOICE
ABC Industries Pvt Ltd
GSTIN: 27AABCU9603R1ZX
Invoice No: INV-2026-00451
Bill To: XYZ Trading Co
GSTIN: 29AAACX1234D1Z5
Subtotal: 3700.00
CGST: 333.00
SGST: 333.00
Grand Total: 4366.00
"""


def test_detect_eway_bill():
    assert detect_document_type(EWAY_OCR) == "EWAY_BILL"


def test_detect_delivery_challan():
    assert detect_document_type(DC_OCR) == "DELIVERY_CHALLAN"


def test_detect_tax_invoice():
    assert detect_document_type(INVOICE_OCR) == "TAX_INVOICE"


def test_detect_unknown_on_empty():
    assert detect_document_type("") == "UNKNOWN"
    assert detect_document_type("just some random text with no keywords") == "UNKNOWN"


def test_detect_unknown_on_tie():
    # Equal scores -> UNKNOWN, lets the LLM decide
    text = "Tax Invoice Delivery Challan"
    assert detect_document_type(text) == "UNKNOWN"


def test_prompt_includes_eway_specialization():
    prompt = build_user_prompt(EWAY_OCR, document_type_hint="EWAY_BILL")
    assert EWAY_BILL_HINT in prompt
    # Other hints must NOT appear
    assert DELIVERY_CHALLAN_HINT not in prompt
    assert TAX_INVOICE_HINT not in prompt
    # EWB-specific guidance keywords surface in the prompt
    assert "EWB" in prompt
    assert "Vehicle Number" in prompt  # the "do not extract" instruction
    # OCR text and schema are still present
    assert "EWB No: 181234567890" in prompt
    assert "document_type" in prompt


def test_prompt_includes_delivery_challan_specialization():
    prompt = build_user_prompt(DC_OCR, document_type_hint="DELIVERY_CHALLAN")
    assert DELIVERY_CHALLAN_HINT in prompt
    assert EWAY_BILL_HINT not in prompt
    # Challan-specific guidance
    assert "no tax amounts" in prompt
    assert "Challan No" in prompt


def test_prompt_includes_tax_invoice_specialization():
    prompt = build_user_prompt(INVOICE_OCR, document_type_hint="TAX_INVOICE")
    assert TAX_INVOICE_HINT in prompt
    assert "Bill To" in prompt


def test_prompt_without_hint_is_generic():
    prompt = build_user_prompt(INVOICE_OCR)
    assert EWAY_BILL_HINT not in prompt
    assert DELIVERY_CHALLAN_HINT not in prompt
    assert TAX_INVOICE_HINT not in prompt
    # Schema still required
    assert "document_type" in prompt


def test_unknown_hint_is_treated_as_no_specialization():
    prompt = build_user_prompt(INVOICE_OCR, document_type_hint="UNKNOWN")
    assert TAX_INVOICE_HINT not in prompt
    assert EWAY_BILL_HINT not in prompt
