import pytest
from PIL import Image

from app.document import _run_paddle_ocr
from app.scan import scan_receipt
from tests.conftest import PNG_BYTES


class FakeResult:
    json = {"res": {"rec_texts": ["Fresh Mart", "", "Total INR 123.45"]}}


class FakePaddleOCR:
    def predict(self, image):
        assert image.shape == (50, 100, 3)
        return [FakeResult()]


def test_paddle_ocr_result_is_converted_to_text(monkeypatch) -> None:
    monkeypatch.setattr("app.document._get_paddle_ocr", lambda: FakePaddleOCR())
    image = Image.new("RGB", (100, 50), "white")
    assert _run_paddle_ocr(image) == "Fresh Mart\nTotal INR 123.45"


def test_scan_accepts_png_magic_bytes() -> None:
    assert scan_receipt(PNG_BYTES, "image/png") == "clean"


def test_scan_rejects_mismatched_bytes() -> None:
    with pytest.raises(ValueError):
        scan_receipt(b"hello", "image/png")
