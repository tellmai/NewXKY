from __future__ import annotations

import base64
from dataclasses import replace
import json
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from license_server.codes import generate_code
from license_server.signing import public_key_text, sign_activation
from newxky.licensing import LicenseError, LicenseManager, LicenseState, LicenseStore

NOW = 1_800_000_000
MACHINE = "a" * 64


@pytest.fixture()
def signed_response():
    key = Ed25519PrivateKey.generate()
    code = generate_code()
    data = sign_activation({"ok": True, "activated_at": NOW, "expires_at": NOW + 2400,
                            "server_time": NOW, "remaining_seconds": 2400}, code, MACHINE, key)
    return key, code, data


class Api:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def activate(self, code, machine):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def manager(tmp_path, signed_response, *, response=None, now=NOW, key=None):
    signing_key, code, data = signed_response
    return LicenseManager(tmp_path, machine_id=MACHINE, clock=lambda: now,
                          public_key=key or public_key_text(signing_key),
                          api=Api(data if response is None else response))


def test_signed_lease_resumes_offline_and_refresh_does_not_restart_the_period(tmp_path, signed_response):
    original = manager(tmp_path, signed_response)
    original.activate(signed_response[1])
    offline = manager(tmp_path, signed_response, response=LicenseError("network"), now=NOW + 120)
    assert offline.restore()
    assert offline.remaining_seconds() == 2280
    with pytest.raises(LicenseError, match="无法连接"):
        offline.refresh()
    assert offline.can_use
    assert offline.remaining_seconds() <= 2280


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI storage")
@pytest.mark.parametrize("format", ["raw", "JSON1", "JSON2"])
def test_unsigned_plaintext_cannot_grant_a_day_of_offline_use(tmp_path, signed_response, format):
    state = LicenseState(signed_response[1], MACHINE, NOW, NOW + 86400, 0, NOW, "")
    payload = json.dumps(state.as_dict()).encode()
    if format == "JSON1":
        payload = b"JSON1\n" + base64.b64encode(payload)
    elif format == "JSON2":
        payload = b"JSON2\n" + payload
    (tmp_path / "license.dat").write_bytes(payload)
    client = manager(tmp_path, signed_response, response=LicenseError("network"))
    assert not client.restore()
    assert not client.can_use
    assert client.api.calls == 0


@pytest.mark.parametrize("field", ["expires_at", "activated_at", "clock_offset", "code", "signature", "lease"])
def test_tampered_cached_fields_are_rejected_even_inside_dpapi(tmp_path, signed_response, field):
    client = manager(tmp_path, signed_response)
    state = client.activate(signed_response[1])
    changes = {
        "expires_at": NOW + 86400, "activated_at": NOW - 86400,
        "clock_offset": -86400, "code": generate_code(), "signature": "A" * 88,
        "lease": {**state.lease, "expires_at": NOW + 86400},
    }
    client.store.save(replace(state, **{field: changes[field]}))
    restored = manager(tmp_path, signed_response, response=LicenseError("network"))
    assert not restored.restore()
    assert not restored.can_use
    assert restored.api.calls == 0


@pytest.mark.parametrize("damage", ["wrong_key", "wrong_code", "wrong_machine", "unsigned", "long_duration"])
def test_invalid_online_lease_cannot_activate(tmp_path, signed_response, damage):
    signing_key, code, original = signed_response
    data = json.loads(json.dumps(original))
    if damage == "wrong_key":
        signing_key = Ed25519PrivateKey.generate()
    if damage == "unsigned":
        data.pop("signature")
    elif damage in {"wrong_code", "wrong_machine", "long_duration"}:
        result = {**original}
        if damage == "long_duration":
            result["expires_at"] = NOW + 86400
        data = sign_activation(result, generate_code() if damage == "wrong_code" else code,
                               "b" * 64 if damage == "wrong_machine" else MACHINE, signing_key)
    client = manager(tmp_path, signed_response, response=data, key=public_key_text(signing_key))
    with pytest.raises(LicenseError) as caught:
        client.activate(code)
    assert caught.value.code == "bad_signature"
    assert not client.can_use


def test_a_bad_refresh_signature_locks_the_existing_lease(tmp_path, signed_response):
    client = manager(tmp_path, signed_response)
    client.activate(signed_response[1])
    client.api.response = {**signed_response[2], "signature": "invalid"}
    with pytest.raises(LicenseError):
        client.refresh()
    assert not client.can_use


def test_legacy_encrypted_record_requires_online_upgrade(tmp_path, signed_response):
    client = manager(tmp_path, signed_response)
    state = client.activate(signed_response[1])
    client.store.save(replace(state, lease={}, signature="", expires_at=NOW + 86400))
    offline = manager(tmp_path, signed_response, response=LicenseError("network"))
    assert not offline.restore()
    assert not offline.can_use
    online = manager(tmp_path, signed_response)
    assert online.restore()
    assert online.api.calls == 1
    assert online.remaining_seconds() == 2400
    assert online.state.signature


def test_windows_encryption_failure_never_writes_a_plaintext_fallback(tmp_path, signed_response, monkeypatch):
    monkeypatch.setattr("newxky.licensing.sys.platform", "win32")
    monkeypatch.setattr("newxky.licensing._dpapi_call", lambda *args, **kwargs: None)
    store = LicenseStore(tmp_path / "license.dat")
    state = LicenseState(signed_response[1], MACHINE, NOW, NOW + 2400, 0, NOW, "")
    with pytest.raises(LicenseError):
        store.save(state)
    assert not store.path.exists()


def test_bad_system_clock_requires_correction(tmp_path, signed_response):
    client = manager(tmp_path, signed_response, now=NOW - 86400)
    with pytest.raises(LicenseError) as caught:
        client.activate(signed_response[1])
    assert caught.value.code == "clock_rollback"
    assert not client.can_use


def test_runtime_executable_uses_embedded_endpoint(monkeypatch):
    from newxky.licensing import configured_server_url, LICENSE_SERVER_URL

    monkeypatch.setenv("NEWXKY_LICENSE_SERVER", "http://127.0.0.1:1")
    monkeypatch.setattr(sys, "_newxky_packaged", True, raising=False)
    assert configured_server_url() == LICENSE_SERVER_URL.rstrip("/")
    monkeypatch.setattr(sys, "_newxky_packaged", False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert configured_server_url() == "http://127.0.0.1:1"
