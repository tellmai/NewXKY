from dataclasses import replace

import pytest

from newxky.automation import AutoResolver, AutoSession, QuestionRecord, _compatible_fragment
from newxky.desktop_input import pixel_to_logical
from newxky.exam_view import Control, DialogView, ExamView, Rect, VisibleOption
from newxky.matching import KnowledgeIndex
from newxky.models import Question


def question(number,stem="关于网络数据安全，下列说法正确的是（）",kind="单选"):
    return Question(number,kind,stem,{"A":"定期开展安全检查","B":"完全不需要安全检查",
                                    "C":"依法开展风险评估","D":"可以随意提供数据"},
                    ("A","C") if kind=="多选" else ("C",),(1,))


class FakeExam:
    """A local deterministic page adapter, including wrong pre-existing choices."""
    def __init__(self,questions,start=0,unknown=None):
        self.questions = questions
        self.index = start
        self.unknown = unknown
        self.selections = [set() for _ in questions]
        self.dialog = DialogView("unknown")
        self.events = []
        self.submitted = False
        self.last = len(questions)-1

    def view(self):
        q = self.questions[self.index]
        # Page order is intentionally different from bank order.
        values = [q.options[k] for k in "CADB"]
        options = tuple(VisibleOption(k,v,Rect(10,100+i*80,40,130+i*80),
                                      k in self.selections[self.index]) for i,(k,v) in enumerate(zip("ABCD",values)))
        controls = {"previous":Control("previous",Rect(400,700,480,735),self.index>0),
                    "submit":Control("submit",Rect(650,700,740,735),True)}
        name = "finish" if self.index==self.last else "next"
        controls[name] = Control(name,Rect(520,700,620,735),True)
        stem = "这道题完全不在题库中，内容没有任何对应资料" if self.unknown==self.index else q.stem
        return ExamView(stem,options,controls,800,760,680,number=self.index+1,total=len(self.questions))

    def execute(self,action):
        if action.kind != "click":
            return
        self.events.append((self.index,action.point,action.message))
        if self.dialog.kind == "checked":
            self.dialog = DialogView("unknown")
            return
        if self.dialog.kind == "confirm":
            self.dialog = DialogView("success")
            self.submitted = True
            return
        view = self.view()
        for name,c in view.controls.items():
            if c.box.contains(action.point):
                if name=="previous":
                    self.index -= 1
                elif name=="next":
                    self.index += 1
                elif name=="finish":
                    self.dialog = DialogView("checked",Control("ack",Rect(300,300,400,340),True))
                elif name=="submit":
                    self.dialog = DialogView("confirm",Control("confirm",Rect(300,400,430,440),True))
                return
        for o in view.options:
            if o.box.contains(action.point):
                selected = self.selections[self.index]
                if self.questions[self.index].kind=="多选":
                    selected.symmetric_difference_update({o.letter})
                else:
                    self.selections[self.index] = {o.letter}
                return
        raise AssertionError(action)

    def run(self,session):
        for i in range(300):
            action = session.advance(self.view(),i*.6,self.dialog)
            self.execute(action)
            if session.done:
                return
        raise AssertionError((session.state,session.message))


def test_starts_at_current_question_maps_shuffled_options_and_never_rewinds():
    questions = [question(1),question(2,"关于应急管理，下列说法正确的是（）","多选"),
                 question(3,"关于信息保护，下列说法正确的是（）")]
    exam = FakeExam(questions,start=1)
    exam.selections[0] = {"D"}  # Previously selected wrong answer.
    exam.selections[1] = {"A","D"}  # One correct, one wrong; do not toggle A off.
    session = AutoSession(KnowledgeIndex(questions))
    exam.run(session)
    assert session.submitted and exam.submitted
    assert [r.number for r in session.records]==[2,3] and all(r.completed for r in session.records)
    assert exam.selections == [{"D"},{"A","B"},{"A"}]
    assert not any("上一题"in message for _,_,message in exam.events)
    multi_a = Rect(10,100,40,130).center
    assert not any(i==1 and point==multi_a for i,point,_ in exam.events)
    assert "提交成功" in session.reason


@pytest.mark.parametrize("missing",[0,1,2])
def test_unknown_question_is_skipped_until_last_and_never_submitted(missing):
    questions = [question(i+1,f"根据不同领域管理要求第{i+1}种情况应当如何处理（）") for i in range(3)]
    exam = FakeExam(questions,unknown=missing)
    session = AutoSession(KnowledgeIndex(questions))
    exam.run(session)
    assert exam.index==2
    assert not session.submitted and not exam.submitted
    assert len(session.records)==3 and len(session.incomplete)==1
    assert session.incomplete[0].number==missing+1
    assert not any("提交" in message or "完成检查" in message for _,_,message in exam.events)


