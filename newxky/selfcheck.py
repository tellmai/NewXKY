"""Hidden headless OCR/bank verification for packaged builds."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path


def self_check(image_path, report_path) -> int:
    report = {"ok": False}
    try:
        from PIL import Image

        from .default_bank import load_startup_bank
        from .matching import KnowledgeIndex
        from .ocr import LocalOCR

        root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
        bank, notes = load_startup_bank(root)
        if not bank.questions:
            raise ValueError("；".join(notes) or "内置题库为空")
        image = Image.open(image_path).convert("RGB")
        content = io.BytesIO()
        image.save(content, format="PNG")
        text = LocalOCR().recognize(content.getvalue())
        match = KnowledgeIndex(bank.questions).lookup(text)
        report.update(
            questions=len(bank.questions),
            ocr_text=text,
            status=match.status,
            answers=list(match.answers),
            question=match.question.number if match.question else None,
            ok=match.status in {"matched", "reference"},
        )
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
