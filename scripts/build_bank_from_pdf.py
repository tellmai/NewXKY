"""Build the bundled question bank JSON from the supplied review PDF."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from newxky.bank import normalized, question_key, save_bank
from newxky.default_bank import SOURCE_LABEL
from newxky.models import Bank, Question

TITLE = re.compile(r"\d{4}\s*年度.*(?:考试复习资料|考试题库)")


def parse_lines(lines: list[tuple[int, str]], page_count: int, source: str) -> Bank:
    bank = Bank(page_count=page_count)
    current: list[tuple[int, str]] = []
    number = None
    section_kind = ""

    def finish():
        nonlocal number, current
        if number is None:
            return
        stem, options, answers = [], {}, ()
        active = None
        problems = []
        ended = False
        for _, line in current:
            answer = re.fullmatch(
                r"(?:参考|正确)?答案\s*[:：]\s*([A-Ha-h\s,，、]+)[。.]?", line
            )
            if answer:
                if answers:
                    problems.append("出现多个答案标记")
                answers = tuple(dict.fromkeys(re.findall(r"[A-H]", answer[1].upper())))
                ended = True
                continue
            if ended:
                if not re.match(r"^(?:解析|答案解析|说明)\s*[:：]", line):
                    if "答案后有附加内容" not in problems:
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
        if not options or not set(answers).issubset(options) or any(
            not value.strip() for value in options.values()
        ):
            problems.append("答案与选项不匹配或选项为空")
        if not any(stem):
            problems.append("题干为空")
        pages = tuple(sorted({page for page, _ in current}))
        if problems:
            bank.issues.append(
                f"{source} 第 {number} 题（页 {','.join(map(str, pages))}）：{'；'.join(problems)}"
            )
            current = []
            return
        values = {normalized(value) for value in options.values()}
        kind = section_kind or (
            "判断" if values in ({"正确", "错误"}, {"对", "错"})
            else "多选" if len(answers) > 1 else "单选"
        )
        bank.questions.append(
            Question(number, kind, "".join(stem), options, answers, pages, source)
        )
        current = []

    for page, raw in lines:
        line = raw.strip()
        if not line or TITLE.fullmatch(line):
            continue
        section = re.fullmatch(
            r"(?:[一二三四五六七八九十\d]+[、．.]\s*)?((?:单项|多项|单|多)选|判断)题", line
        )
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
        bank.issues.append(f"{source}：未发现题目")
    return bank


def load_pdf(path: Path) -> Bank:
    import pdfplumber

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
            page.flush_cache()
    bank = parse_lines(lines, count, SOURCE_LABEL)
    bank.sources = [SOURCE_LABEL]
    # De-duplicate identical stem+options; conflicting answers stay reported.
    unique = []
    seen = {}
    for question in bank.questions:
        key = question_key(question)
        answer = frozenset(question.options[letter] for letter in question.answers)
        if key in seen:
            old_answer, old = seen[key]
            if old_answer != answer:
                bank.issues.append(
                    f"{SOURCE_LABEL} 第 {question.number} 题与第 {old.number} 题答案冲突；已保留第 {old.number} 题"
                )
            else:
                bank.duplicates += 1
            continue
        seen[key] = answer, question
        unique.append(question)
    bank.questions = unique
    return bank


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, nargs="?", default=ROOT / "题库" / "2026考试复习资料.pdf")
    parser.add_argument("--output", type=Path, default=ROOT / "题库" / "default-bank.json")
    args = parser.parse_args()
    pdf = args.pdf.resolve()
    if not pdf.is_file():
        parser.error(f"PDF 不存在：{pdf}")
    bank = load_pdf(pdf)
    if not bank.questions:
        parser.error("未解析出有效题目：" + "；".join(bank.issues[:10]))
    save_bank(bank, args.output)
    manifest = {
        "version": 1,
        "pdf": pdf.name,
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "cache_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "questions": len(bank.questions),
        "pages": bank.page_count,
        "duplicates": bank.duplicates,
        "issues": len(bank.issues),
        "source_label": SOURCE_LABEL,
    }
    (args.output.parent / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    for issue in bank.issues[:20]:
        print("ISSUE", issue, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
