"""Collect one question across overlapping scroll frames, without guessing text."""
from dataclasses import dataclass, replace
from collections import Counter
import re

from .bank import normalized
from .matching import Match, clean_stem, screen_parts


def complete_match(match):
    if match.status != 'matched' or match.question is None or not match.options:
        return False
    return (len(match.options) == len(match.question.options)
            and sorted(map(normalized, match.options.values()))
            == sorted(map(normalized, match.question.options.values())))


def join_fragment(first, second):
    """Use only observed characters. Disjoint/conflicting fragments cannot merge."""
    a, b = normalized(first), normalized(second)
    if not b or b in a:
        return first
    if not a or a in b:
        return second
    for length in range(min(len(a), len(b)), 5, -1):
        if a.endswith(b[:length]):
            return a + b[length:]
    return None


class QuestionFragments:
    def __init__(self, index):
        self.index = index
        self.stem = ''
        self.options = {}
        self.conflict = False
        self.question_number = None

    @property
    def text(self):
        return self.stem + '\n' + '\n'.join(
            f'{label}. {value}' for label, value in sorted(self.options.items()))

    def add(self, text, question=None):
        leading, options = screen_parts(text)
        leading = clean_stem(leading).strip()
        current_stem = normalized(leading)
        identified = (question is not None and current_stem == normalized(question.stem)
                      and bool(options) and Counter(map(normalized, options.values()))
                      <= Counter(map(normalized, question.options.values())))
        switched = bool(identified and self.question_number is not None
                        and question.number != self.question_number)
        # A newly visible, complete different stem means a question switch.
        if (self.stem and current_stem in self.index.stems
                and current_stem != normalized(self.stem)) or switched:
            switched = True
            self.stem, self.options, self.conflict = '', {}, False
            self.question_number = None
        if identified:
            self.question_number = question.number
        if not self.options:
            joined = join_fragment(self.stem, leading)
            if joined is not None:
                self.stem = joined
            elif leading:
                self.conflict = True
        elif leading:
            stem = normalized(self.stem)
            if current_stem != stem and current_stem not in stem:
                # Unlabelled text before C/D is often the tail of B.
                preceding = [label for label in self.options if not options or label < min(options)]
                if preceding:
                    label = max(preceding)
                    joined = join_fragment(self.options[label], leading)
                    if joined is not None:
                        self.options[label] = joined
                    else:
                        self.conflict = True
                else:
                    self.conflict = True
        known={normalized(option) for q in self.index.questions
               if normalized(q.stem)==normalized(self.stem) for option in q.options.values()}
        for label, value in options.items():
            old=self.options.get(label,'')
            old_key,new_key=normalized(old),normalized(value)
            tail=old_key[len(new_key):] if old_key.startswith(new_key) else ''
            duplicate_tail=(len(tail)>=6 and any(normalized(other).startswith(tail)
                            or tail.startswith(normalized(other)[:6])
                            for key,other in options.items() if key!=label and len(normalized(other))>=6))
            # A later full reading can remove the clipped start of the NEXT
            # option accidentally attached to this label in an earlier frame.
            if new_key in known and old_key not in known and duplicate_tail:
                joined=value
            else:
                joined = join_fragment(old, value)
            if joined is None:
                self.conflict = True
            else:
                self.options[label] = joined
        return switched

    def lookup(self):
        result = self.index.lookup(self.text)
        if self.conflict and result.status == 'matched':
            return Match('unverified', '跨屏文字有冲突，无法确认当前网页选项顺序。', result.question)
        return result


@dataclass(frozen=True)
class ScrollStep:
    text: str
    match: Match
    direction: int = 0  # +1 up, -1 down; zero means no more input.


class ScrollReader:
    """Bounded top-to-bottom scan; UI owns all state and issues each wheel step."""
    def __init__(self, index, max_steps=28):
        self.index = index
        self.max_steps = max_steps
        self.steps = 0
        self.phase = 'idle'
        self.fragments = QuestionFragments(index)
        self.last_key = None
        self.unchanged = 0
        self.best = None
        self.last_text = ''

    @staticmethod
    def needs_scan(text, match, index=None):
        if complete_match(match) or match.status in ('empty', 'ambiguous', 'unreadable'):
            return False
        _, options = screen_parts(text)
        exam_hint=re.search(r'请选择(?:一个|一项|所有|全部)|(?:单选|多选|判断)题',text)
        if match.question or exam_hint:
            return True
        if not options:
            return False
        if index is None:
            return True
        # A bare A/B/C in another window is not enough to authorize a scan.
        visible=[normalized(value) for value in options.values() if normalized(value)]
        return any(sum(value in [normalized(old) for old in q.options.values()]
                       for value in visible)>=2 for q in index.questions)

    def feed(self, text, match):
        self.last_text = text
        if match.question is not None:
            self.best = match
        if complete_match(match):
            self.phase = 'finished'
            return ScrollStep(text, match)
        leading, options = screen_parts(text)
        stem = normalized(clean_stem(leading))
        key = (stem, tuple((label, normalized(value)) for label, value in options.items()))
        self.unchanged = self.unchanged + 1 if key == self.last_key else 0
        self.last_key = key
        if self.phase == 'idle':
            if not self.needs_scan(text, match, self.index):
                self.phase = 'finished'
                return ScrollStep(text, match)
            # A known complete stem followed by A is already a useful top frame.
            self.phase = 'down' if stem in self.index.stems and 'A' in options else 'up'
        if self.phase == 'up':
            if self.unchanged >= 2:
                self.phase = 'down'
                self.unchanged = 0
                self.fragments = QuestionFragments(self.index)
                self.fragments.add(text, match.question)
        else:
            if self.fragments.add(text, match.question):
                self.steps = 0
                self.unchanged = 0
            merged = self.fragments.lookup()
            if complete_match(merged):
                self.phase = 'finished'
                return ScrollStep(self.fragments.text, replace(
                    merged, message='已读取滚动区域的完整题干与全部选项，答案按当前页面字母对应。'))
            if merged.question is not None:
                self.best = merged
            if self.unchanged >= 2:
                return self.finish('已到达滚动区域底部，仍未完整核对')
        if self.steps >= self.max_steps:
            return self.finish('已达到本题滚动读取上限，仍未完整核对')
        self.steps += 1
        return ScrollStep(text, Match('scanning', '正在滚动读取完整题干与选项，核对完成后显示网页答案。'),
                          1 if self.phase == 'up' else -1)

    def finish(self, reason):
        self.phase = 'finished'
        merged = self.fragments.lookup() if self.fragments.stem else None
        best = merged if merged and merged.question else self.best
        text = self.fragments.text if self.fragments.stem else self.last_text
        if best and best.question:
            # Do not silently upgrade a partly read card to a verified letter.
            question = best.question
            status = 'candidate' if best.status == 'candidate' else 'reference'
            return ScrollStep(text, Match(
                status, reason + '；以下按题库顺序显示参考答案，请按选项内容核对。',
                question, question.answers, question.options, best.score))
        return ScrollStep(text, Match('missing', reason + '；题库中未找到可靠答案，可用关键词搜题。'))
