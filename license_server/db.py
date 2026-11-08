"""SQLite persistence for one-time, machine-bound license activation."""
from __future__ import annotations

import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .codes import hash_code, normalize_code, valid_code

MACHINE_RE = re.compile(r"^[0-9a-f]{64}$")
SESSION_SECONDS = 40 * 60


class ActivationError(Exception):
    def __init__(self, code: str, message: str, http_status: int):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)

    def as_dict(self) -> dict:
        return {"ok": False, "error": self.code, "message": self.message}


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS licenses (
    code_hash TEXT PRIMARY KEY,
    batch INTEGER NOT NULL,
    serial INTEGER NOT NULL,
    machine_id TEXT,
    activated_at INTEGER,
    expires_at INTEGER,
    last_seen_at INTEGER,
    disabled INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_licenses_machine ON licenses(machine_id);
CREATE INDEX IF NOT EXISTS idx_licenses_batch_serial ON licenses(batch, serial);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


@contextmanager
def session(path: str | Path):
    connection = connect(path)
    try:
        yield connection
    finally:
        connection.close()


def initialize(path: str | Path):
    with session(path) as connection:
        connection.executescript(SCHEMA)


def seed_codes(path: str | Path, entries) -> int:
    """Insert (batch, serial, code) entries; existing hashes are left untouched."""
    initialize(path)
    rows = []
    now = int(time.time())
    for batch, serial, code in entries:
        normalized = normalize_code(code)
        if not valid_code(normalized):
            raise ValueError(f"invalid code at batch {batch}, serial {serial}")
        rows.append((hash_code(normalized), int(batch), int(serial), now))
    with session(path) as connection:
        before = connection.total_changes
        connection.executemany(
            "INSERT OR IGNORE INTO licenses(code_hash,batch,serial,created_at) VALUES(?,?,?,?)",
            rows,
        )
        return connection.total_changes - before


def activate(path: str | Path, code: str, machine_id: str, *, now: int | None = None,
             duration: int = SESSION_SECONDS) -> dict:
    normalized = normalize_code(code)
    if not valid_code(normalized):
        raise ActivationError("invalid_code", "验证码格式不正确，请核对后重试。", 400)
    if not MACHINE_RE.fullmatch(str(machine_id or "")):
        raise ActivationError("bad_request", "设备标识无效。", 400)
    moment = int(time.time() if now is None else now)
    digest = hash_code(normalized)
    initialize(path)
    connection = connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT machine_id, activated_at, expires_at, disabled FROM licenses WHERE code_hash=?",
            (digest,),
        ).fetchone()
        if row is None:
            raise ActivationError("invalid_code", "验证码不存在，请核对后重试。", 404)
        if row["disabled"]:
            raise ActivationError("disabled", "这个验证码已被停用，请联系软件提供者。", 403)
        if row["machine_id"] is None:
            activated_at = moment
            expires_at = moment + int(duration)
            cursor = connection.execute(
                "UPDATE licenses SET machine_id=?, activated_at=?, expires_at=?, last_seen_at=? "
                "WHERE code_hash=? AND machine_id IS NULL",
                (machine_id, activated_at, expires_at, moment, digest),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise ActivationError("already_used", "这个验证码已在其他电脑激活，不能再次使用。", 409)
            connection.commit()
            return {
                "ok": True,
                "status": "active",
                "activated_at": activated_at,
                "expires_at": expires_at,
                "server_time": moment,
                "remaining_seconds": max(0, expires_at - moment),
            }
        if row["machine_id"] != machine_id:
            raise ActivationError("already_used", "这个验证码已在其他电脑激活，不能再次使用。", 409)
        expires_at = int(row["expires_at"] or 0)
        remaining = max(0, expires_at - moment)
        if remaining <= 0:
            connection.execute(
                "UPDATE licenses SET last_seen_at=? WHERE code_hash=?", (moment, digest)
            )
            connection.commit()
            raise ActivationError("expired", "这个验证码的 40 分钟使用时间已结束，请使用新的验证码。", 410)
        connection.execute(
            "UPDATE licenses SET last_seen_at=? WHERE code_hash=?", (moment, digest)
        )
        connection.commit()
        return {
            "ok": True,
            "status": "active",
            "activated_at": int(row["activated_at"] or moment),
            "expires_at": expires_at,
            "server_time": moment,
            "remaining_seconds": remaining,
        }
    except ActivationError:
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def stats(path: str | Path, *, now: int | None = None) -> dict:
    initialize(path)
    moment = int(time.time() if now is None else now)
    with session(path) as connection:
        total = connection.execute("SELECT COUNT(*) FROM licenses").fetchone()[0]
        used = connection.execute(
            "SELECT COUNT(*) FROM licenses WHERE machine_id IS NOT NULL"
        ).fetchone()[0]
        active = connection.execute(
            "SELECT COUNT(*) FROM licenses WHERE machine_id IS NOT NULL "
            "AND expires_at>? AND disabled=0", (moment,)
        ).fetchone()[0]
    return {"ok": True, "total": total, "used": used, "active": active,
            "unused": total - used, "server_time": moment}
