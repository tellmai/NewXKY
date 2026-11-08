from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from license_server import db
from license_server.codes import generate_code
from license_server.db import ActivationError
from license_server.server import LicenseServer
from newxky.licensing import (
    LicenseError,
    LicenseManager,
    format_code,
    format_remaining,
    normalize_code,
    valid_code,
)


@pytest.fixture()
def service(tmp_path):
    database = tmp_path / "licenses.db"
    code = generate_code()
    db.seed_codes(database, [(1, 1, code)])
    server = LicenseServer(("127.0.0.1", 0), database)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "url": f"http://127.0.0.1:{server.server_address[1]}",
            "database": database,
            "code": code,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def manager(tmp_path, service, machine="a" * 64, now=1_800_000_000):
    return LicenseManager(
        tmp_path / "data",
        server_url=service["url"],
        machine_id=machine,
        clock=lambda: now,
    )


def test_code_normalization_and_formatting():
    code = generate_code()
    spaced = format_code(code).lower().replace("-", " ")
    assert normalize_code(spaced) == code
    assert valid_code(spaced)
    assert not valid_code("AAAA")
    assert format_remaining(2399) == "39:59"
    assert format_remaining(-1) == "00:00"


def test_first_activation_binds_and_same_machine_resumes(tmp_path, service):
    original = manager(tmp_path, service)
    state = original.activate(service["code"])
    assert state.machine_id == "a" * 64
    assert state.remaining(state.last_seen_at) >= 2395

    resumed = manager(tmp_path, service, now=1_800_000_030)
    assert resumed.restore()
    assert resumed.remaining_seconds() >= 2360


def test_other_machine_cannot_use_the_same_code(tmp_path, service):
    original = manager(tmp_path, service)
    original.activate(service["code"])
    other = manager(tmp_path / "other", service, machine="b" * 64)
    with pytest.raises(LicenseError) as caught:
        other.activate(service["code"])
    assert caught.value.code == "already_used"
    assert not other.restore()


def test_expired_code_is_permanent_for_same_machine(tmp_path, service):
    original = manager(tmp_path, service)
    original.activate(service["code"])
    data = tmp_path / "data" / "license.dat"
    assert data.exists()
    later = manager(tmp_path, service, now=1_800_003_700)
    assert not later.restore()
    assert later.expired
    assert not later.can_use


def test_copied_local_lease_is_rejected_on_another_machine(tmp_path, service):
    original = manager(tmp_path / "source", service)
    original.activate(service["code"])
    copied = tmp_path / "target" / "license.dat"
    copied.parent.mkdir(parents=True)
    copied.write_bytes((tmp_path / "source" / "data" / "license.dat").read_bytes())
    other = LicenseManager(
        tmp_path / "target", server_url=service["url"], machine_id="b" * 64,
        clock=lambda: 1_800_000_010,
    )
    assert not other.restore()
    assert "不属于当前电脑" in other.last_error


def test_offline_restart_within_the_hour(tmp_path, service):
    original = manager(tmp_path, service)
    original.activate(service["code"])
    service["url"] = "http://127.0.0.1:1"
    offline = manager(tmp_path, service, now=1_800_000_100)
    assert offline.restore()
    assert offline.remaining_seconds() > 0


def test_clock_rollback_is_rejected(tmp_path, service):
    original = manager(tmp_path, service)
    original.activate(service["code"])
    rolled_back = manager(tmp_path, service, now=1_799_990_000)
    assert not rolled_back.restore()
    assert "系统时间异常" in rolled_back.last_error


def test_database_expiry_is_authoritative():
    code = generate_code()
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        database = Path(tmp) / "licenses.db"
        db.seed_codes(database, [(1, 1, code)])
        first = db.activate(database, code, "a" * 64, now=100)
        assert first["remaining_seconds"] == 2400
        with pytest.raises(ActivationError) as caught:
            db.activate(database, code, "a" * 64, now=2501)
        assert caught.value.code == "expired"


def test_http_endpoint_rejects_other_machine(service):
    body = json.dumps({"code": service["code"], "machine_id": "a" * 64}).encode()
    request = Request(
        service["url"] + "/api/v1/activate", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=5) as response:
        assert response.status == 200
    body = json.dumps({"code": service["code"], "machine_id": "b" * 64}).encode()
    request = Request(
        service["url"] + "/api/v1/activate", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(HTTPError) as caught:
        urlopen(request, timeout=5)
    assert caught.value.code == 409
    assert json.loads(caught.value.read())["error"] == "already_used"
