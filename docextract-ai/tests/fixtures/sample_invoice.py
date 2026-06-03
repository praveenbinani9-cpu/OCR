"""Sample OCR text and corresponding LLM JSON for tests."""

SAMPLE_INVOICE_OCR_TEXT = """
TAX INVOICE
ABC Industries Pvt Ltd
GSTIN: 27AABCU9603R1ZX
Invoice No: INV-2026-00451
Invoice Date: 12/01/2026

Bill To:
XYZ Trading Co
GSTIN: 29AAACX1234D1Z5

Item Description           HSN        Qty    Rate       Amount
Steel Bolts M12 x 50mm     7318       100    25.00      2500.00
Hex Nuts M12               7318       100    8.50       850.00
Lock Washers               7318       100    3.50       350.00

Subtotal:                                              3700.00
CGST 9%:                                                333.00
SGST 9%:                                                333.00
IGST:                                                     0.00
Total Tax:                                              666.00
Grand Total:                                           4366.00

Authorised Signatory
"""

SAMPLE_INVOICE_EXTRACTED = {
    "document_type": "TAX_INVOICE",
    "overall_confidence": 0.97,
    "data": {
        "vendor_name": {"value": "ABC Industries Pvt Ltd", "confidence": 0.99},
        "vendor_gstin": {"value": "27AABCU9603R1ZX", "confidence": 0.99},
        "customer_name": {"value": "XYZ Trading Co", "confidence": 0.95},
        "customer_gstin": {"value": "29AAACX1234D1Z5", "confidence": 0.96},
        "document_number": {"value": "INV-2026-00451", "confidence": 0.98},
        "document_date": {"value": "2026-01-12", "confidence": 0.97},
        "subtotal": {"value": "3700.00", "confidence": 0.98},
        "cgst": {"value": "333.00", "confidence": 0.98},
        "sgst": {"value": "333.00", "confidence": 0.98},
        "igst": {"value": "0.00", "confidence": 0.98},
        "total_tax": {"value": "666.00", "confidence": 0.98},
        "grand_total": {"value": "4366.00", "confidence": 0.99},
        "items": [
            {
                "description": {"value": "Steel Bolts M12 x 50mm", "confidence": 0.95},
                "hsn": {"value": "7318", "confidence": 0.98},
                "qty": {"value": "100", "confidence": 0.97},
                "rate": {"value": "25.00", "confidence": 0.97},
                "amount": {"value": "2500.00", "confidence": 0.97},
            },
            {
                "description": {"value": "Hex Nuts M12", "confidence": 0.94},
                "hsn": {"value": "7318", "confidence": 0.98},
                "qty": {"value": "100", "confidence": 0.97},
                "rate": {"value": "8.50", "confidence": 0.97},
                "amount": {"value": "850.00", "confidence": 0.97},
            },
            {
                "description": {"value": "Lock Washers", "confidence": 0.94},
                "hsn": {"value": "7318", "confidence": 0.98},
                "qty": {"value": "100", "confidence": 0.97},
                "rate": {"value": "3.50", "confidence": 0.97},
                "amount": {"value": "350.00", "confidence": 0.97},
            },
        ],
    },
}
