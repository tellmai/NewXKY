"""Personnel import and the explicitly advanced, in-memory exam queue."""
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_URL = "https://ks.cqsdx.cn/exam/"


@dataclass(frozen=True)
class Candidate:
    row: int
    district: str
    name: str = field(repr=False)
    id_number: str = field(repr=False)

    @property
    def masked_id(self):
        return self.id_number[:3] + "*" * (len(self.id_number) - 7) + self.id_number[-4:]


@dataclass
class IdentityImport:
    candidates: list[Candidate]
    issues: list[str]
    sheet: str


@dataclass(frozen=True)
class SiteConfig:
    url: str = DEFAULT_URL
    chrome_path: str = ""
    timeout_ms: int = 20000
    allow_local_test: bool = False

    def validate(self):
        p = urlparse(self.url)
        if p.username or p.password or p.query or p.fragment:
            raise ValueError("考试入口网址不能包含账号、查询参数或片段")
        local = self.allow_local_test and p.hostname in {"127.0.0.1", "localhost"}
        if not local and (p.scheme != "https" or p.hostname != "ks.cqsdx.cn" or p.port not in (None, 443)):
            raise ValueError("请选择 https://ks.cqsdx.cn/exam/ 考试入口")
        if local and p.scheme != "http":
            raise ValueError("本地测试地址须使用 HTTP")
        if p.path.rstrip("/") not in {"/exam", "/exam/index"}:
            raise ValueError("请选择区县选择入口 /exam/")
        if self.chrome_path and not Path(self.chrome_path).is_file():
            raise ValueError("选择的浏览器文件不存在，请刷新列表或重新选择")


def load_identities(path):
    from openpyxl import load_workbook

    if Path(path).suffix.lower() != ".xlsx":
        raise ValueError("请选择 .xlsx 人员信息文件")
    wb = load_workbook(path, read_only=True, data_only=True)
    required = ("所在的区县", "姓名", "身份证号")
    try:
        for sheet in wb:
            rows = sheet.iter_rows(values_only=True)
            names = [str(v or "").strip() for v in next(rows, ())]
            if not all(n in names for n in required):
                continue
            indices = [names.index(n) for n in required]
            candidates, issues, seen = [], [], set()
            for number, cells in enumerate(rows, 2):
                chosen = [cells[i] if i < len(cells) else None for i in indices]
                if all(v is None or not str(v).strip() for v in chosen):
                    continue
                district, name, raw_id = chosen
                reason = ""
                if any(v is None or not str(v).strip() for v in chosen):
                    reason = "区县、姓名、身份证号均为必填"
                elif not isinstance(raw_id, str):
                    if (isinstance(raw_id, bool) or not isinstance(raw_id, (int, float))
                            or raw_id != int(raw_id) or len(str(int(raw_id))) != 15):
                        reason = "身份证号须按文本保存；数值格式可能丢失精度，请从原始资料重新录入"
                    else:
                        raw_id = str(int(raw_id))
                if not reason:
                    raw_id = raw_id.strip().upper()
                    if not re.fullmatch(r"(?:[0-9]{15}|[0-9]{17}[0-9X])", raw_id):
                        reason = "身份证号应为 15 位或 18 位，末位可为 X"
                    elif raw_id in seen:
                        reason = "人员重复，已保留首次出现的记录"
                if reason:
                    issues.append(f"第 {number} 行：{reason}")
                    continue
                seen.add(raw_id)
                candidates.append(Candidate(number, str(district).strip(), str(name).strip(), raw_id))
            return IdentityImport(candidates, issues, sheet.title)
        raise ValueError("找不到包含「所在的区县、姓名、身份证号」三列表头的工作表")
    finally:
        wb.close()


@dataclass
class CandidateRecord:
    candidate: Candidate
    status: str = "待考试"
    detail: str = ""


class ExamQueue:
    def __init__(self, candidates=()):
        self.records = [CandidateRecord(c) for c in candidates]
        self.position = 0
        self.started = False

    @property
    def current(self):
        return self.records[self.position] if self.position < len(self.records) else None

    @property
    def pending(self):
        return self.records[self.position:]

    def add(self, candidates):
        seen = {r.candidate.id_number for r in self.records}
        for candidate in candidates:
            if candidate.id_number not in seen:
                self.records.append(CandidateRecord(candidate))
                seen.add(candidate.id_number)

    def reorder(self, rows):
        pending = {r.candidate.row: r for r in self.pending}
        if len(rows) != len(pending) or set(rows) != set(pending):
            raise ValueError("待考列表发生变化，请重新调整顺序")
        if self.current and self.current.status not in {"待考试", "加载失败"} and rows[0] != self.current.candidate.row:
            raise ValueError("当前人员正在考试，请完成或跳过后再调整其位置")
        self.records[self.position:] = [pending[row] for row in rows]

    def remove(self, rows):
        selected = set(rows)
        self.records[self.position:] = [r for r in self.pending
            if r.candidate.row not in selected or r.status not in {"待考试", "加载失败"}]

    def begin(self):
        record = self.current
        if record is None or record.status not in {"待考试", "加载失败"}:
            raise ValueError("请先完成或跳过当前人员，再加载下一人")
        self.started = True
        record.status, record.detail = "正在加载", ""
        return record.candidate

    def finish(self, submitted, reason):
        record = self.current
        if record is None:
            return
        record.status, record.detail = ("已完成" if submitted else "已暂停"), reason
        if submitted:
            self.position += 1

    def skip(self):
        if self.current is not None:
            self.current.status = "已跳过"
            self.position += 1
