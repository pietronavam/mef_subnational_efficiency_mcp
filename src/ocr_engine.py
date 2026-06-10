"""
PaddleOCR engine for extracting text from the 1964 Ministerio de Hacienda PDF.
Processes a minimum of 15 pages and saves structured results to data/processed/.

Usage (standalone):
    python src/ocr_engine.py <pdf_path> '[1,2,3,...,15]'

Called by the MCP server tool procesar_ocr_paginas_1964.
"""
import io
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"


def pdf_to_images(pdf_path: str, page_numbers: list[int]) -> list[tuple[int, Image.Image]]:
    """Convert selected PDF pages to PIL images using pypdfium2."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_path)
    n_pages = len(pdf)
    images = []
    for page_num in page_numbers:
        idx = page_num - 1  # pypdfium2 is 0-indexed
        if idx < 0 or idx >= n_pages:
            continue
        page = pdf[idx]
        bitmap = page.render(scale=2.0, rotation=0)
        pil_image = bitmap.to_pil()
        images.append((page_num, pil_image))
    return images


def run_ocr_on_image(image: Image.Image, ocr_engine) -> list[dict]:
    """Run PaddleOCR on a PIL image and return structured text blocks."""
    img_array = np.array(image.convert("RGB"))
    results = ocr_engine.ocr(img_array, cls=True)
    blocks = []
    if not results or results[0] is None:
        return blocks
    for line in results[0]:
        if line is None:
            continue
        box, (text, confidence) = line
        blocks.append({
            "text": text,
            "confidence": round(float(confidence), 3),
            "box": [[round(float(c), 1) for c in pt] for pt in box],
        })
    return blocks


def extract_numeric_values(blocks: list[dict]) -> list[dict]:
    """Pull out text blocks that look like financial figures."""
    pattern = re.compile(r"[\d,\.]+")
    financial = []
    for b in blocks:
        if pattern.search(b["text"]) and b["confidence"] > 0.7:
            financial.append(b)
    return financial


def build_page_summary(page_num: int, blocks: list[dict]) -> dict:
    """Summarise one page of OCR results."""
    all_text = " ".join(b["text"] for b in blocks)
    financial = extract_numeric_values(blocks)
    return {
        "page": page_num,
        "total_blocks": len(blocks),
        "financial_blocks": len(financial),
        "full_text": all_text[:3000],
        "blocks": blocks[:50],
    }


def build_historical_dataframe(page_summaries: list[dict]) -> list[dict]:
    """
    Build a flat list of financial entries from all OCR page summaries.
    Returns records suitable for pandas/Streamlit display.
    """
    records = []
    for ps in page_summaries:
        for block in ps.get("blocks", []):
            text = block.get("text", "").strip()
            if not text:
                continue
            records.append({
                "page": ps["page"],
                "text": text,
                "confidence": block.get("confidence", 0),
                "is_numeric": bool(re.search(r"\d", text)),
            })
    return records


def process_pdf(pdf_path: str, page_numbers: list[int]) -> dict:
    """Full pipeline: PDF → images → OCR → structured output."""
    from paddleocr import PaddleOCR

    PROCESSED.mkdir(parents=True, exist_ok=True)
    ocr = PaddleOCR(use_angle_cls=True, lang="es", show_log=False)

    images = pdf_to_images(pdf_path, page_numbers)
    if not images:
        return {"error": f"No pages extracted from {pdf_path}"}

    page_summaries = []
    for page_num, img in images:
        blocks = run_ocr_on_image(img, ocr)
        summary = build_page_summary(page_num, blocks)
        page_summaries.append(summary)

    records = build_historical_dataframe(page_summaries)

    result = {
        "pdf_path": str(pdf_path),
        "pages_processed": len(page_summaries),
        "total_text_blocks": sum(ps["total_blocks"] for ps in page_summaries),
        "page_summaries": page_summaries,
        "flat_records": records[:500],
    }

    out_path = PROCESSED / "ocr_1964_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return {
        "status": "success",
        "pages_processed": result["pages_processed"],
        "total_text_blocks": result["total_text_blocks"],
        "output_file": str(out_path),
        "page_summaries": [
            {"page": ps["page"], "blocks": ps["total_blocks"], "preview": ps["full_text"][:200]}
            for ps in page_summaries
        ],
    }


if __name__ == "__main__":
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data" / "raw_pdfs" / "hacienda_1964.pdf")
    page_numbers = json.loads(sys.argv[2]) if len(sys.argv) > 2 else list(range(1, 16))
    result = process_pdf(pdf_path, page_numbers)
    print(json.dumps(result, ensure_ascii=False))
