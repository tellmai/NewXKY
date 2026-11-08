"""Generate the 20 distribution workbooks and seed the license database."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Side, Border
from openpyxl.utils import get_column_letter

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from license_server.codes import format_code, generate_code
    from license_server.db import initialize, seed_codes
else:
    from .codes import format_code, generate_code
    from .db import initialize, seed_codes

ROOT = Path(__file__).resolve().parents[1]
HEADER_FILL = PatternFill("solid", fgColor="0B7F70")
HEADER_FONT = Font(color="FFFFFF", bold=True)
THIN = Side(style="thin", color="D8E3ED")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_workbook(path: Path, entries: list[tuple[int, int, str]], batch: int):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = f"第{batch:02d}批"
    sheet.append(["序号", "验证码", "使用说明"])
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
    for serial, _, code in entries:
        sheet.append([serial, format_code(code), "首次激活的电脑可用 40 分钟，验证码仅限使用一次"])
    widths = (10, 24, 62)
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:C{sheet.max_row}"
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.border = BORDER
            cell.alignment = Alignment(vertical="center")
    workbook.save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "授权码-40分钟")
    parser.add_argument("--db", type=Path,
                        default=Path(os.environ.get("NEWXKY_LICENSE_DB",
                                                   str(ROOT / "license_server" / "data" / "licenses.db"))))
    parser.add_argument("--count", type=int, default=10000)
    parser.add_argument("--files", type=int, default=20)
    parser.add_argument("--per-file", type=int, default=500)
    parser.add_argument("--reset-db", action="store_true", help="delete the target database before seeding")
    args = parser.parse_args()
    if args.count != args.files * args.per_file:
        parser.error("--count 必须等于 --files × --per-file")
    if args.count <= 0 or args.files <= 0 or args.per_file <= 0:
        parser.error("数量必须大于 0")

    args.output.mkdir(parents=True, exist_ok=True)
    if args.reset_db:
        for suffix in ("", "-wal", "-shm"):
            Path(str(args.db) + suffix).unlink(missing_ok=True)
    initialize(args.db)

    seen: set[str] = set()
    batches: list[list[tuple[int, int, str]]] = []
    for batch in range(1, args.files + 1):
        entries = []
        for serial in range(1, args.per_file + 1):
            while True:
                code = generate_code()
                if code not in seen:
                    seen.add(code)
                    break
            entries.append((batch, serial, code))
        batches.append(entries)

    manifest = {
        "format": 1,
        "product": "NewXKY",
        "version": "1.0.9",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": args.count,
        "files": [],
    }
    for batch, entries in enumerate(batches, 1):
        path = args.output / f"NewXKY授权码-{batch:02d}.xlsx"
        write_workbook(path, entries, batch)
        manifest["files"].append({
            "name": path.name,
            "batch": batch,
            "count": len(entries),
            "sha256": sha256(path),
        })
        print(f"WROTE {path} ({len(entries)} codes)", flush=True)

    inserted = 0
    for entries in batches:
        inserted += seed_codes(args.db, entries)
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"SEEDED {args.db}: inserted={inserted} total={args.count}", flush=True)
    print(f"MANIFEST {args.output / 'manifest.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
