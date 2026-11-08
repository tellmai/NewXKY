"""Question-bank storage and text normalization.

The simplified application ships one verified bank and does not import PDFs at
runtime, so this module only reads and writes the JSON cache.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import asdict
from pathlib import Path

from .models import Bank, Question


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    # Keep numeric punctuation and operators: 1.5, 15 and -15 are different.
    text = re.sub(r"(?<=\d)\.(?=\d)", "小数点", text)
    text = text.replace("%", "百分号").replace("+", "加号").replace("=", "等号")
    text = re.sub(r"[-−](?=\d)", "负号", text)
    return re.sub(r"[\W_]+", "", text)


def question_key(question: Question):
    return normalized(question.stem), tuple(sorted(normalized(v) for v in question.options.values()))


def save_bank(bank: Bank, path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump({"version": 1, **asdict(bank)}, file, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


def read_bank(path: Path) -> Bank:
    path = Path(path)
    if not path.exists():
        return Bank()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError("题库缓存版本不兼容")
    questions = [
        Question(**(q | {"answers": tuple(q["answers"]), "pages": tuple(q["pages"])}))
        for q in data["questions"]
    ]
    return Bank(
        questions,
        list(data.get("issues", [])),
        list(data.get("sources", [])),
        int(data.get("page_count", 0)),
        int(data.get("duplicates", 0)),
    )
