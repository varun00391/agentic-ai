from functools import lru_cache
from io import BytesIO

import numpy as np
import pymupdf
from PIL import Image, ImageOps


class DocumentError(ValueError):
    pass


SUPPORTED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "application/pdf",
}


def extract_document_text(content: bytes, content_type: str) -> str:
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise DocumentError(f"Unsupported content type: {content_type}")

    try:
        if content_type == "application/pdf":
            text = _extract_pdf_text(content)
        else:
            text = _extract_image_text(content)
    except (pymupdf.FileDataError, OSError, ValueError) as exc:
        raise DocumentError("The uploaded document could not be read") from exc

    cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not cleaned:
        raise DocumentError("No readable text was found in the document")
    return cleaned


def _extract_pdf_text(content: bytes) -> str:
    pages: list[str] = []
    with pymupdf.open(stream=content, filetype="pdf") as document:
        for page in document[:5]:
            embedded_text = page.get_text("text").strip()
            if embedded_text:
                pages.append(embedded_text)
                continue
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            image = Image.open(BytesIO(pixmap.tobytes("png")))
            pages.append(_run_paddle_ocr(image))
    return "\n".join(pages)


def _extract_image_text(content: bytes) -> str:
    with Image.open(BytesIO(content)) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = ImageOps.autocontrast(image)
        return _run_paddle_ocr(image)


@lru_cache(maxsize=1)
def _get_paddle_ocr():
    from paddleocr import PaddleOCR

    return PaddleOCR(
        device="cpu",
        engine="transformers",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def _run_paddle_ocr(image: Image.Image) -> str:
    try:
        results = _get_paddle_ocr().predict(np.asarray(image))
        lines: list[str] = []
        for result in results:
            payload = result.json.get("res", result.json)
            lines.extend(
                text.strip()
                for text in payload.get("rec_texts", [])
                if text and text.strip()
            )
        return "\n".join(lines)
    except Exception as exc:
        raise DocumentError("PaddleOCR could not process the document") from exc
