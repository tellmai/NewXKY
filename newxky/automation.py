"""Deterministic automatic-answer state machine, independent of desktop input."""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .bank import normalized
from .exam_view import DialogView, ExamView
from .matching import clean_stem


@dataclass(frozen=True)
class Resolution:
    question: object | None
    method: str = ""
    reason: str = ""


def _compatible_fragment(observed, expected):
    """Allow a clipped/partially recognised stem, but preserve semantic tokens."""
    if observed == expected:
        return True
    if len(observed) < 10:
        return False
    numbers = lambda value:re.findall(r"-?\d+(?:\.\d+)?[%％]?",value)
    if numbers(observed) != numbers(expected):
        return False
    matcher = SequenceMatcher(None, observed, expected, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    substantial = [b for b in matcher.get_matching_blocks() if b.size >= 4]
    if matched / len(observed) < .88 or matched / len(expected) < .4:
        return False
    if sum(b.size for b in substantial) < 10:
        return False
    for tag,a,b,c,d in matcher.get_opcodes():
        if tag == "equal":
            continue
        # A dropped “不”, a changed year or a decimal is not a harmless typo.
        if re.search(r"不|未|无|非|禁止|严禁|不得|应当|必须|可以|仅|只|全部|所有|至少|至多|\d|[%％]",observed[a:b]+expected[c:d]):
            return False
    return True


class AutoResolver:
    def __init__(self, index):
        self.index = index
        self._queries = {}

    def resolve(self, stem, options) -> Resolution:
        key = normalized(clean_stem(stem))
        if not key:
            return Resolution(None,reason="没有识别到可用题干")
        exact = [q for q,s in zip(self.index.questions,self.index.stems) if s == key]
        candidates = exact
        method = "完整题干"
        if not exact:
            method = "关键词检索"
            # Search several independent fragments. One misread character must
            # not make a large AND query discard the otherwise correct question.
            terms = {key[i:i+6] for i in range(0,max(1,len(key)-5),3)}
            terms |= {key[-6:]}
            found = {}
            for term in terms:
                if len(term) < 4:
                    continue
                if term not in self._queries:
                    self._queries[term] = self.index.search(term)
                for q in self._queries[term]:
                    found[id(q)] = q
            candidates = [q for q in found.values() if _compatible_fragment(key,normalized(q.stem))]
        values = [normalized(v) for v in options.values() if normalized(v)]
        verified = []
        for q in candidates:
            bank = {normalized(v) for v in q.options.values()}
            # Full, recognised options distinguish same-stem variants. Partial
            # option text is accumulated during scrolling, not guessed here.
            if values and all(value in bank for value in values):
                verified.append(q)
        if len(verified) == 1 and (exact or len(set(values)) >= 2):
            return Resolution(verified[0],method)
        if len(candidates) == 1 and exact and not values:
            return Resolution(candidates[0],method)
        if len(verified) > 1:
            return Resolution(None,method,"关键词和选项仍对应多道题，已跳过")
        if candidates:
            return Resolution(None,method,"题库候选与已识别选项无法完整核对")
        return Resolution(None,method,"题库关键词检索未找到可靠答案")


@dataclass(frozen=True)
class Action:
    kind: str = "wait"
    point: tuple[float,float] | None = None
    amount: int = 0
    message: str = ""
    delay: int = 180
    target: str = ""
    selected: bool | None = None


@dataclass
class QuestionRecord:
    number: int
    stem: str
    completed: bool
    reason: str
    answers: tuple[str,...] = ()


def view_key(view):
    return (view.number,normalized(view.stem),
            tuple((o.letter,normalized(o.text)) for o in view.options))


def same_question(view,previous,question=None):
    """Compare meaning, tolerating OCR/letter changes caused by selection."""
    if previous is None:
        return None
    if view.number is not None and previous.number is not None and view.number!=previous.number:
        return False
    current = normalized(clean_stem(view.stem))
    expected = normalized(clean_stem(previous.stem))
    if current and expected:
        stem_same = current==expected or _compatible_fragment(current,expected) or _compatible_fragment(expected,current)
        if not stem_same and len(current)>=10:
            return False
    else:
        stem_same = False
    old = {o.letter:normalized(o.text) for o in previous.options if o.text}
    if question:
        values = {normalized(v)for v in question.options.values()}
    else:
        values = set(old.values())
    agreeing = 0
    for option in view.options:
        value = normalized(option.text)
        if not value:
            continue
        expected_value = old.get(option.letter)
        compatible = lambda other:value==other or (len(value)>=10 and _compatible_fragment(value,other)) or value in other and len(value)>=4
        if expected_value and compatible(expected_value):
            agreeing+=1
        elif option.complete and not any(compatible(other)for other in values):
            return False
        elif expected_value and value in values and value!=expected_value:
            return False
    return True if stem_same or agreeing>=2 else None


class AutoSession:
    """One active session; every input requires a fresh observed frame.

    The caller supplies monotonic time and serialises capture/inference/input.
    There is deliberately no default answer and no top-similarity selection.
    """
    def __init__(self,index):
        self.resolver = AutoResolver(index)
        self.state = "current"
        self.records = []
        self.ordinal = 1
        self.stem = ""
        self.options = {}
        self.question = None
        self.method = ""
        self.message = "从当前题开始自动答题"
        self.done = False
        self.submitted = False
        self.reason = ""
        self.before = None
        self.before_view = None
        self.last_view = None
        self.verified_mapping = None
        self.coverage_confirmed = False
        self.resume_from = None
        self.resume_state = None
        self.deadline = 0
        self.retry_count = 0
        self.pending = None
        self.started_page = None
        self.scrolls = 0
        self.scroll_key = None
        self.scroll_unchanged = 0
        self.direction = -1
        self.rewind_count = 0
        self.submit_limit = None
        self.receipt_limit = None
        self.confirm_clicked = False
        self.confirm_deadline = None
        self.wait_until = 0
        self.checked = False
        self._check_clicked = False

    @property
    def needs_window(self):
        return self.state in {"after_check","submit","receipt","wait_submit","close_check","close_wait"}

    @property
    def incomplete(self):
        return [r for r in self.records if not r.completed]

    def stop(self,reason):
        self.done = True
        self.reason = self.message = reason
        return Action("stop",message=reason)

    def resume(self,now):
        if self.submitted:
            raise ValueError("答卷已提交，不能继续")
        if self.state in {"receipt","wait_submit","close_wait","after_check","close_check","submit"}:
            # An unknown receipt is never permission to issue a second submit.
            if self.state=="receipt":
                self.receipt_limit=now+60
                self.confirm_deadline=now+5
        else:
            self.resume_state=self.state
            self.resume_from=self.last_view
            self.state="resuming"
        self.done=False
        self.reason=""
        self.message="正在从当前题继续"

    def _save_record(self,record):
        self.records=[r for r in self.records if r.number!=record.number]
        self.records.append(record)
        self.records.sort(key=lambda r:r.number)

    def _click(self,control,message):
        return Action("click",control.box.center,message=message,target=control.name)

    def _scroll(self,view,amount,message):
        # Keep the pointer in the scrollable question, above its fixed footer.
        return Action("scroll",(view.width*.62,max(20,view.footer_top*.58)),amount,message,target="question")

    def _move(self,view,name,state,now):
        control = view.controls.get(name)
        if control is None or control.enabled is not True:
            return self.stop(f"无法可靠定位可用的{name == 'previous' and '上一题' or '下一题'}按钮")
        self.before = view_key(view)
        self.before_view = view
        self.state = state
        self.pending = name
        self.deadline = now+5
        self.retry_count = 0
        return self._click(control,"正在返回上一题" if name=="previous" else "正在进入下一题")

    def _new_page(self,now):
        self.state = "top"
        self.stem = ""
        self.options = {}
        self.question = None
        self.verified_mapping = None
        self.method = ""
        self.started_page = now
        self.scrolls = self.scroll_unchanged = 0
        self.scroll_key = None
        self.direction = -1

    def _record(self,view,now,completed,reason):
        self._save_record(QuestionRecord(self.ordinal,self.stem or view.stem,completed,reason,
                            tuple(self.question.options[k] for k in self.question.answers) if completed else ()))
        if view.last:
            if self.incomplete:
                numbers = "、".join(str(r.number) for r in self.incomplete)
                return self.stop(f"已到最后一题；第 {numbers} 题未完成，未提交答卷")
            if not self.records or any(not r.completed for r in self.records):
                return self.stop("整卷完成状态无法确认，未提交答卷")
            if view.answered is not None and view.total is not None and view.answered==view.total:
                self.coverage_confirmed=True
            self.submit_limit = now+600
            if view.controls["finish"].enabled is not True:
                return self.stop("完成检查按钮状态无法确认，未提交答卷")
            self.state = "after_check"
            self.deadline = now+8
            self._check_clicked = True
            return self._click(view.controls["finish"],"全部题目已核验，正在完成检查")
        return self._move(view,"next","await_next",now)

    def _merge(self,view):
        if not self.stem and normalized(view.stem):
            self.stem = view.stem
        for option in view.options:
            old = self.options.get(option.letter)
            value = normalized(option.text)
            if old is None:
                self.options[option.letter] = {"text":option.text,"selected":option.selected,
                                              "complete":option.complete,"confidence":option.confidence,
                                              "starts":option.starts,"ends":option.ends}
            else:
                previous = normalized(old["text"])
                if self.verified_mapping is not None and old["complete"]:
                    compatible = value==previous or value in previous and len(value)>=4 or _compatible_fragment(value,previous)
                    old["selected"] = option.selected if compatible else None
                    continue
                if value and (previous in value or (option.complete and not old["complete"])):
                    old.update(text=option.text,complete=option.complete,confidence=option.confidence,
                               starts=old["starts"] or option.starts,ends=old["ends"] or option.ends)
                elif value and value not in previous:
                    # Merge overlapping wrapped fragments only. The final bank
                    # comparison must still be exact before this can be clicked.
                    merged = None
                    for a,b in ((previous,value),(value,previous)):
                        for overlap in range(min(len(a),len(b)),2,-1):
                            if a.endswith(b[:overlap]):
                                merged = a+b[overlap:]
                                break
                        if merged:
                            break
                    if merged:
                        old.update(text=merged,confidence=min(old["confidence"],option.confidence),
                                   starts=old["starts"] or option.starts,ends=old["ends"] or option.ends)
                    elif option.complete:
                        old.update(text=option.text,complete=True,confidence=option.confidence,
                                   starts=option.starts,ends=option.ends)
                elif value:
                    old["starts"] |= option.starts
                    old["ends"] |= option.ends
                old["complete"] = old["complete"] or (old["starts"] and old["ends"])
                old["selected"] = option.selected

    def _mapping(self):
        if self.question is None:
            return None
        bank = [normalized(v) for v in self.question.options.values()]
        observed = [normalized(v["text"]) for v in self.options.values()]
        if (len(bank) != len(observed) or len(set(bank)) != len(bank)
                or set(bank) != set(observed) or len(set(observed)) != len(observed)):
            return None
        if any(not o["complete"] or o["confidence"] < .75 for o in self.options.values()):
            return None
        correct = {normalized(self.question.options[k]) for k in self.question.answers}
        return {letter:normalized(o["text"]) in correct for letter,o in self.options.items()}

    def _scan(self,view,now):
        self._merge(view)
        values = {k:v["text"] for k,v in self.options.items() if v["complete"]}
        result = self.resolver.resolve(self.stem,values) if self.verified_mapping is None else Resolution(self.question,self.method)
        self.question, self.method = result.question,result.method
        mapping = self._mapping()
        if mapping is not None:
            self.verified_mapping = dict(mapping)
            for option in view.options:
                stored = self.options[option.letter]
                if (not normalized(option.text) or normalized(option.text) not in normalized(stored["text"])
                        or option.selected is None or option.confidence < .75):
                    continue
                desired = mapping[option.letter]
                if option.selected != desired:
                    # Only multi-select questions can require explicit clearing;
                    # single-choice clicks must not accidentally toggle off.
                    if not desired and len(self.question.answers) == 1 and "多" not in self.question.kind:
                        continue
                    self.pending = (option.letter,desired)
                    self.deadline = now+5
                    self.retry_count = 0
                    self.state = "verify"
                    self.before = view_key(view)
                    self.before_view = view
                    self.direction = -1
                    self.scroll_unchanged = 0
                    self.scroll_key = None
                    # A radio click can deselect a hidden option. Force readback
                    # of every option after input rather than trusting old state.
                    for item in self.options.values():
                        item["selected"] = None
                    return Action("click",option.box.center,message=f"第 {self.ordinal} 题：{'选择' if desired else '取消'} {option.letter}",target="option:"+option.letter,selected=desired)
            if all(o["selected"] is not None and o["selected"] == mapping[k] for k,o in self.options.items()):
                return self._record(view,now,True,self.method+"；所选答案已核验")
        if now-self.started_page >= 30 or self.scrolls >= 12:
            reason = result.reason or "选项内容、位置或选中状态无法核验"
            return self._record(view,now,False,reason)
        current = view_key(view)
        self.scroll_unchanged = self.scroll_unchanged+1 if current == self.scroll_key else 0
        self.scroll_key = current
        if self.scroll_unchanged >= 2:
            if self.direction == -1:
                self.direction = 1
                self.scroll_unchanged = 0
            elif mapping is not None and any(o["selected"] is None for o in self.options.values()):
                self.direction = -1
                self.scroll_unchanged = 0
            else:
                return self._record(view,now,False,result.reason or "滚动后仍不能完整核对全部选项及选择状态")
        self.scrolls += 1
        return self._scroll(view, -360 if self.direction == -1 else 360,
                            f"第 {self.ordinal} 题：{result.method or '识别题目'}，正在查找完整选项")

    def advance(self,view: ExamView,now: float,dialog: DialogView | None = None) -> Action:
        if self.done:
            return Action("stop",message=self.reason)
        self.last_view = view
        if self.state=="resuming":
            same = same_question(view,self.resume_from,self.question)
            if view.number is not None:
                if view.number!=self.ordinal:
                    if not any(r.number==self.ordinal for r in self.records):
                        self._save_record(QuestionRecord(self.ordinal,self.stem,False,"暂停后已切换题目，本题尚未核验"))
                    self.coverage_confirmed=False
                self.ordinal=view.number
            elif same is False:
                if not any(r.number==self.ordinal for r in self.records):
                    self._save_record(QuestionRecord(self.ordinal,self.stem,False,"暂停后已切换题目，本题尚未核验"))
                self.ordinal+=1
                self.coverage_confirmed=False
            self._new_page(now)
        if self.state=="current":
            self.ordinal=view.number or 1
            previous=view.controls.get("previous")
            self.coverage_confirmed=view.number==1 or bool(previous and previous.enabled is False)
            self._new_page(now)
        if self.state in {"await_rewind","await_next"}:
            if same_question(view,self.before_view,self.question) is False and normalized(view.stem):
                if self.state == "await_rewind":
                    self.rewind_count += 1
                    if self.rewind_count > 1000:
                        return self.stop("返回第一题次数异常，请检查框选范围")
                    self.state = "rewind"
                else:
                    self.ordinal = view.number or self.ordinal+1
                    self._new_page(now)
            elif now < self.deadline:
                return Action(message="正在确认翻页结果")
            elif (self.retry_count == 0 and view_key(view) == self.before
                  and view.number is not None):
                control = view.controls.get(self.pending)
                if control is None or control.enabled is not True:
                    return self.stop("翻页按钮状态无法确认，已停止")
                self.retry_count = 1
                self.deadline = now+5
                return self._click(control,"翻页未生效，重试一次")
            else:
                return self.stop("无法确认是否翻页成功，已停止；未提交答卷")
        if self.state == "rewind":
            previous = view.controls.get("previous")
            if previous is None or previous.enabled is None:
                return self.stop("未找到可靠的上一题按钮；请框入题干、选项和底部按钮")
            if previous.enabled:
                return self._move(view,"previous","await_rewind",now)
            if view.number not in (None,1):
                return self.stop("上一题已禁用，但当前题号不是第一题")
            self._new_page(now)
        if self.state == "top":
            # Arrival normally resets the inner scroller. Only scroll upwards
            # when its first option/stem is actually absent.
            if normalized(view.stem) and (view.source=="dom" or any(o.letter == "A" for o in view.options)):
                self.state = "scan"
            else:
                current = view_key(view)
                self.scroll_unchanged = self.scroll_unchanged+1 if current == self.scroll_key else 0
                self.scroll_key = current
                if self.scroll_unchanged >= 2 or self.scrolls >= 12 or now-self.started_page >= 30:
                    self.state = "scan"
                else:
                    self.scrolls += 1
                    return self._scroll(view,720,"正在滚回题干顶部")
        if self.state == "verify":
            if same_question(view,self.before_view,self.question) is False:
                return self.stop("选择答案后题目内容发生变化，已停止")
            letter,desired = self.pending
            option = next((o for o in view.options if o.letter == letter),None)
            if option and option.selected == desired:
                self.state = "scan"
            elif now < self.deadline:
                return Action(message=f"正在核验 {letter} 的选中状态")
            elif option and option.selected is not None and self.retry_count == 0:
                self.retry_count = 1
                self.deadline = now+5
                return Action("click",option.box.center,message=f"{letter} 尚未生效，重试一次",target="option:"+letter,selected=desired)
            else:
                return self._record(view,now,False,"点击后的选中状态无法确认")
        if self.state == "scan":
            return self._scan(view,now)
        return self._submission(view,now,dialog or DialogView("unknown"))

    def _submission(self,view,now,dialog):
        if self.incomplete or not self.records:
            return self.stop("仍有未完成题目，未提交答卷")
        if dialog.kind == "incomplete":
            return self.stop("网页检查提示有未完成题目，未提交答卷")
        if dialog.kind == "blocked":
            return self.stop("发现无法确认用途的弹窗，已停止；未继续交卷")
        if view.total is not None and view.answered is not None and view.answered != view.total:
            return self.stop("网页已答进度与完成记录不一致，未提交答卷")
        if view.total is not None and view.answered==view.total:
            self.coverage_confirmed=True
        if dialog.kind == "success" and self.state == "receipt":
            self.submitted = True
            return self.stop(f"{len(self.records)} 题已完成，答卷提交成功")
        if self.state == "after_check":
            if dialog.kind == "checked" and dialog.control and dialog.control.enabled is True:
                self.checked = True
                self.coverage_confirmed=True
                self.state = "close_check"
                self.deadline = now+5
                return self._click(dialog.control,"检查完成，关闭提示")
            if dialog.kind == "checked":
                if now >= self.deadline:
                    return self.stop("检查提示的确认按钮无法可靠定位，未提交答卷")
                return Action(message="正在定位完成检查的确认按钮")
            if dialog.kind == "confirm":
                # Some sites combine “完成检查” and the final confirmation.
                if not self.coverage_confirmed:
                    return self.stop("前面题目的完成状态无法确认，请人工核对后交卷")
                self.state = "receipt"
                self.receipt_limit = now+60
                self.confirm_clicked = True
                self.confirm_deadline = now+5
                if dialog.control and dialog.control.enabled is True:
                    return self._click(dialog.control,"全部题目已完成，确认交卷")
                return self.stop("交卷确认按钮无法可靠定位，已停止")
            if view.last and "submit" in view.controls:
                self.state = "submit"
            elif now >= self.deadline:
                return self.stop("完成检查的结果无法确认，未提交答卷")
            else:
                return Action(message="正在等待完成检查结果")
        if self.state == "close_check":
            if dialog.kind == "checked":
                if now >= self.deadline:
                    return self.stop("检查提示未关闭，已停止")
                return Action(message="等待检查提示关闭")
            self.state = "submit"
        if self.state == "receipt":
            if dialog.kind == "wait":
                self.wait_until = now+min(600,dialog.wait_seconds or 5)
                if dialog.control and dialog.control.enabled is True:
                    self.state = "close_wait"
                    self.deadline = now+5
                    return self._click(dialog.control,"尚未到交卷时间，关闭提示并等待")
                self.state = "wait_submit"
            elif dialog.kind == "confirm":
                if self.confirm_clicked:
                    if now >= self.confirm_deadline:
                        return self.stop("交卷确认后没有明确结果，已停止；不会重复提交")
                    return Action(message="正在等待交卷确认结果")
                if dialog.control is None or dialog.control.enabled is not True:
                    return self.stop("交卷确认按钮无法可靠定位，已停止")
                self.confirm_clicked = True
                self.confirm_deadline = now+5
                return self._click(dialog.control,"全部题目已完成，确认交卷")
            elif now >= self.receipt_limit:
                return self.stop("未收到明确的交卷成功回执，已停止；不会重复提交")
            else:
                return Action(message="等待交卷成功回执",delay=400)
        if self.state == "close_wait":
            if dialog.kind == "wait":
                if now >= self.deadline:
                    return self.stop("交卷时间提示未关闭，已停止")
                return Action(message="等待提示关闭")
            self.state = "wait_submit"
        if self.state == "wait_submit":
            if now >= self.submit_limit:
                return self.stop("等待交卷时间超过 10 分钟，已停止")
            if now < self.wait_until:
                return Action(message=f"尚未到交卷时间，等待 {max(1,round(self.wait_until-now))} 秒",delay=1000)
            if dialog.kind == "wait":
                return Action(message="等待交卷时间提示消失",delay=1000)
            self.state = "submit"
        if self.state == "submit":
            if not self.coverage_confirmed:
                return self.stop("从中途开始答题，尚未确认整卷全部完成；未提交答卷")
            control = view.controls.get("submit")
            if control and control.enabled is True:
                self.state = "receipt"
                self.receipt_limit = now+60
                self.confirm_clicked = False
                return self._click(control,"全部题目已核验，正在提交答卷")
            if now >= self.submit_limit:
                return self.stop("交卷按钮长时间不可用，未提交答卷")
            return Action(message="等待交卷按钮可用",delay=1000)
        return self.stop("自动答题状态异常，已停止")
