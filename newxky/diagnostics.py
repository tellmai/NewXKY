"""Headless runtime verification for the standalone Windows build."""
import json
from io import BytesIO
from pathlib import Path


def self_check(report_path, pdf_path, image_path, crop=None):
    report = {"ok": False}
    try:
        from PIL import Image
        from .bank import load_pdf, merge_banks
        from .matching import KnowledgeIndex
        from .ocr import LocalOCR
        bank = merge_banks([load_pdf(pdf_path)])
        if not bank.questions:
            raise ValueError("PDF 未解析出题目")
        image = Image.open(image_path).convert("RGB")
        if crop:
            image = image.crop(crop)
        content = BytesIO()
        image.save(content, format="PNG")
        text = LocalOCR().recognize(content.getvalue())
        match = KnowledgeIndex(bank.questions).lookup(text)
        report.update(pages=bank.page_count, questions=len(bank.questions), issues=len(bank.issues),
                      ocr_text=text, status=match.status, answers=match.answers,
                      source_question=match.question.number if match.question else None,
                      ok=match.status in ("matched", "reference"))
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
