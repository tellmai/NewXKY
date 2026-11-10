"""Server-only signing keys. Never distribute the private PEM with the client."""
from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .codes import hash_code

KEY_NAME = "lease-signing-key.pem"


def load_key(path: str | Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("The lease signing key must be Ed25519")
    return key


def public_key_text(key: Ed25519PrivateKey) -> str:
    return base64.b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode("ascii")


def sign_activation(result: dict, code: str, machine_id: str, key: Ed25519PrivateKey) -> dict:
    lease = {
        "version": 1,
        "code_hash": hash_code(code),
        "machine_id": machine_id,
        "activated_at": result["activated_at"],
        "expires_at": result["expires_at"],
        "issued_at": result["server_time"],
    }
    payload = json.dumps(lease, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return {**result, "lease": lease,
            "signature": base64.b64encode(key.sign(payload)).decode("ascii")}
