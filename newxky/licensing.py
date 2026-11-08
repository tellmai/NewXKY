"""One-time online activation with a 40-minute, machine-bound local lease.

The license service is authoritative: it binds a code to the first computer
that activates it and rejects every other computer.  The local lease only
avoids a network round trip when the application is closed and reopened within
the same hour; it is encrypted with Windows DPAPI and still checked against the
machine fingerprint on every start.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import platform
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from . import __version__
from .license_config import LICENSE_SERVER_URL

SESSION_SECONDS = 40 * 60
CLOCK_ROLLBACK_TOLERANCE = 5 * 60
TOUCH_INTERVAL = 15

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_RE = re.compile(r"^[A-HJ-NP-Z2-9]{16}$")
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

ERROR_MESSAGES = {
    "invalid_format": "验证码格式不正确，请按 XXXX-XXXX-XXXX-XXXX 输入。",
    "not_configured": "未配置授权服务器，请联系软件提供者。",
    "network": "无法连接授权服务器，请检查网络后重试。",
    "timeout": "连接授权服务器超时，请检查网络后重试。",
    "invalid_code": "验证码不存在，请核对后重试。",
    "already_used": "这个验证码已在其他电脑激活，不能再次使用。",
    "expired": "这个验证码的 40 分钟使用时间已结束，请使用新的验证码。",
    "disabled": "这个验证码已被停用，请联系软件提供者。",
    "server_error": "授权服务器暂时不可用，请稍后重试。",
    "bad_response": "授权服务器返回了无效数据，请稍后重试。",
    "machine_mismatch": "本机授权记录不属于当前电脑，请重新激活。",
    "clock_rollback": "系统时间异常，请校准 Windows 时间后重试。",
    "local_store": "无法读写本机授权记录，请检查软件目录写入权限。",
}


class LicenseError(RuntimeError):
    """A user-facing activation or lease error."""

    def __init__(self, code: str, message: str | None = None):
        self.code = code
        self.message = message or ERROR_MESSAGES.get(code, ERROR_MESSAGES["server_error"])
        super().__init__(self.message)


def normalize_code(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).upper()
    text = re.sub(r"[\s\-_]+", "", text)
    return text


def format_code(value: str) -> str:
    text = normalize_code(value)
    return "-".join(text[index:index + 4] for index in range(0, len(text), 4))


def valid_code(value: str) -> bool:
    return bool(_CODE_RE.fullmatch(normalize_code(value)))


def format_remaining(seconds: int | float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def configured_server_url() -> str:
    """Return the compiled release address; source runs may use a local override."""
    configured = str(LICENSE_SERVER_URL or "").strip().rstrip("/")
    if not getattr(sys, "frozen", False):
        override = os.environ.get("NEWXKY_LICENSE_SERVER", "").strip().rstrip("/")
        if override:
            configured = override
    return configured


def _valid_server_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme == "https" and parsed.hostname:
        return True
    return parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS


@dataclass
class LicenseState:
    code: str
    machine_id: str
    activated_at: int
    expires_at: int
    clock_offset: int
    last_seen_at: int
    server_url: str

    def remaining(self, now: int | float | None = None) -> int:
        local_now = int(time.time() if now is None else now)
        server_now = local_now + int(self.clock_offset)
        return max(0, int(self.expires_at) - server_now)

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "machine_id": self.machine_id,
            "activated_at": int(self.activated_at),
            "expires_at": int(self.expires_at),
            "clock_offset": int(self.clock_offset),
            "last_seen_at": int(self.last_seen_at),
            "server_url": self.server_url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LicenseState":
        required = ("code", "machine_id", "activated_at", "expires_at",
                    "clock_offset", "last_seen_at", "server_url")
        if not isinstance(data, dict) or any(key not in data for key in required):
            raise ValueError("授权记录不完整")
        if not valid_code(data["code"]) or not re.fullmatch(r"[0-9a-f]{64}", str(data["machine_id"])):
            raise ValueError("授权记录格式错误")
        return cls(
            code=normalize_code(data["code"]),
            machine_id=str(data["machine_id"]),
            activated_at=int(data["activated_at"]),
            expires_at=int(data["expires_at"]),
            clock_offset=int(data["clock_offset"]),
            last_seen_at=int(data["last_seen_at"]),
            server_url=str(data["server_url"]),
        )


def _dpapi_call(data: bytes, *, protect: bool) -> bytes | None:
    if sys.platform != "win32":
        return None
    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        buffer = ctypes.create_string_buffer(data, len(data))

        class DataBlob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        input_blob = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        output_blob = DataBlob()
        if protect:
            crypt32.CryptProtectData.argtypes = [
                ctypes.POINTER(DataBlob), wintypes.LPCWSTR, ctypes.POINTER(DataBlob),
                ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob),
            ]
            crypt32.CryptProtectData.restype = wintypes.BOOL
            ok = crypt32.CryptProtectData(
                ctypes.byref(input_blob), "NewXKY 授权", None, None, None,
                0x01, ctypes.byref(output_blob),
            )
        else:
            crypt32.CryptUnprotectData.argtypes = [
                ctypes.POINTER(DataBlob), ctypes.POINTER(wintypes.LPWSTR),
                ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                wintypes.DWORD, ctypes.POINTER(DataBlob),
            ]
            crypt32.CryptUnprotectData.restype = wintypes.BOOL
            ok = crypt32.CryptUnprotectData(
                ctypes.byref(input_blob), None, None, None, None,
                0x01, ctypes.byref(output_blob),
            )
        if not ok or not output_blob.pbData:
            return None
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            kernel32.LocalFree.argtypes = [ctypes.c_void_p]
            kernel32.LocalFree.restype = ctypes.c_void_p
            kernel32.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))
    except (AttributeError, OSError, ValueError):
        return None


class LicenseStore:
    """Atomic local lease storage; DPAPI-protected on Windows when available."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> LicenseState | None:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError:
            raise LicenseError("local_store")
        try:
            if raw.startswith(b"DPAPI1\n"):
                payload = _dpapi_call(raw[7:], protect=False)
                if payload is None:
                    return None
            elif raw.startswith(b"JSON1\n"):
                payload = base64.b64decode(raw[6:], validate=True)
            else:
                payload = raw
            return LicenseState.from_dict(json.loads(payload.decode("utf-8")))
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def save(self, state: LicenseState):
        payload = json.dumps(state.as_dict(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        protected = _dpapi_call(payload, protect=True)
        raw = b"DPAPI1\n" + protected if protected is not None else b"JSON1\n" + base64.b64encode(payload)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            with temporary.open("wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        except OSError as error:
            raise LicenseError("local_store", f"无法保存本机授权记录：{error}") from error

    def clear(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


def _windows_machine_guid() -> str:
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except (OSError, ImportError, TypeError):
        return ""


def _windows_volume_serial() -> str:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        serial = wintypes.DWORD()
        root = os.environ.get("SystemDrive", "C:") + "\\"
        kernel32.GetVolumeInformationW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
        ]
        kernel32.GetVolumeInformationW.restype = wintypes.BOOL
        if kernel32.GetVolumeInformationW(root, None, 0, ctypes.byref(serial), None, None, None, 0):
            return f"{serial.value:08X}"
    except (AttributeError, OSError):
        pass
    return ""


@lru_cache(maxsize=1)
def current_machine_id() -> str:
    """Stable machine fingerprint; the same installation moved to another PC changes."""
    parts: list[str] = []
    if sys.platform == "win32":
        guid = _windows_machine_guid()
        if guid:
            parts.append(guid)
        volume = _windows_volume_serial()
        if volume:
            parts.append(volume)
    else:
        try:
            parts.append(Path("/etc/machine-id").read_text(encoding="utf-8").strip())
        except OSError:
            pass
    if not any(parts):
        parts = [platform.node(), str(uuid.getnode())]
    material = "NewXKY/1|" + "|".join(parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class LicenseApi:
    """Small JSON client for the NewXKY license service."""

    def __init__(self, base_url: str, timeout: float = 8):
        self.base_url = str(base_url or "").rstrip("/")
        self.timeout = timeout

    def _endpoint(self) -> str:
        if not self.base_url:
            raise LicenseError("not_configured")
        if not _valid_server_url(self.base_url):
            raise LicenseError("not_configured", "授权服务器地址必须使用 HTTPS。")
        return self.base_url + "/api/v1/activate"

    def activate(self, code: str, machine_id: str) -> dict:
        payload = json.dumps({
            "code": normalize_code(code),
            "machine_id": machine_id,
            "app_version": __version__,
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint(),
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": f"NewXKY/{__version__}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read(64 * 1024)
        except urllib.error.HTTPError as error:
            body = error.read(64 * 1024)
            try:
                data = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                data = {}
            code_name = str(data.get("error") or "server_error")
            raise LicenseError(code_name, data.get("message")) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                raise LicenseError("timeout") from error
            raise LicenseError("network") from error
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            raise LicenseError("bad_response") from error
        if not isinstance(data, dict) or not data.get("ok"):
            raise LicenseError(str(data.get("error") or "server_error"), data.get("message"))
        try:
            int(data["expires_at"])
            int(data["server_time"])
            int(data.get("remaining_seconds", 0))
        except (KeyError, TypeError, ValueError) as error:
            raise LicenseError("bad_response") from error
        return data


class LicenseManager:
    """Owns the active lease and all local/server transitions."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        server_url: str | None = None,
        machine_id: str | None = None,
        clock: Callable[[], float] = time.time,
        store: LicenseStore | None = None,
        api: LicenseApi | None = None,
    ):
        self.data_dir = Path(data_dir)
        self.server_url = str(server_url if server_url is not None else configured_server_url()).rstrip("/")
        self.machine_id = machine_id or current_machine_id()
        self.clock = clock
        self.store = store or LicenseStore(self.data_dir / "license.dat")
        self.api = api or LicenseApi(self.server_url)
        self.state: LicenseState | None = None
        self.expired = False
        self.last_error = ""
        self._last_touch = 0.0
        self._anchor_monotonic: float | None = None
        self._anchor_remaining = 0
        self._lock = threading.RLock()

    @property
    def can_use(self) -> bool:
        return not self.expired and self.remaining_seconds() > 0

    def remaining_seconds(self) -> int:
        with self._lock:
            if self.state is None:
                return 0
            from_state = self.state.remaining(self.clock())
            if self._anchor_monotonic is None:
                return from_state
            elapsed = max(0, int(time.monotonic() - self._anchor_monotonic))
            return max(0, min(from_state, self._anchor_remaining - elapsed))

    def _anchor(self, now: int):
        self._anchor_monotonic = time.monotonic()
        self._anchor_remaining = self.state.remaining(now) if self.state is not None else 0

    def restore(self) -> bool:
        """Load a valid lease without requiring the network."""
        with self._lock:
            try:
                state = self.store.load()
            except LicenseError as error:
                self.last_error = error.message
                return False
            if state is None:
                return False
            self.state = state
            if state.machine_id != self.machine_id:
                self.store.clear()
                self.state = None
                self.last_error = ERROR_MESSAGES["machine_mismatch"]
                return False
            now = int(self.clock())
            if now < state.last_seen_at - CLOCK_ROLLBACK_TOLERANCE:
                self.expired = True
                self.last_error = ERROR_MESSAGES["clock_rollback"]
                return False
            if state.remaining(now) <= 0:
                self.expired = True
                self.last_error = ERROR_MESSAGES["expired"]
                return False
            state.last_seen_at = now
            self._write(state)
            self._anchor(now)
            return True
    def activate(self, code: str) -> LicenseState:
        normalized = normalize_code(code)
        if not valid_code(normalized):
            raise LicenseError("invalid_format")
        data = self.api.activate(normalized, self.machine_id)
        with self._lock:
            now = int(self.clock())
            server_time = int(data["server_time"])
            expires_at = int(data["expires_at"])
            if expires_at <= server_time:
                raise LicenseError("expired")
            state = LicenseState(
                code=normalized,
                machine_id=self.machine_id,
                activated_at=int(data.get("activated_at") or server_time),
                expires_at=expires_at,
                clock_offset=server_time - now,
                last_seen_at=now,
                server_url=self.server_url,
            )
            saved = self._write(state)
            self.state = state
            self.expired = False
            if saved:
                self.last_error = ""
            self._last_touch = float(now)
            self._anchor(now)
            return state

    def refresh(self) -> int:
        """Query the server and adopt its authoritative remaining time."""
        with self._lock:
            if self.state is None:
                raise LicenseError("expired")
            code = self.state.code
        data = self.api.activate(code, self.machine_id)
        with self._lock:
            if self.state is None or self.state.code != code:
                return self.remaining_seconds()
            now = int(self.clock())
            server_time = int(data["server_time"])
            expires_at = int(data["expires_at"])
            remaining = int(data.get("remaining_seconds", max(0, expires_at - server_time)))
            if remaining <= 0 or expires_at <= server_time:
                self.expired = True
                self.last_error = ERROR_MESSAGES["expired"]
                self.state.last_seen_at = now
                self._write(self.state)
                raise LicenseError("expired")
            self.state.activated_at = int(data.get("activated_at") or self.state.activated_at)
            self.state.expires_at = expires_at
            self.state.clock_offset = server_time - now
            self.state.last_seen_at = now
            self.state.server_url = self.server_url
            saved = self._write(self.state)
            self.expired = False
            if saved:
                self.last_error = ""
            self._last_touch = float(now)
            self._anchor(now)
            return self.state.remaining(now)

    def touch(self):
        """Persist a periodic last-seen value to make clock rollback visible."""
        with self._lock:
            if self.state is None or self.expired:
                return
            now = float(self.clock())
            if now - self._last_touch < TOUCH_INTERVAL:
                return
            self.state.last_seen_at = int(now)
            self._write(self.state)
            self._last_touch = now

    def reload_lease(self):
        """Update the lease after the application was idle (e.g. system sleep)."""
        with self._lock:
            if self.state is not None and self.state.remaining(self.clock()) <= 0:
                self.expired = True
                self.last_error = ERROR_MESSAGES["expired"]

    def _write(self, state: LicenseState) -> bool:
        try:
            self.store.save(state)
            return True
        except LicenseError as error:
            self.last_error = error.message
            return False
