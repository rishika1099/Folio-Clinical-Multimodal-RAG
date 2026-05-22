"""
PDF handling. Native text via pdfplumber (cheap, fast, no LLM); rasterize and
route to vision if the PDF is image-only or extraction is sparse.
"""
import asyncio
import io
from typing import Optional

import pdfplumber

from ..models.router import vision_extract_text


def _native_text_sync(pdf_bytes: bytes) -> str:
    out: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages[:20]:
            txt = page.extract_text() or ""
            if txt.strip():
                out.append(txt)
    return "\n\n".join(out).strip()


async def extract_pdf_text(pdf_bytes: bytes) -> tuple[str, str]:
    """
    Returns (text, method) where method is "native" or "vision".
    """
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, _native_text_sync, pdf_bytes)
    if len(text) >= 80:
        return text, "native"

    # Image-only PDF: rasterize first 10 pages and send to vision.
    images = await loop.run_in_executor(None, _rasterize_sync, pdf_bytes)
    if not images:
        return text, "native"
    try:
        vision_text = await vision_extract_text(images)
        return vision_text or text, "vision"
    except Exception:
        return text, "native"


def _rasterize_sync(pdf_bytes: bytes, max_pages: int = 10) -> list[bytes]:
    try:
        from pdf2image import convert_from_bytes
    except Exception:
        return []
    try:
        pages = convert_from_bytes(pdf_bytes, dpi=140, first_page=1, last_page=max_pages)
    except Exception:
        return []
    out: list[bytes] = []
    for img in pages:
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        out.append(buf.getvalue())
    return out
