"""LLM prompt templates for document extraction."""
from __future__ import annotations

SYSTEM_PROMPT = (
    "You are a document extraction engine for Indian GST documents. "
    "Extract ALL fields with confidence scores. Return ONLY valid JSON."
)

USER_PROMPT_TEMPLATE = (
    "OCR Text:\n{ocr_text}\n\n"
    "Document hints: {hints}\n\n"
    "Extract all invoice fields as JSON matching schema exactly."
)

SCHEMA_HINT = """
Schema (return EXACTLY this shape — empty string + 0.0 confidence if missing):
{
  "document_type": "TAX_INVOICE|DELIVERY_CHALLAN|PACKING_LIST|PURCHASE_ORDER|CREDIT_NOTE|DEBIT_NOTE|EWAY_BILL|UNKNOWN",
  "overall_confidence": 0.0,
  "data": {
    "vendor_name": {"value": "", "confidence": 0.0},
    "vendor_gstin": {"value": "", "confidence": 0.0},
    "customer_name": {"value": "", "confidence": 0.0},
    "customer_gstin": {"value": "", "confidence": 0.0},
    "document_number": {"value": "", "confidence": 0.0},
    "document_date": {"value": "", "confidence": 0.0},
    "subtotal": {"value": "", "confidence": 0.0},
    "cgst": {"value": "", "confidence": 0.0},
    "sgst": {"value": "", "confidence": 0.0},
    "igst": {"value": "", "confidence": 0.0},
    "total_tax": {"value": "", "confidence": 0.0},
    "grand_total": {"value": "", "confidence": 0.0},
    "items": [
      {
        "description": {"value": "", "confidence": 0.0},
        "hsn": {"value": "", "confidence": 0.0},
        "qty": {"value": "", "confidence": 0.0},
        "rate": {"value": "", "confidence": 0.0},
        "amount": {"value": "", "confidence": 0.0}
      }
    ]
  }
}
Rules:
- Amounts: numeric strings without currency symbols.
- Dates: prefer YYYY-MM-DD.
- GSTIN: 15 chars, uppercase.
- confidence in [0,1] reflecting OCR clarity + field certainty.
- Return ONLY the JSON object. No prose, no markdown fences.
""".strip()


def build_user_prompt(ocr_text: str, hints: str = "") -> str:
    base = USER_PROMPT_TEMPLATE.format(ocr_text=ocr_text, hints=hints or "none")
    return f"{base}\n\n{SCHEMA_HINT}"


CORRECTION_PROMPT_TEMPLATE = (
    "Your previous extraction had validation errors:\n{errors}\n\n"
    "Re-examine the OCR text and return a corrected JSON object "
    "in the same schema. Focus on reconciling amounts: "
    "subtotal + cgst + sgst + igst should equal grand_total (±1).\n\n"
    "OCR Text:\n{ocr_text}\n\n"
    "Return ONLY the corrected JSON."
)


def build_correction_prompt(ocr_text: str, errors: list[str]) -> str:
    return CORRECTION_PROMPT_TEMPLATE.format(
        errors="\n- " + "\n- ".join(errors) if errors else "(none)",
        ocr_text=ocr_text,
    )
