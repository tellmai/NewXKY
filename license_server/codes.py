"""Code formatting and hashing shared by the license tools."""
from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 16
CODE_RE = re.compile(r"^[A-HJ-NP-Z2-9]{%d}$" % CODE_LENGTH)


def normalize_code(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).upper()
    return re.sub(r"[\s\-_]+", "", text)


def valid_code(value: str) -> bool:
    return bool(CODE_RE.fullmatch(normalize_code(value)))


def format_code(value: str) -> str:
    text = normalize_code(value)
    return "-".join(text[index:index + 4] for index in range(0, len(text), 4))


def generate_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def hash_code(value: str) -> str:
    normalized = normalize_code(value)
    if not valid_code(normalized):
        raise ValueError("invalid license code")
    return hashlib.sha256(f"NewXKY/license/v1|{normalized}".encode("utf-8")).hexdigest()
