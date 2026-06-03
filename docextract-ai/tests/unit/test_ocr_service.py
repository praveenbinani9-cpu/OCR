from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from app.services import ocr as ocr_mod


def _fake_image() -> np.ndarray:
    return np.zeros((100, 100, 3), dtype=np.uint8)


def test_tesseract_engine_runs_for_each_page():
    fake_pyt = MagicMock()
    fake_pyt.image_to_string.return_value = "INVOICE 123"
    with patch.dict("sys.modules", {"pytesseract": fake_pyt}):
        engine = ocr_mod.TesseractEngine()
        out = engine.ocr([_fake_image(), _fake_image()])
    assert "INVOICE 123" in out
    assert fake_pyt.image_to_string.call_count == 2


def test_paddle_engine_parses_result_shape():
    fake_paddle_inst = MagicMock()
    fake_paddle_inst.ocr.return_value = [
        [
            [[[0, 0], [10, 0], [10, 10], [0, 10]], ("Hello", 0.99)],
            [[[0, 10], [10, 10], [10, 20], [0, 20]], ("World", 0.97)],
        ]
    ]
    fake_paddle_cls = MagicMock(return_value=fake_paddle_inst)
    fake_module = MagicMock(PaddleOCR=fake_paddle_cls)
    ocr_mod.PaddleEngine._instance = None
    with patch.dict("sys.modules", {"paddleocr": fake_module}):
        engine = ocr_mod.PaddleEngine.get()
        out = engine.ocr([_fake_image()])
    assert "Hello" in out and "World" in out
    ocr_mod.PaddleEngine._instance = None


def test_ocr_service_falls_back_to_tesseract_on_paddle_failure():
    ocr_mod.PaddleEngine._instance = None
    fake_paddle = MagicMock()
    fake_paddle.PaddleOCR.side_effect = RuntimeError("paddle broken")
    fake_pyt = MagicMock()
    fake_pyt.image_to_string.return_value = "FALLBACK"

    svc = ocr_mod.OCRService(engine="paddle")
    with patch.dict("sys.modules", {"paddleocr": fake_paddle, "pytesseract": fake_pyt}):
        result = svc._run_engine([_fake_image()])
    assert "FALLBACK" in result
