"""Package a Windows functional-test bundle with its own local license server."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from newxky import __version__


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--server-exe", type=Path, required=True)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "dist" / f"NewXKY-V{__version__}-WindowsTest.zip")
    args = parser.parse_args()
    app = args.app_dir.resolve()
    server = args.server_exe.resolve()
    output = args.output.resolve()
    dist = (ROOT / "dist").resolve()
    if not app.is_relative_to(dist) or not output.is_relative_to(dist):
        parser.error("app and output must be inside dist")
    if not (app / "NewXKY.exe").is_file() or not server.is_file():
        parser.error("app or test server executable missing")
    if not (app / "test-license" / "licenses.db").is_file():
        parser.error("test-license/licenses.db missing")
    if not (app / "test-license" / "测试验证码.txt").is_file():
        parser.error("test-license/测试验证码.txt missing")

    files = [
        path for path in (app / "_internal").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]
    files.extend([
        app / "NewXKY.exe",
        app / "启动测试版.cmd",
        app / "停止测试服务.cmd",
        app / "测试说明.txt",
        app / "使用说明.md",
        app / "THIRD_PARTY_NOTICES.md",
        app / "build-info.json",
        app / "题库" / "default-bank.json",
        server,
        app / "test-license" / "licenses.db",
        app / "test-license" / "测试验证码.txt",
    ])
    for path in files:
        if not path.is_file():
            parser.error(f"missing bundle file: {path}")

    metadata = {
        "format": "windows-functional-test",
        "product": "NewXKY",
        "version": __version__,
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "license_server_url": "http://127.0.0.1:18787",
        "test_codes": 5,
        "note": "仅供功能验收，不能作为正式分发包",
        "app_sha256": digest(app / "NewXKY.exe"),
        "server_sha256": digest(server),
        "database_sha256": digest(app / "test-license" / "licenses.db"),
    }
    (app / "test-license" / "build-info.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    files.append(app / "test-license" / "build-info.json")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + "." + uuid4().hex + ".partial")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(files):
                archive.write(path, (Path("NewXKY") / path.relative_to(app)).as_posix())
        with zipfile.ZipFile(temporary) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            assert "NewXKY/NewXKY.exe" in names
            assert "NewXKY/NewXKY-TestLicenseServer.exe" in names
            assert "NewXKY/test-license/licenses.db" in names
            assert all(
                Path(name).parts[1] not in {"data", "license.dat", "人员记录", "人员结果"}
                for name in names
            )
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    checksum = digest(output)
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{checksum}  {output.name}\n", encoding="utf-8"
    )
    print("TEST_BUNDLE_READY", output, output.stat().st_size, checksum, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
