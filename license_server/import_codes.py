"""Import existing distribution workbooks into the license database."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from openpyxl import load_workbook

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from license_server.db import initialize, seed_codes
else:
    from .db import initialize, seed_codes

ROOT = Path(__file__).resolve().parents[1]


def workbook_codes(path: Path):
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    header = next(rows, None)
    if not header or "验证码" not in [str(value or "").strip() for value in header]:
        raise ValueError(f"{path.name}: 缺少“验证码”列")
    column = [str(value or "").strip() for value in header].index("验证码")
    for serial, row in enumerate(rows, 1):
        if not row or column >= len(row):
            continue
        code = str(row[column] or "").strip()
        if code:
            yield serial, code
    workbook.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--db", type=Path,
                        default=Path(ROOT / "license_server" / "data" / "licenses.db"))
    parser.add_argument("--reset-db", action="store_true")
    args = parser.parse_args()
    if args.reset_db:
        for suffix in ("", "-wal", "-shm"):
            Path(str(args.db) + suffix).unlink(missing_ok=True)
    initialize(args.db)
    total = 0
    for path in args.files:
        entries = []
        for serial, code in workbook_codes(path):
            entries.append((path.stem, serial, code))
        inserted = seed_codes(args.db, entries)
        total += inserted
        print(f"IMPORTED {path.name}: {len(entries)} rows, inserted {inserted}", flush=True)
    print(f"DONE inserted={total} db={args.db}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
