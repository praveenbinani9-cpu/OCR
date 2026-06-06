from __future__ import annotations
import os
import asyncio
from typing import Any
from mindee import ClientV2, InferenceParameters, InferenceResponse
from mindee.input import BytesInput

class MindeeExtractionService:
    def __init__(self) -> None:
        self._client = ClientV2(os.getenv("MINDEE_API_KEY", ""))
        self._model_id = os.getenv("MINDEE_MODEL_ID", "")

    def _v(self, field, default=""):
        v = getattr(field, "value", None) if field else None
        return {"value": str(v) if v is not None else default, "confidence": 0.9 if v is not None else 0.0}

    def _addr(self, field):
        if not field: return {}
        return {
            "address": str(getattr(field, "address", "") or ""),
            "city": str(getattr(field, "city", "") or ""),
            "state": str(getattr(field, "state", "") or ""),
            "postal_code": str(getattr(field, "postal_code", "") or ""),
            "country": str(getattr(field, "country", "") or ""),
        }

    async def extract(self, raw: bytes, mime_type: str = "image/jpeg", hints: str = "") -> dict[str, Any]:
        model_params = InferenceParameters(model_id=self._model_id)
        input_source = BytesInput(raw, "invoice.jpg")
        response = await asyncio.to_thread(
            self._client.enqueue_and_get_result,
            InferenceResponse, input_source, model_params,
        )
        f = response.inference.result.fields

        def fv(key):
            return self._v(f.get(key))

        # GSTIN from registration lists
        def gstin(key):
            field = f.get(key)
            items = getattr(field, "items", []) if field else []
            for item in (items or []):
                ifields = getattr(item, "fields", {})
                num = ifields.get("number")
                v = getattr(num, "value", None) if num else None
                if v:
                    return {"value": str(v), "confidence": 0.9}
            return {"value": "", "confidence": 0.0}

        # Bank details
        bank = {}
        pd = f.get("supplier_payment_details")
        pd_items = getattr(pd, "items", []) if pd else []
        if pd_items:
            pf = getattr(pd_items[0], "fields", {})
            bank = {
                "account_number": str(getattr(pf.get("account_number"), "value", "") or ""),
                "ifsc": str(getattr(pf.get("routing_number"), "value", "") or ""),
                "iban": str(getattr(pf.get("iban"), "value", "") or ""),
            }

        # Taxes
        taxes = []
        tax_field = f.get("taxes")
        tax_items = getattr(tax_field, "items", []) if tax_field else []
        for t in (tax_items or []):
            tf = getattr(t, "fields", {})
            taxes.append({
                "rate": str(getattr(tf.get("rate"), "value", "") or ""),
                "base": str(getattr(tf.get("base"), "value", "") or ""),
                "amount": str(getattr(tf.get("amount"), "value", "") or ""),
            })

        # Line items
        items = []
        li_field = f.get("line_items")
        li_items = getattr(li_field, "items", []) if li_field else []
        for item in (li_items or []):
            ifields = getattr(item, "fields", {})
            def iv(k):
                field = ifields.get(k)
                v = getattr(field, "value", None) if field else None
                return str(v) if v is not None else ""
            items.append({
                "description": {"value": iv("description"), "confidence": 0.9},
                "hsn": {"value": iv("product_code"), "confidence": 0.9},
                "qty": {"value": iv("quantity"), "confidence": 0.9},
                "unit_measure": {"value": iv("unit_measure"), "confidence": 0.9},
                "rate": {"value": iv("unit_price"), "confidence": 0.9},
                "amount": {"value": iv("total_price"), "confidence": 0.9},
                "tax_rate": {"value": iv("tax_rate"), "confidence": 0.9},
                "tax_amount": {"value": iv("tax_amount"), "confidence": 0.9},
            })

        # Transporter
        trans = f.get("transporter_details")
        transporter = {}
        if trans:
            transporter = {
                "name": str(getattr(trans, "name", "") or ""),
                "id": str(getattr(trans, "id", "") or ""),
                "mode": str(getattr(trans, "mode", "") or ""),
                "vehicle_number": str(getattr(trans, "vehicle_number", "") or ""),
            }

        return {
            "document_type": "TAX_INVOICE",
            "overall_confidence": 0.9,
            "data": {
                "vendor_name": fv("supplier_name"),
                "vendor_gstin": gstin("supplier_company_registration"),
                "vendor_email": fv("supplier_email"),
                "vendor_phone": fv("supplier_phone_number"),
                "vendor_address": self._addr(f.get("supplier_address")),
                "vendor_bank": bank,
                "customer_name": fv("customer_name"),
                "customer_gstin": gstin("customer_company_registration"),
                "customer_address": self._addr(f.get("customer_address")),
                "billing_address": self._addr(f.get("billing_address")),
                "shipping_address": self._addr(f.get("shipping_address")),
                "document_number": fv("invoice_number"),
                "document_date": fv("date"),
                "due_date": fv("due_date"),
                "po_number": fv("po_number"),
                "subtotal": fv("total_net"),
                "cgst": fv("cgst"),
                "sgst": fv("sgst"),
                "igst": fv("igst"),
                "total_tax": fv("total_tax"),
                "grand_total": fv("total_amount"),
                "discount": fv("discount"),
                "taxes": taxes,
                "transporter": transporter,
                "items": items,
            }
        }

    async def correct(self, ocr_text: str, errors: list) -> dict[str, Any]:
        return {}

class LLMError(Exception):
    pass

mindee_extraction_service = MindeeExtractionService()
