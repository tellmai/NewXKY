"""Match verified content and restore screen order from visible letter anchors."""
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache

from .bank import normalized
from .models import Question

NAVIGATION = re.compile(r"\n\s*(?:上一题|上题|下一题|提交试卷|提交答卷|完成检查|交卷|答题卡|标记此题|收藏本题)(?:\s|$)")


def _option_orders(text, values):
    """Find up to two complete content orders; ambiguous orders stay references."""
    if not all(values) or len(set(values)) != len(values):
        return ()

    @lru_cache(None)
    def cover(offset, used):
        if used == (1 << len(values)) - 1:
            return ((),) if offset == len(text) else ()
        orders = []
        for i, value in enumerate(values):
            if not used & (1 << i) and text.startswith(value, offset):
                for suffix in cover(offset + len(value), used | (1 << i)):
                    orders.append((i, *suffix))
                    if len(orders) == 2:
                        return tuple(orders)
        return tuple(orders)

    return cover(0, 0)


def _map_recovered_letters(question, order, leading_size, stem_size, options):
    """Use visible letters first, then corroborated consecutive-label positions."""
    values = list(question.options.values())
    ends, cursor = [], 0
    for index in order:
        cursor += len(normalized(values[index]))
        ends.append(cursor)
    visible, offsets = {}, set()
    position = leading_size - stem_size
    for label, value in options.items():
        index = next((i for i, end in enumerate(ends) if position < end), None)
        if index is None or position < 0 or index in visible:
            return None
        visible[index] = label
        offsets.add(ord(label) - ord("A") - index)
        position += len(normalized(value))
    correct = {normalized(question.options[label]) for label in question.answers}
    correct_indices = {i for i, bank_index in enumerate(order) if normalized(values[bank_index]) in correct}
    if len(visible) >= 2 and len(offsets) == 1:
        base = next(iter(offsets))
        if 0 <= base and base + len(order) <= 8:
            visible = {i: chr(ord("A") + base + i) for i in range(len(order))}
    if not correct_indices.issubset(visible):
        return None
    answers = tuple(sorted(visible[i] for i in correct_indices))
    mapped = {label: values[order[i]] for i, label in visible.items()}
    return answers, mapped


@dataclass(frozen=True)
class AnswerReference:
    answers: tuple[str, ...]
    options: dict[str, str]
    screen_order: bool = False


def _option_reference(question, options):
    """Suggest letters only when each complete option has a distinct close peer.

    Similarity is used for the labelled reference, never for a verified answer.
    Near-identical choices, duplicate contents and collisions keep bank order.
    """
    fallback = AnswerReference(question.answers, question.options)
    if len(options) != len(question.options) or len(options) < 2:
        return fallback
    bank = {label: normalized(value) for label, value in question.options.items()}
    visible = {label: normalized(value) for label, value in options.items()}
    if (not all(bank.values()) or not all(visible.values())
            or len(set(bank.values())) != len(bank) or len(set(visible.values())) != len(visible)):
        return fallback
    mapping = {}
    for label, value in visible.items():
        ranked = sorted(((SequenceMatcher(None, value, other, autojunk=False).ratio(), old)
                         for old, other in bank.items()), reverse=True)
        if ranked[0][0] < .9 or ranked[0][0] - ranked[1][0] < .1:
            return fallback
        mapping[label] = ranked[0][1]
    if len(set(mapping.values())) != len(bank):
        return fallback
    answers = tuple(sorted(label for label, old in mapping.items() if old in question.answers))
    return AnswerReference(answers, {label: question.options[old] for label, old in mapping.items()}, True)


@dataclass(frozen=True)
class Match:
    status: str
    message: str
    question: Question | None = None
    answers: tuple[str, ...] = ()
    options: dict[str, str] | None = None
    score: float = 0
    reference: AnswerReference | None = None


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
        value = NAVIGATION.split(value)[0]
        options[label] = value
    return text[:markers[0].start()], options


