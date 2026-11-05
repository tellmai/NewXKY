"""Save each imported batch as two re-importable personnel workbooks."""
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4


HEADERS = ("所在的区县", "姓名", "身份证号")


class PersonnelResults:
    def __init__(self, data_dir, candidates, journal=None):
        self.candidates = tuple(candidates)
        self.root = Path(data_dir) / "人员结果" / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"
        self.directory = self.root
        self._lock = Lock()
        self.journal = journal

    def save(self, completed_ids):
        completed = set(completed_ids)
        is_done = lambda c:c.key in completed or c.id_number in completed
        done = [c for c in self.candidates if is_done(c)]
        remaining = [c for c in self.candidates if not is_done(c)]
        with self._lock:
            copied = False
            try:
                self._write_pair(self.directory, done, remaining)
            except PermissionError:
                # Excel can lock an open result file. Keep it intact and save
                # a complete, current pair in a new directory instead.
                directory = self.root / f"更新-{datetime.now():%H%M%S}-{uuid4().hex[:6]}"
                self._write_pair(directory, done, remaining)
                self.directory = directory
                copied = True
            history = self.journal.export() if self.journal else None
            return {"directory": self.directory, "completed": len(done),
                    "incomplete": len(remaining), "saved_copy": copied, "history":history}

    def _write_pair(self, directory, done, remaining):
        directory.mkdir(parents=True, exist_ok=True)
        temporary = []
        try:
            for filename, people in (("已完成人员.xlsx", done), ("未完成人员.xlsx", remaining)):
                path = directory / f".{uuid4().hex}.xlsx"
                temporary.append((path, directory / filename))
                self._write_workbook(path, people)
            # Both workbooks have been generated successfully before replacing
            # any existing result; every individual replacement is atomic.
            for source, destination in temporary:
                source.replace(destination)
        finally:
            for source, _ in temporary:
                source.unlink(missing_ok=True)

    @staticmethod
    def _write_workbook(path, people):
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill

        workbook = Workbook()
        try:
            sheet = workbook.active
            sheet.title = "人员信息"
            sheet.append(HEADERS)
            for row, candidate in enumerate(people, 2):
                values = (candidate.district, candidate.name, candidate.id_number)
                for column, value in enumerate(values, 1):
                    cell = sheet.cell(row, column)
                    cell.value = str(value)
                    cell.data_type = "s"
                    cell.number_format = "@"
                    cell.alignment = Alignment(vertical="center")
            for cell in sheet[1]:
                cell.font = Font(name="Microsoft YaHei", bold=True, color="087F70")
                cell.fill = PatternFill("solid", fgColor="E8F5F1")
                cell.alignment = Alignment(vertical="center")
            sheet.row_dimensions[1].height = 26
            for letter, width in (("A", 22), ("B", 20), ("C", 28)):
                sheet.column_dimensions[letter].width = width
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = f"A1:C{sheet.max_row}"
            workbook.save(path)
        finally:
            workbook.close()
