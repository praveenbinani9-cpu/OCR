"""LLM prompt templates for document extraction.

Includes per-document-type hint blocks that get prepended when we can
classify the OCR text up-front (EWAY_BILL / DELIVERY_CHALLAN / TAX_INVOICE).
Specialized hints don't change the response schema — they help Claude
extract the right fields and assign the correct ``document_type`` label.
"""
from __future__ import annotations

import re

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


# ---------- Per-document-type specialization ----------

EWAY_BILL_HINT = """
Document-type specialization — E-WAY BILL:
- This is an EWB (E-Way Bill) generated on ewaybillgst.gov.in. Set
  document_type = "EWAY_BILL" with high confidence.
- "vendor_name" / "vendor_gstin" map to the **Generator / Supplier** of the EWB
  (look for "GSTIN of Generator", "From GSTIN", "From:").
- "customer_name" / "customer_gstin" map to the **Recipient / Consignee**
  ("To GSTIN", "To:", "Place of Delivery").
- "document_number" is the **EWB No.** (12-digit numeric, often near "EWB No"
  or "E-Way Bill No"); do NOT confuse with the underlying invoice number.
- "document_date" is the **EWB Generation Date** (not invoice date).
- Amounts: EWBs carry an "Invoice Value" — populate "grand_total" from it. If
  only "Total Value" appears, treat as grand_total. Tax breakdown (CGST/SGST/
  IGST) is usually present; if absent leave those fields empty with 0.0
  confidence (do NOT fabricate).
- DO NOT extract Vehicle Number, Transporter ID, Mode, Distance, or Valid-Upto
  into the standard schema — they have no mapping (would lower data quality).
- If a per-item HSN/qty table is present, populate "items"; otherwise return [].
""".strip()

DELIVERY_CHALLAN_HINT = """
Document-type specialization — DELIVERY CHALLAN:
- A Delivery Challan accompanies a non-sale movement of goods (job-work,
  branch transfer, sample, sale-on-approval). Set document_type = "DELIVERY_CHALLAN".
- Delivery Challans typically have **no tax amounts** because no sale has
  occurred yet. If CGST/SGST/IGST are absent, return them as empty strings
  with 0.0 confidence — DO NOT infer or compute them.
- "subtotal" and "grand_total" should reflect the **value of goods** declared
  on the challan (often labelled "Value of goods", "Total Value", "Amount").
  If only one total is present, populate both with the same value.
- "document_number" comes from "Challan No.", "DC No.", "Delivery Challan No."
- "vendor_name" / "vendor_gstin" = the consignor / sender (issuer of the challan).
- "customer_name" / "customer_gstin" = the consignee / receiver.
- Items table (description, HSN, qty, rate, amount) MUST be extracted when present.
- Common challan-specific labels: "Despatched through", "Mode of Transport",
  "Place of Supply", "Reason for Transportation" — these don't map to the
  schema; ignore them.
""".strip()

TAX_INVOICE_HINT = """
Document-type specialization — TAX INVOICE:
- A standard GST Tax Invoice. Set document_type = "TAX_INVOICE".
- Both vendor (supplier) and customer (recipient) sections are usually labelled
  explicitly. Always look for "Bill To" / "Ship To" for the customer block.
- All tax fields (CGST, SGST, IGST) should reconcile against subtotal and
  grand_total within ±1 rupee. Prioritise extracting them accurately.
""".strip()


# ---------- Type detection heuristics ----------

_EWAY_KEYWORDS = (
    r"\bE-?\s*Way\s*Bill\b",
    r"\bEWB\s*N?o\b",
    r"\bewaybillgst\b",
    r"\bGSTIN\s+of\s+Generator\b",
    r"\bValid\s*Upto\b",
)

_DELIVERY_CHALLAN_KEYWORDS = (
    r"\bDelivery\s*Challan\b",
    r"\bChallan\s*N?o\b",
    r"\bD\.?C\.?\s*N?o\b",
    r"\bDespatch(?:ed)?\s*through\b",
    r"\bReason\s*for\s*Transportation\b",
)

_TAX_INVOICE_KEYWORDS = (
    r"\bTax\s*Invoice\b",
    r"\bInvoice\s*N?o\b",
    r"\bBill\s*To\b",
)


def _score(text: str, patterns: tuple[str, ...]) -> int:
    return sum(1 for p in patterns if re.search(p, text, flags=re.IGNORECASE))


def detect_document_type(ocr_text: str) -> str:
    """Best-effort classification from raw OCR text. Returns one of:
    "EWAY_BILL" | "DELIVERY_CHALLAN" | "TAX_INVOICE" | "UNKNOWN".

    Used only to pick a specialized prompt — the LLM may override.
    """
    if not ocr_text:
        return "UNKNOWN"
    scores = {
        "EWAY_BILL": _score(ocr_text, _EWAY_KEYWORDS),
        "DELIVERY_CHALLAN": _score(ocr_text, _DELIVERY_CHALLAN_KEYWORDS),
        "TAX_INVOICE": _score(ocr_text, _TAX_INVOICE_KEYWORDS),
    }
    best_type, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score == 0:
        return "UNKNOWN"
    # Require a clear lead to avoid wrong specialization
    sorted_scores = sorted(scores.values(), reverse=True)
    if len(sorted_scores) >= 2 and sorted_scores[0] == sorted_scores[1]:
        return "UNKNOWN"
    return best_type


_TYPE_HINTS = {
    "EWAY_BILL": EWAY_BILL_HINT,
    "DELIVERY_CHALLAN": DELIVERY_CHALLAN_HINT,
    "TAX_INVOICE": TAX_INVOICE_HINT,
}


def build_user_prompt(
    ocr_text: str,
    hints: str = "",
    document_type_hint: str | None = None,
) -> str:
    """Assemble the full user prompt. If ``document_type_hint`` is one of the
    specialized types, its hint block is appended verbatim so the model
    extracts the right fields and labels the document correctly.
    """
    base = USER_PROMPT_TEMPLATE.format(ocr_text=ocr_text, hints=hints or "none")
    type_block = _TYPE_HINTS.get((document_type_hint or "").upper(), "")
    parts = [base]
    if type_block:
        parts.append(type_block)
    parts.append(SCHEMA_HINT)
    return "\n\n".join(parts)


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
