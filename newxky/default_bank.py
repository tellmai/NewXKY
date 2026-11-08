"""Locate and load the verified question bank shipped with the application."""
from __future__ import annotations

import sys
from pathlib import Path

from .bank import read_bank
from .models import Bank

BUNDLE_DIRECTORY = "题库"
CACHE_NAME = "default-bank.json"
SOURCE_LABEL = "2026知识库"


def _candidates(app_dir=None):
    roots = []
    if app_dir is not None:
        roots.append(Path(app_dir))
    else:
        roots.append(Path(__file__).resolve().parents[1])
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        roots.append(Path(bundle))
    seen = set()
    for root in roots:
        for directory in (root / BUNDLE_DIRECTORY, root / "_internal" / BUNDLE_DIRECTORY):
            path = directory / CACHE_NAME
            key = str(path.resolve()) if path.exists() else str(path)
            if key in seen:
                continue
            seen.add(key)
            yield path


def find_bundled_bank(app_dir=None) -> Path | None:
    for path in _candidates(app_dir):
        if path.is_file():
            return path
    return None


def load_startup_bank(app_dir=None) -> tuple[Bank, list[str]]:
    """Load the read-only bundled bank; never falls back to a user PDF import."""
    path = find_bundled_bank(app_dir)
    if path is None:
        return Bank(), ["未找到内置题库文件，请重新解压完整的软件安装包。"]
    try:
        bank = read_bank(path)
    except (OSError, ValueError, TypeError, KeyError) as error:
        return Bank(), [f"内置题库读取失败：{error}"]
    if not bank.questions:
        return Bank(), ["内置题库为空，请重新解压完整的软件安装包。"]
    notes = [f"内置题库已加载：{len(bank.questions):,} 题 · 异常 {len(bank.issues)} 条"]
    if bank.issues:
        notes.extend(bank.issues[:8])
    return bank, notes