def test_keyword_search_recovers_incomplete_stem_and_verifies_options():
    q = question(1,"根据本市自然灾害防治条例，受到自然灾害威胁的人员适用本条例（）","多选")
    result = AutoResolver(KnowledgeIndex([q])).resolve("受到自然灾害威胁的人员适用本条例",q.options)
    assert result.question==q and result.method=="关键词检索"


def test_keyword_search_uses_options_to_distinguish_candidates():
    first = question(1,"根据本市自然灾害防治条例，受到自然灾害威胁的人员适用本条例（）")
    second = replace(first,number=2,stem="根据本市自然灾害救助条例，受到自然灾害威胁的人员适用本条例（）",
                     options={"A":"选择甲内容","B":"选择乙内容","C":"选择丙内容","D":"选择丁内容"})
    resolver = AutoResolver(KnowledgeIndex([first,second]))
    assert resolver.resolve("受到自然灾害威胁的人员适用本条例",first.options).question==first
    ambiguous = AutoResolver(KnowledgeIndex([first,replace(second,options=first.options)]))
    assert ambiguous.resolve("受到自然灾害威胁的人员适用本条例",first.options).question is None


@pytest.mark.parametrize("observed,expected",[
    ("接待单位可以根据实际情况超标准接待","接待单位不可以根据实际情况超标准接待"),
    ("每年应当至少进行15次安全风险评估","每年应当至少进行1.5次安全风险评估"),
    ("每年应当至少进行20次安全风险评估","每年应当至少进行30次安全风险评估"),
])
def test_keyword_search_preserves_negations_and_numbers(observed,expected):
    assert not _compatible_fragment(observed,expected)


def test_keyword_search_does_not_choose_unique_result_without_option_evidence():
    q = question(1,"根据本市自然灾害防治条例，受到自然灾害威胁的人员适用本条例（）")
    result = AutoResolver(KnowledgeIndex([q])).resolve("受到自然灾害威胁的人员适用本条例",{})
    assert result.question is None


def test_last_question_marker_is_finish_not_ever_present_submit():
    exam = FakeExam([question(1),question(2)])
    assert "submit" in exam.view().controls and not exam.view().last
    exam.index=1
    assert exam.view().last


def test_ambiguous_identical_pages_are_not_double_advanced():
    exam = FakeExam([question(1),question(2)])
    session = AutoSession(KnowledgeIndex(exam.questions))
    view = replace(exam.view(),number=None,total=None)
    session._move(view,"next","await_next",0)
    action = session.advance(view,6)
    assert action.kind=="stop" and "翻页" in action.message


def test_selection_failure_marks_incomplete_and_next_still_runs():
    questions = [question(1),question(2,"国家机关应当如何履行保护职责（）")]
    exam = FakeExam(questions)
    session = AutoSession(KnowledgeIndex(questions))
    first = session.advance(exam.view(),0)
    assert first.kind=="click"
    # Drop both attempts at selecting an option.
    assert session.advance(exam.view(),6).kind=="click"
    following = session.advance(exam.view(),12)
    assert following.kind=="click" and "下一题" in following.message
    assert not session.records[0].completed


def test_page_change_during_selection_cancels_further_input():
    exam = FakeExam([question(1),question(2,"国家机关应当如何履行保护职责（）")])
    session = AutoSession(KnowledgeIndex(exam.questions))
    assert session.advance(exam.view(),0).kind=="click"
    exam.index=1
    assert session.advance(exam.view(),1).kind=="stop"


def submit_session():
    s = AutoSession(KnowledgeIndex([]))
    s.records=[QuestionRecord(1,"已核验题目",True,"")]
    s.state="submit"
    s.submit_limit=600
    s.coverage_confirmed=True
    return s


def test_submit_waits_for_disabled_button_and_stops_at_limit():
    exam = FakeExam([question(1)])
    view = exam.view()
    controls = dict(view.controls)
    controls["submit"] = replace(controls["submit"],enabled=False)
    view = replace(view,controls=controls)
    session=submit_session()
    assert session.advance(view,1).kind=="wait"
    assert session.advance(view,601).kind=="stop"


def test_no_success_receipt_does_not_repeat_submission():
    view = FakeExam([question(1)]).view()
    session=submit_session()
    assert session.advance(view,0).kind=="click"
    assert session.advance(view,20).kind=="wait"
    assert session.advance(view,61).kind=="stop"
    assert not session.submitted