def clean_stem(text: str):
    # Exam cards put the type and a decorative question number above the stem.
    # A complete standalone tag can delimit the card even in a larger selection.
    # Tiny type badges may read e.g. "多造明·可多造 95". Their full
    # decorative pattern plus a card number distinguishes them from prose.
    tag = r"(?:单选|多选|判断)题(?:[ \t]*[·•.][ \t]*可多选)?[ \t]*(?:\d{1,4})?"
    small_tag = r"多\S{1,2}[ \t]*[·•.][ \t]*可多\S[ \t]+\d{1,4}"
    tags = list(re.finditer(r"^[ \t]*(?:" + tag + "|" + small_tag + r")[ \t]*$", text, re.M))
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
        self.search_fields = [(stem, *(normalized(value) for value in q.options.values()))
                              for stem, q in zip(self.stems, questions)]
        self.by_gram = defaultdict(set)
        for i, stem in enumerate(self.stems):
            for j in range(len(stem) - 1):
                self.by_gram[stem[j:j + 2]].add(i)

    def search(self, query: str) -> list[Question]:
        """Find all keywords in the stored stem or option contents."""
        terms = [value for word in query.split() if (value := normalized(word))]
        if not terms:
            return []
        matches = [i for i, fields in enumerate(self.search_fields)
                   if all(any(term in field for field in fields) for term in terms)]
        matches.sort(key=lambda i: -sum(term in self.stems[i] for term in terms))
        return [self.questions[i] for i in matches]

    def lookup(self, text: str) -> Match:
        if not self.questions:
            return Match("empty", "请先导入 PDF 题库")
        if not text.strip():
            return Match("unreadable", "未识别到文字，请检查区域是否包含完整题目")
        stem_text, options = screen_parts(text)
        stem = normalized(clean_stem(stem_text))
        whole = normalized(text)
        contained = [i for i, key in enumerate(self.stems) if key and key in whole]
        # Generic stems (e.g. "以下说法正确的是") can be a suffix of a longer
        # bank stem. Count separate occurrences, not nested stem substrings.
        spans = set()
        for key in {self.stems[i] for i in contained}:
            start = whole.find(key)
            while start >= 0:
                spans.add((start, start + len(key)))
                start = whole.find(key, start + 1)
        separate = [span for span in spans if not any(
            other != span and other[0] <= span[0] and span[1] <= other[1] for other in spans)]
        if len(separate) > 1:
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
        # Verify the full content even when badges are missing or interleaved
        # with wrapped lines. The stem must end at an actual OCR line boundary;
        # no extra prose, negation or changed number is discarded.
        leading = clean_stem(NAVIGATION.split(stem_text)[0])
        lines = leading.splitlines()
        prefixes = {normalized("\n".join(lines[:n])) for n in range(1, len(lines) + 1)}
        content = normalized(leading + "\n" + "\n".join(options.values()))
        recovered = {}
        for i in contained:
            if self.stems[i] in prefixes and content.startswith(self.stems[i]):
                orders = _option_orders(content[len(self.stems[i]):],
                                        tuple(normalized(value) for value in self.questions[i].options.values()))
                if orders:
                    recovered[i] = orders
        if recovered:
            exact = list(recovered)
        if exact:
            candidates = [self.questions[i] for i in exact]
            outcomes = {frozenset(normalized(q.options[a]) for a in q.answers) for q in candidates}
            if len(outcomes) != 1:
                return Match("ambiguous", "同一题干在题库中有不同答案；网页选项不完整，无法确定对应题目")
            q = candidates[0]
            if recovered and len(recovered[exact[0]]) == 1:
                mapped = _map_recovered_letters(q, recovered[exact[0]][0], len(normalized(leading)),
                                                len(self.stems[exact[0]]), options)
                if mapped:
                    answers, mapped_options = mapped
                    return Match("matched", "题干与全部选项内容已核对，答案字母已按当前画面顺序对应", q, answers, mapped_options, 1)
            if not recovered and len(options) < len(q.options):
                visible = {label: normalized(value) for label, value in options.items()}
                bank_values = {normalized(value) for value in q.options.values()}
                correct = {normalized(q.options[label]) for label in q.answers}
                if (len(set(visible.values())) == len(visible) and set(visible.values()).issubset(bank_values)
                        and correct.issubset(visible.values())):
                    answers = tuple(sorted(label for label, value in visible.items() if value in correct))
                    return Match("matched", "题干与正确选项内容已核对，答案字母已按当前画面对应", q, answers, options, 1)
            if not recovered and len(options) >= min(len(candidate.options) for candidate in candidates):
                reference = _option_reference(q, options)
                scope = "以下按相似内容推测网页顺序" if reference.screen_order else "以下按题库顺序显示答案"
                return Match("unverified", f"题干已匹配，但选项有漏字或差异；{scope}，仅供参考，请核对选项。",
                             q, reference=reference)
            message = ("题干与全部选项内容已核对；字母或换行未完整识别，以下字母和内容按题库顺序显示"
                       if recovered else "题干已匹配；网页选项未完整核对，以下字母和内容按题库顺序显示")
            return Match("reference", message, q, q.answers, q.options, 1)
        # Similar questions stay explicit references, not verified current answers.
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
            return Match("candidate", "未完全匹配：以下为相似题的题库答案，仅供参考；请核对题干差异。", self.questions[best], score=score)
        return Match("missing", "题库中未找到完整匹配，请检查题库和框选范围")
