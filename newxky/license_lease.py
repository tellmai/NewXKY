"""Verify server-issued Ed25519 leases without holding any signing secret."""
from __future__ import annotations

import base64
import hashlib
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SESSION_SECONDS = 40 * 60


def public_key(value: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(value, validate=True))


def verify_lease(lease: dict, signature: str, key: str, code: str, machine_id: str) -> dict:
    try:
        payload = json.dumps(lease, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")
        public_key(key).verify(base64.b64decode(signature, validate=True), payload)
        if not isinstance(lease, dict) or lease.get("version") != 1:
            raise ValueError("Unsupported lease")
        for name in ("activated_at", "expires_at", "issued_at"):
            if type(lease[name]) is not int:
                raise ValueError("Invalid lease timestamp")
        if not (0 <= lease["activated_at"] <= lease["issued_at"] < lease["expires_at"]
                and 0 < lease["expires_at"] - lease["activated_at"] <= SESSION_SECONDS):
            raise ValueError("Invalid lease duration")
        expected_hash = hashlib.sha256(f"NewXKY/license/v1|{code}".encode("utf-8")).hexdigest()
        if lease["code_hash"] != expected_hash or lease["machine_id"] != machine_id:
            raise ValueError("Lease belongs to a different code or machine")
    except (InvalidSignature, ValueError, TypeError, KeyError) as error:
        raise ValueError("Invalid server-signed lease") from error
    return dict(lease)
