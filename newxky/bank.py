"""PDF parsing adapted from Answering-S's importers; storage is independent."""
import json
import os
import re
import unicodedata
from dataclasses import asdict
from pathlib import Path

from .models import Bank, Question


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    # Keep numeric punctuation and operators: 1.5, 15 and -15 are different.
    text = re.sub(r"(?<=\d)\.(?=\d)", "小数点", text)
    text = text.replace("%", "百分号").replace("+", "加号").replace("=", "等号")
    text = re.sub(r"[-−](?=\d)", "负号", text)
    return re.sub(r"[\W_]+", "", text)


def question_key(question: Question):
    return normalized(question.stem), tuple(sorted(normalized(v) for v in question.options.values()))


def parse_lines(lines: list[tuple[int, str]], page_count: int, source: str = "") -> Bank:
    bank = Bank(page_count=page_count)
    current: list[tuple[int, str]] = []
    number = None
    section_kind = ""

    def finish():
        if number is None:
            return
        stem, options, answers = [], {}, ()
        active = None
        problems = []
        ended = False
        for _, line in current:
            answer = re.fullmatch(r"(?:参考|正确)?答案\s*[:：]\s*([A-Ha-h\s,，、]+)[。.]?", line)
            if answer:
                if answers:
                    problems.append("出现多个答案标记")
                answers = tuple(dict.fromkeys(re.findall(r"[A-H]", answer[1].upper())))
                ended = True
                continue
            if ended:
                if not re.match(r"^(?:解析|答案解析|说明)\s*[:：]", line):
                    # Explanations are not appended to question/option content.
                    if not any(p == "答案后有附加内容" for p in problems):
                        problems.append("答案后有附加内容")
                continue
            option = re.match(r"^([A-H])[.．、:：)）]\s*(.*)", line)
            if option:
                active = option[1]
                if active in options:
                    problems.append("选项编号重复")
                options[active] = option[2]
            elif active:
                options[active] += line
            else:
                stem.append(line)
        if not answers:
            problems.append("缺少正确答案")
        if not options or not set(answers).issubset(options) or any(not v.strip() for v in options.values()):
            problems.append("答案与选项不匹配或选项为空")
        if not any(stem):
            problems.append("题干为空")
        pages = tuple(sorted({p for p, _ in current}))
        if problems:
            bank.issues.append(f"{source} 第 {number} 题（页 {','.join(map(str, pages))}）：{'；'.join(problems)}")
            return
        values = {normalized(v) for v in options.values()}
        kind = section_kind or ("判断" if values in ({"正确", "错误"}, {"对", "错"}) else "多选" if len(answers) > 1 else "单选")
        bank.questions.append(Question(number, kind, "".join(stem), options, answers, pages, source))

    for page, raw in lines:
        line = raw.strip()
        if not line or re.fullmatch(r"\d{4}\s*年度.*(?:考试复习资料|考试题库)", line):
            continue
        section = re.fullmatch(r"(?:[一二三四五六七八九十\d]+[、．.]\s*)?((?:单项|多项|单|多)选|判断)题", line)
        if section:
            finish()
            number, current = None, []
            section_kind = section[1].replace("单项", "单").replace("多项", "多")
            continue
        start = re.match(r"^(\d{1,5})[、．.]\s*(.*)", line)
        if start:
            finish()
            number, current = int(start[1]), [(page, start[2])]
        elif number is not None:
            current.append((page, line))
    finish()
    if not bank.questions and not bank.issues:
        bank.issues.append(f"{source}：未发现题目。需要包含文字、题号、选项及“正确答案：A”的 PDF；扫描件请先做文字识别。")
    return bank


def load_pdf(path: str | Path, progress=lambda value, total, message: None) -> Bank:
    import pdfplumber

    path = Path(path)
    if path.suffix.lower() != ".pdf":
        raise ValueError("题库仅支持 PDF 文件")
    lines = []
    with pdfplumber.open(path) as pdf:
        count = len(pdf.pages)
        if not count:
            raise ValueError("PDF 没有页面")
        for i, page in enumerate(pdf.pages, 1):
            page_lines = (page.extract_text() or "").splitlines()
            if page_lines and re.fullmatch(r"\s*(?:第\s*)?" + str(i) + r"\s*(?:页)?\s*", page_lines[-1]):
                page_lines.pop()
            if page_lines and page_lines[0].strip() == str(i):
                page_lines.pop(0)
            lines.extend((i, line) for line in page_lines)
            progress(i, count, f"{path.name} · {i}/{count} 页")
            page.flush_cache()
    result = parse_lines(lines, count, path.name)
    result.sources = [str(path.resolve())]
    return result


def merge_banks(banks: list[Bank]) -> Bank:
    result = Bank()
    entries = {}
    for bank in banks:
        result.sources.extend(p for p in bank.sources if p not in result.sources)
        result.issues.extend(bank.issues)
        result.page_count += bank.page_count
        result.duplicates += bank.duplicates
        for question in bank.questions:
            key = question_key(question)
            answer = frozenset(normalized(question.options[a]) for a in question.answers)
            if key in entries:
                old_answer, old = entries[key]
                if old_answer != answer:
                    raise ValueError(f"答案冲突：{old.source} 第 {old.number} 题与 {question.source} 第 {question.number} 题；请先核对原文。原题库未修改。")
                result.duplicates += 1
                continue
            entries[key] = answer, question
            result.questions.append(question)
    return result


def save_bank(bank: Bank, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump({"version": 1, **asdict(bank)}, file, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


def read_bank(path: Path) -> Bank:
    if not path.exists():
        return Bank()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError("题库缓存版本不兼容，请重新导入 PDF")
    questions = [Question(**(q | {"answers": tuple(q["answers"]), "pages": tuple(q["pages"])})) for q in data["questions"]]
    return Bank(questions, data["issues"], data["sources"], data["page_count"], data["duplicates"])
