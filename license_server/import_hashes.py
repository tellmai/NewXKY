"""Import pre-hashed license codes into an existing NewXKY database.

This is a small, standard-library-only helper for adding a new batch to a live
server without touching existing activation records.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import time
from pathlib import Path

SCHEMA = """
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
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    with args.csv_file.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            rows.append((
                str(row["code_hash"]).strip(),
                int(row["batch"]),
                int(row["serial"]),
                int(time.time()),
            ))
    connection = sqlite3.connect(args.db, timeout=10)
    try:
        connection.execute("PRAGMA busy_timeout=5000")
        connection.executescript(SCHEMA)
        before = connection.total_changes
        connection.executemany(
            "INSERT OR IGNORE INTO licenses(code_hash,batch,serial,created_at) VALUES(?,?,?,?)",
            rows,
        )
        inserted = connection.total_changes - before
        connection.commit()
        total = connection.execute("SELECT COUNT(*) FROM licenses").fetchone()[0]
    finally:
        connection.close()
    print(f"IMPORTED inserted={inserted} skipped={len(rows) - inserted} total={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
