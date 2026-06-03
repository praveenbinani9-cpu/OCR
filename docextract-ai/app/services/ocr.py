"""OCR service with PaddleOCR (primary in production) and pytesseract (fallback).

The engine is selected via OCR_ENGINE env var: "paddle" | "tesseract".
PaddleOCR is imported lazily so the module is importable in lightweight runtimes
where the heavy paddle stack is not installed.
"""
from __future__ import annotations

import io
from typing import List

import cv2
import numpy as np
from PIL import Image

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("ocr")


# ---------- Preprocessing ----------

def _deskew(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    edges = cv2.Canny(gray, 50, 200, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
    if lines is None:
        return image
    angles: list[float] = []
    for rho_theta in lines[:50]:
        _, theta = rho_theta[0]
        angle = (theta * 180.0 / np.pi) - 90.0
        if -45 < angle < 45:
            angles.append(angle)
    if not angles:
        return image
    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.5:
        return image
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), median_angle, 1.0)
    return cv2.warpAffine(
        image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def _enhance(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    # CLAHE for contrast (helps mobile photos)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    contrasted = clahe.apply(gray)
    # Light denoise
    denoised = cv2.fastNlMeansDenoising(contrasted, h=10, templateWindowSize=7, searchWindowSize=21)
    # Adaptive threshold
    binary = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    return binary


def preprocess_image_bytes(data: bytes) -> List[np.ndarray]:
    """Return list of preprocessed numpy arrays (one per page)."""
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        # Fall back to PIL (e.g. WEBP / oddities)
        pil = Image.open(io.BytesIO(data)).convert("RGB")
        img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    deskewed = _deskew(img)
    enhanced = _enhance(deskewed)
    return [enhanced]


def preprocess_pdf_bytes(data: bytes) -> List[np.ndarray]:
    """Convert PDF -> images -> preprocess. Returns one ndarray per page."""
    from pdf2image import convert_from_bytes  # lazy

    pages = convert_from_bytes(data, dpi=250, fmt="png")
    processed: List[np.ndarray] = []
    for page in pages:
        arr = cv2.cvtColor(np.array(page.convert("RGB")), cv2.COLOR_RGB2BGR)
        processed.append(_enhance(_deskew(arr)))
    return processed


# ---------- OCR engines ----------

class TesseractEngine:
    def __init__(self) -> None:
        import pytesseract  # lazy import

        self._pt = pytesseract

    def ocr(self, images: List[np.ndarray]) -> str:
        out: list[str] = []
        for img in images:
            text = self._pt.image_to_string(img, lang="eng", config="--oem 3 --psm 6")
            out.append(text)
        return "\n\n".join(out).strip()


class PaddleEngine:
    _instance: "PaddleEngine | None" = None

    def __init__(self) -> None:
        from paddleocr import PaddleOCR  # lazy heavy import

        self._engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)

    @classmethod
    def get(cls) -> "PaddleEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def ocr(self, images: List[np.ndarray]) -> str:
        out: list[str] = []
        for img in images:
            result = self._engine.ocr(img, cls=True)
            if not result:
                continue
            # PaddleOCR returns [[ [bbox, (text, conf)], ... ]]
            for page in result:
                if not page:
                    continue
                lines = [line[1][0] for line in page if line and len(line) >= 2]
                out.append("\n".join(lines))
        return "\n\n".join(out).strip()


# ---------- Facade ----------

class OCRService:
    def __init__(self, engine: str | None = None) -> None:
        self.engine = (engine or settings.ocr_engine).lower()

    def _run_engine(self, images: List[np.ndarray]) -> str:
        if self.engine == "paddle":
            try:
                return PaddleEngine.get().ocr(images)
            except Exception as exc:
                log.warning("paddle_failed_fallback_to_tesseract", error=str(exc))
                return TesseractEngine().ocr(images)
        return TesseractEngine().ocr(images)

    def extract_text(self, data: bytes, mime_type: str) -> str:
        if mime_type == "application/pdf":
            images = preprocess_pdf_bytes(data)
        else:
            images = preprocess_image_bytes(data)
        text = self._run_engine(images)
        log.info("ocr_done", engine=self.engine, chars=len(text), pages=len(images))
        return text

    def health(self) -> bool:
        try:
            if self.engine == "paddle":
                PaddleEngine.get()  # trigger init
            else:
                import pytesseract  # noqa: F401
            return True
        except Exception as exc:
            log.warning("ocr_health_failed", error=str(exc))
            return False


ocr_service = OCRService()
