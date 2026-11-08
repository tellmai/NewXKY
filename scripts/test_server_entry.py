"""Entry point for the self-contained Windows test license server."""
from __future__ import annotations

import os
import sys
from pathlib import Path

root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
os.environ.setdefault("NEWXKY_LICENSE_DB", str(root / "test-license" / "licenses.db"))
os.environ.setdefault("NEWXKY_LICENSE_HOST", "127.0.0.1")
os.environ.setdefault("NEWXKY_LICENSE_PORT", "18787")
os.environ.setdefault("NEWXKY_ADMIN_TOKEN", "newxky-test-only")

from license_server.server import main

if __name__ == "__main__":
    raise SystemExit(main())
