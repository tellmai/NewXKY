"""Conservative content matching. Letters always come from the visible options."""
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from .bank import normalized
from .models import Question


@dataclass(frozen=True)
class Match:
    status: str
    message: str
    question: Question | None = None
    answers: tuple[str, ...] = ()
    options: dict[str, str] | None = None
    score: float = 0


def screen_parts(text: str):
    text = unicodedata.normalize("NFKC", text)
    # Labels can be a separate OCR row, or all options can be on one row.
    marker = re.compile(r"(?:^|\n|[ \t]+)[○◯〇●◎□☐☑✓√\s]*([A-H])(?:[.、:)]\s*|[ \t]+|(?=\n|$))", re.M)
    markers = list(marker.finditer(text))
    if not markers:
        return text, {}
    options = {}
    for i, item in enumerate(markers):
        label = item[1]
        if label in options:
            return text[:markers[0].start()], {}  # More than one question / duplicate labels.
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        value = text[item.end():end].strip()
        # Only discard standalone, recognisable navigation rows after an option.
        value = re.split(r"\n\s*(?:上一题|下一题|提交试卷|提交答卷|完成检查|交卷|答题卡|标记此题|收藏本题)(?:\s|$)", value)[0]
        options[label] = value
    return text[:markers[0].start()], options


def clean_stem(text: str):
    # Exam cards put the type and a decorative question number above the stem.
    # A complete standalone tag can delimit the card even in a larger selection.
    tags = list(re.finditer(r"^[ \t]*(?:单选|多选|判断)题(?:\s*[·•.]\s*可多选)?[ \t]*(?:\d{1,4})?[ \t]*$", text, re.M))
    if tags:
        text = text[tags[-1].end():]
        text = re.sub(r"^\s*\d{1,4}[ \t]*\n", "", text)
    for _ in range(4):
        text = re.sub(r"^\s*(?:第\s*\d+\s*题\s*[、.．:：]?|\d+\s*[、.．:：])\s*", "", text)
        text = re.sub(r"^\s*[【\[(（]?\s*(?:单项选择|多项选择|单选|多选|判断)题?\s*[】\])）:：.、]*\s*", "", text)
        text = re.sub(r"^\s*[(（]\s*\d+(?:\.\d+)?\s*分\s*[)）]\s*", "", text)
    text = re.sub(r"\s*[(（]\s*\d+(?:\.\d+)?\s*分\s*[)）]\s*$", "", text)
    return text


class KnowledgeIndex:
    def __init__(self, questions: list[Question]):
        self.questions = questions
        self.stems = [normalized(q.stem) for q in questions]
        self.by_gram = defaultdict(set)
        for i, stem in enumerate(self.stems):
            for j in range(len(stem) - 1):
                self.by_gram[stem[j:j + 2]].add(i)

    def lookup(self, text: str) -> Match:
        if not self.questions:
            return Match("empty", "请先导入 PDF 题库")
        if not text.strip():
            return Match("unreadable", "未识别到文字，请检查区域是否包含完整题目")
        stem_text, options = screen_parts(text)
        stem = normalized(clean_stem(stem_text))
        whole = normalized(text)
        contained = [i for i, key in enumerate(self.stems) if key and key in whole]
        # A second visible question must not be mistaken for the current question.
        distinct = {self.stems[i] for i in contained}
        if len(distinct) > 1:
            return Match("ambiguous", "区域中识别到多个题干，请只框选一道完整题目")
        # Equality prevents an extra leading negation from turning a different
        # question into a match, even if the original stem is a substring.
        exact = [i for i, key in enumerate(self.stems) if key and key == stem]
        resolved = []
        for i in exact:
            q = self.questions[i]
            visible = {k: normalized(v) for k, v in options.items()}
            bank_values = [normalized(v) for v in q.options.values()]
            if len(set(bank_values)) != len(bank_values):
                continue
            if len(visible) != len(bank_values) or sorted(visible.values()) != sorted(bank_values):
                continue
            correct = {normalized(q.options[a]) for a in q.answers}
            answers = tuple(sorted(k for k, v in visible.items() if v in correct))
            resolved.append((q, answers))
        if resolved:
            outcomes = {answers for _, answers in resolved}
            if len(outcomes) != 1:
                return Match("ambiguous", "题库存在不同答案，无法确定，请核对原文")
            q, answers = resolved[0]
            return Match("matched", "完整题干与选项已核对", q, answers, options, 1)
        if exact:
            candidates = [self.questions[i] for i in exact]
            outcomes = {frozenset(normalized(q.options[a]) for a in q.answers) for q in candidates}
            if len(outcomes) != 1:
                return Match("ambiguous", "同一题干在题库中有不同答案；网页选项不完整，无法确定对应题目")
            q = candidates[0]
            if len(options) >= min(len(candidate.options) for candidate in candidates):
                return Match("unverified", "网页选项已识别，但内容与题库不一致；请重新识别或核对选项，暂不提供字母答案", q)
            return Match("reference", "题干已匹配；网页选项未完整核对，以下字母和内容按题库顺序显示", q, q.answers, q.options, 1)
        # Fuzzy results are diagnostic candidates only: never yield an answer.
        counts = defaultdict(int)
        for gram in {stem[j:j + 2] for j in range(len(stem) - 1)}:
            for i in self.by_gram.get(gram, ()):
                counts[i] += 1
        candidates = sorted(counts, key=counts.get, reverse=True)[:12]
        best, score = None, 0.0
        for i in candidates:
            key = self.stems[i]
            value = SequenceMatcher(None, stem, key, autojunk=False).ratio()
            if value > score:
                best, score = i, value
        if best is not None and score >= .75:
            return Match("candidate", "发现相似题目，文字未完全一致，暂不显示答案；请调整浏览器缩放或重新框选", self.questions[best], score=score)
        return Match("missing", "题库中未找到完整匹配，请检查题库和框选范围")
