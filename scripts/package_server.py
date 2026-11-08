"""Package the license service and seeded database for server deployment."""
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
from license_server import db
from newxky import __version__


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "dist" / f"NewXKY-LicenseServer-V{__version__}.zip")
    parser.add_argument("--db", type=Path,
                        default=ROOT / "license_server" / "data" / "licenses.db")
    args = parser.parse_args()
    database = args.db.resolve()
    if not database.is_file():
        parser.error(f"database missing: {database}")
    stats = db.stats(database)
    if not stats["total"]:
        parser.error("database contains no codes")
    with db.session(database) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "dist").resolve()):
        parser.error("output must stay inside dist")

    root_name = "NewXKY-LicenseServer"
    service = ROOT / "license_server"
    files = [
        service / "README.md",
        service / "Caddyfile.example",
        service / "newxky-license.service.example",
        service / "deploy.sh",
        service / "codes.py",
        service / "db.py",
        service / "server.py",
        service / "generate_codes.py",
        service / "import_codes.py",
        service / "__init__.py",
    ]
    files = [path for path in files if path.is_file()]
    metadata = {
        "format": "license-server",
        "version": __version__,
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "database_sha256": digest(database),
        "database": stats,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + "." + uuid4().hex + ".partial")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(files):
                archive.write(path, f"{root_name}/license_server/{path.relative_to(service).as_posix()}")
            archive.writestr(
                f"{root_name}/license_server/data/licenses.db", database.read_bytes()
            )
            archive.writestr(
                f"{root_name}/build-info.json",
                json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
            )
        with zipfile.ZipFile(temporary) as archive:
            names = archive.namelist()
            assert archive.testzip() is None
            assert not any(name.lower().endswith((".xlsx", ".xls", ".csv")) for name in names)
            assert f"{root_name}/license_server/data/licenses.db" in names
            assert f"{root_name}/license_server/server.py" in names
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    checksum = digest(output)
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{checksum}  {output.name}\n", encoding="utf-8"
    )
    print("SERVER_PACKAGE_READY", output, output.stat().st_size, checksum,
          json.dumps(stats, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
