"""NewXKY license service.

Runs behind an HTTPS reverse proxy.  The service stores only SHA-256 hashes of
codes, binds the first successful activation to a machine fingerprint, and
returns the authoritative 40-minute expiry.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from collections import defaultdict, deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from license_server.db import ActivationError, activate, initialize, stats
else:
    from .db import ActivationError, activate, initialize, stats

MAX_BODY = 8 * 1024
ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "licenses.db"


class RateLimiter:
    def __init__(self, limit: int = 120, window: int = 60):
        self.limit = limit
        self.window = window
        self.events = defaultdict(deque)
        self.lock = Lock()

    def allow(self, key: str) -> bool:
        moment = time.monotonic()
        with self.lock:
            bucket = self.events[key]
            while bucket and moment - bucket[0] > self.window:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(moment)
            return True


class Handler(BaseHTTPRequestHandler):
    server_version = "NewXKYLicense/1.0"
    sys_version = ""

    def log_message(self, format, *args):
        sys.stdout.write("%s - %s\n" % (self.address_string(), format % args))
        sys.stdout.flush()

    def _send(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _client_key(self) -> str:
        if os.environ.get("NEWXKY_TRUST_PROXY") == "1":
            forwarded = self.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",", 1)[0].strip()
        return self.client_address[0]

    def _body(self) -> dict:
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type.lower():
            raise ActivationError("bad_request", "请求格式必须是 JSON。", 400)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ActivationError("bad_request", "请求长度无效。", 400) from error
        if length <= 0 or length > MAX_BODY:
            raise ActivationError("bad_request", "请求内容为空或过大。", 400)
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            raise ActivationError("bad_request", "请求 JSON 无效。", 400) from error
        if not isinstance(data, dict):
            raise ActivationError("bad_request", "请求 JSON 必须是对象。", 400)
        return data

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            self._send(HTTPStatus.OK, {"ok": True, "service": "NewXKYLicense/1.0"})
            return
        if path == "/api/v1/time":
            self._send(HTTPStatus.OK, {"ok": True, "server_time": int(time.time())})
            return
        if path == "/api/v1/admin/stats":
            token = os.environ.get("NEWXKY_ADMIN_TOKEN", "")
            supplied = self.headers.get("X-Admin-Token", "")
            if not token or supplied != token:
                self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
                return
            self._send(HTTPStatus.OK, stats(self.server.db_path))
            return
        self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path != "/api/v1/activate":
            self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        if not self.server.limiter.allow(self._client_key()):
            self._send(HTTPStatus.TOO_MANY_REQUESTS,
                       {"ok": False, "error": "rate_limited", "message": "请求过于频繁，请稍后再试。"})
            return
        try:
            data = self._body()
            result = activate(
                self.server.db_path,
                str(data.get("code", "")),
                str(data.get("machine_id", "")),
            )
            self._send(HTTPStatus.OK, result)
        except ActivationError as error:
            self._send(error.http_status, error.as_dict())
        except Exception:
            traceback.print_exc()
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR,
                       {"ok": False, "error": "server_error", "message": "授权服务器暂时不可用，请稍后重试。"})


class LicenseServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128

    def __init__(self, address, db_path):
        self.db_path = Path(db_path)
        try:
            limit = max(1, int(os.environ.get("NEWXKY_RATE_LIMIT", "120")))
        except ValueError:
            limit = 120
        self.limiter = RateLimiter(limit=limit)
        super().__init__(address, Handler)


def main() -> int:
    db_path = Path(os.environ.get("NEWXKY_LICENSE_DB", str(DEFAULT_DB))).resolve()
    host = os.environ.get("NEWXKY_LICENSE_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("NEWXKY_LICENSE_PORT", "8787"))
    except ValueError:
        print("NEWXKY_LICENSE_PORT must be an integer", file=sys.stderr)
        return 2
    initialize(db_path)
    server = LicenseServer((host, port), db_path)
    print(f"NewXKY license service listening on http://{host}:{port}", flush=True)
    print(f"Database: {db_path}", flush=True)
    print("Put this service behind HTTPS before distributing the client.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