def test_platform_missing_warning_blocks_submission():
    session=submit_session()
    action=session.advance(FakeExam([question(1)]).view(),0,DialogView("incomplete"))
    assert action.kind=="stop" and not session.submitted


def test_already_complete_check_can_open_submit_confirmation_directly():
    session=submit_session()
    session.state="after_check"
    session.deadline=10
    view=FakeExam([question(1)]).view()
    dialog=DialogView("confirm",Control("confirm",Rect(20,20,80,50),True))
    assert session.advance(view,0,dialog).kind=="click"
    assert session.advance(view,2,dialog).kind=="wait"
    assert session.advance(view,6,dialog).kind=="stop"


@pytest.mark.parametrize("ratio",[1,1.25,1.5,2])
@pytest.mark.parametrize("origin",[(0,0),(-1920,200),(3840,300)])
def test_native_click_mapping_uses_capture_origin_and_actual_ratio(ratio,origin):
    assert pixel_to_logical((150*ratio,90*ratio),origin,ratio)==(origin[0]+150,origin[1]+90)


def test_wrong_total_or_answered_count_blocks_submission():
    session=submit_session()
    view=replace(FakeExam([question(1)]).view(),total=2,answered=1)
    assert session.advance(view,0).kind=="stop"


def test_scrolling_collects_and_verifies_hidden_options_after_multiple_clicks():
    q=question(1,kind="多选")
    class ScrolledExam(FakeExam):
        def __init__(self):
            super().__init__([q])
            self.offset=0
            self.selections[0]={"D"}
        def view(self):
            full=super().view()
            return replace(full,stem=full.stem if not self.offset else "",
                           options=full.options[2:] if self.offset else full.options[:2])
        def execute(self,action):
            if action.kind=="scroll":
                self.offset=1 if action.amount<0 else 0
            else:
                super().execute(action)
    exam=ScrolledExam()
    session=AutoSession(KnowledgeIndex([q]))
    exam.run(session)
    assert session.submitted and exam.selections==[{"A","B"}]


def test_overlapping_parts_of_a_long_option_require_both_start_and_end_evidence():
    session=AutoSession(KnowledgeIndex([]))
    base=FakeExam([question(1)]).view()
    prefix=VisibleOption("A","自然灾害威胁的人员应当及时转移",Rect(10,100,40,130),False,False,.99,True,False)
    suffix=replace(prefix,text="人员应当及时转移到安全区域",starts=False,ends=True)
    session._merge(replace(base,options=(prefix,)))
    assert not session.options["A"]["complete"]
    session._merge(replace(base,options=(suffix,)))
    assert session.options["A"]["text"]=="自然灾害威胁的人员应当及时转移到安全区域"
    assert session.options["A"]["complete"]


def test_unknown_modal_blocks_submit_even_when_footer_is_visible_behind_it():
    session=submit_session()
    assert session.advance(FakeExam([question(1)]).view(),0,DialogView("blocked")).kind=="stop"


def test_resume_rechecks_selected_option_and_does_not_rewind_or_toggle_it_off():
    questions=[question(1),question(2,"国家机关履行数据保护职责应当如何处理（）")]
    exam=FakeExam(questions)
    session=AutoSession(KnowledgeIndex(questions))
    action=session.advance(exam.view(),0)
    exam.execute(action)
    session.stop("手动暂停")
    session.resume(1)
    action=session.advance(exam.view(),1)
    assert action.target=="next"
    assert exam.selections[0]=={"A"}
    assert len(session.records)==1 and session.records[0].completed


def test_missing_label_after_selection_is_not_a_new_question():
    exam=FakeExam([question(1),question(2,"国家机关履行数据保护职责应当如何处理（）")])
    session=AutoSession(KnowledgeIndex(exam.questions))
    action=session.advance(exam.view(),0)
    exam.execute(action)
    view=exam.view()
    # One unrelated option temporarily disappears from OCR after highlighting.
    changed=replace(view,options=view.options[:-1])
    action=session.advance(changed,1)
    assert not session.done and action.kind!="stop"
    action=session.advance(view,2)
    assert action.target=="next"


def test_resume_after_manual_navigation_preserves_an_unfinished_record():
    exam=FakeExam([question(1),question(2,"国家机关履行数据保护职责应当如何处理（）")])
    session=AutoSession(KnowledgeIndex(exam.questions))
    session.advance(exam.view(),0)
    session.stop("暂停")
    exam.index=1
    session.resume(1)
    session.advance(exam.view(),1)
    assert session.ordinal==2
    assert any(r.number==1 and not r.completed for r in session.records)
