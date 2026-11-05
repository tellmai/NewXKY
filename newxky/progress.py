"""Durable submission receipts and date-based, re-importable personnel exports."""
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from .identities import Candidate
from .personnel_results import PersonnelResults


class ProgressJournal:
    def __init__(self, directory, clock=datetime.now):
        self.directory = Path(directory)
        self.clock = clock
        self._export_lock = Lock()
        self.directory.mkdir(parents=True,exist_ok=True)
        self.path = self.directory / "progress.sqlite3"
        with self._database() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS people (
                person_id INTEGER PRIMARY KEY, district TEXT NOT NULL, name TEXT NOT NULL,
                id_number TEXT NOT NULL, added_on TEXT NOT NULL, completed_on TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(district,name,id_number))""")
            if "active" not in {row[1] for row in db.execute("PRAGMA table_info(people)")}:
                db.execute("ALTER TABLE people ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
            db.execute("""CREATE TABLE IF NOT EXISTS receipts (
                session_id TEXT PRIMARY KEY, completed_at TEXT NOT NULL,
                person_id INTEGER REFERENCES people(person_id))""")

    @contextmanager
    def _database(self):
        with closing(sqlite3.connect(self.path,timeout=5)) as db:
            db.row_factory = sqlite3.Row
            with db:
                yield db

    @property
    def total(self):
        with self._database() as db:
            return db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]

    def register(self, candidates, *, replace_pending=False):
        day = self.clock().date().isoformat()
        with self._database() as db:
            if replace_pending:
                db.execute("UPDATE people SET active=0 WHERE completed_on IS NULL")
            db.executemany("""INSERT INTO people(district,name,id_number,added_on) VALUES(?,?,?,?)
                            ON CONFLICT(district,name,id_number) DO UPDATE SET active=1""",
                           [(*candidate.key,day) for candidate in candidates])

    def record_success(self, session_id, candidate=None):
        if not isinstance(session_id,str) or not session_id.strip():
            raise ValueError("成功交卷记录缺少会话编号")
        moment = self.clock().isoformat(timespec="seconds")
        with self._database() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM receipts WHERE session_id=?",(session_id,)).fetchone():
                return db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
            person = None
            if candidate is not None:
                db.execute("INSERT OR IGNORE INTO people(district,name,id_number,added_on) VALUES(?,?,?,?)",
                           (*candidate.key,moment[:10]))
                person = db.execute("SELECT person_id FROM people WHERE district=? AND name=? AND id_number=?",
                                    candidate.key).fetchone()[0]
            inserted = db.execute("INSERT OR IGNORE INTO receipts VALUES(?,?,?)",(session_id,moment,person)).rowcount
            if inserted and person is not None:
                db.execute("UPDATE people SET completed_on=COALESCE(completed_on,?) WHERE person_id=?",
                           (moment[:10],person))
            return db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]

    def export(self):
        """Excel is a projection: a locked workbook cannot lose the receipt."""
        with self._export_lock:
            day = self.clock().date().isoformat()
            with self._database() as db:
                people = db.execute("SELECT * FROM people ORDER BY person_id").fetchall()
                today_ids = {row[0] for row in db.execute(
                    "SELECT DISTINCT person_id FROM receipts WHERE substr(completed_at,1,10)=?",(day,))}
            completed,remaining,today = [],[],[]
            for row in people:
                candidate = Candidate(row["person_id"],row["district"],row["name"],row["id_number"])
                if row["completed_on"]:
                    completed.append(candidate)
                elif row["active"]:
                    remaining.append(candidate)
                if row["person_id"] in today_ids:
                    today.append(candidate)
            outputs = (("已完成",f"已完成{day}.xlsx",today),
                       ("已完成","已完成总表.xlsx",completed),
                       ("未完成",f"未完成{day}.xlsx",remaining),
                       ("未完成","未完成总表.xlsx",remaining))
            copies = []
            for subfolder,name,candidates in outputs:
                folder = self.directory / subfolder
                folder.mkdir(parents=True,exist_ok=True)
                path = folder / name
                temporary = folder / f".{uuid4().hex}.xlsx"
                try:
                    PersonnelResults._write_workbook(temporary,candidates)
                    try:
                        temporary.replace(path)
                    except PermissionError:
                        copy = folder / f"{path.stem}-更新{self.clock():%H%M%S}-{uuid4().hex[:6]}.xlsx"
                        temporary.replace(copy)
                        copies.append(copy)
                finally:
                    temporary.unlink(missing_ok=True)
            return {"completed":len(completed),"incomplete":len(remaining),"copies":copies,
                    "directory":self.directory,"total":self.total}
