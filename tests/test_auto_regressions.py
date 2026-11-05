from dataclasses import replace

import cv2
import pytest

from newxky.automation import AutoSession,same_question
from newxky.bank import normalized
from newxky.exam_view import parse_exam
from newxky.matching import KnowledgeIndex
from newxky.ocr import LocalOCR,OCRLayout
from test_automation import FakeExam,question
from test_exam_view import fixture,line


@pytest.mark.parametrize("number,tag", [(1,""),(2,"单选题"),(15,"模糊题型")])
def test_bare_card_number_is_metadata_not_a_stem_keyword(number,tag):
    pixels,layout = fixture()
    cv2.rectangle(pixels,(15,25),(980,125),(215,215,215),1)
    rows = [line(920,2,f"{number:02}",40,16),*layout.lines]
    if tag:
        rows.append(line(20,2,tag,80,16))
    view = parse_exam(OCRLayout("\n".join(r.text for r in rows),tuple(rows),1000,700),pixels)
    assert view.number == number
    assert normalized(view.stem) == normalized(layout.lines[0].text)


def test_a_real_numeric_stem_inside_the_card_is_preserved():
    pixels,layout = fixture()
    cv2.rectangle(pixels,(15,25),(980,125),(215,215,215),1)
    rows = (line(920,2,"15",40,16),line(160,35,"100",80,22),
            line(160,65,"元是本题规定的标准",600,22),*layout.lines[1:])
    view = parse_exam(OCRLayout("",rows,1000,700),pixels)
    assert view.number == 15 and normalized(view.stem).startswith("100元")


def test_unreadable_selected_a_cannot_push_its_content_into_stem():
    pixels,layout = fixture(selected=True)
    previous = parse_exam(layout,pixels)
    rows = (layout.lines[0],*layout.lines[2:])
    view = parse_exam(OCRLayout("",rows,1000,700),pixels)
    assert normalized(view.stem) == normalized(previous.stem)
    assert same_question(view,previous) is True


def test_first_bad_stem_can_be_replaced_by_a_later_complete_frame():
    exam = FakeExam([question(1),question(2,"国家机关应当如何履行保护职责（）")])
    session = AutoSession(KnowledgeIndex(exam.questions))
    assert session.advance(replace(exam.view(),stem="01\n"+exam.view().stem),0).kind == "scroll"
    action = session.advance(exam.view(),1)
    assert action.kind == "click" and action.target.startswith("option:")
    assert session.question == exam.questions[0]


def test_transient_selected_frame_requires_fresh_read_before_proceeding():
    exam = FakeExam([question(1),question(2,"国家机关应当如何履行保护职责（）")])
    session = AutoSession(KnowledgeIndex(exam.questions))
    exam.execute(session.advance(exam.view(),0))
    bad = replace(exam.view(),stem="01\n"+exam.view().stem)
    assert session.advance(bad,1).kind == "reread"
    assert not session.done
    assert session.advance(exam.view(),2).target == "next"


def test_persistent_changed_meaning_stops_without_additional_clicks():
    exam = FakeExam([question(1),question(2,"国家机关应当如何履行保护职责（）")])
    session = AutoSession(KnowledgeIndex(exam.questions))
    exam.execute(session.advance(exam.view(),0))
    changed = replace(exam.view(),stem=exam.view().stem.replace("正确","不正确"))
    assert session.advance(changed,1).kind == "reread"
    assert session.advance(changed,2).kind == "reread"
    assert session.advance(changed,3).kind == "stop" and not session.submitted


def test_forced_ocr_does_not_reuse_an_exact_cached_bad_frame():
    pixels,layout = fixture()
    content = cv2.imencode(".png",pixels)[1].tobytes()
    ocr = LocalOCR()
    ocr._engine = lambda image,use_det=True:[(r.box,r.text,r.confidence) for r in layout.lines] if use_det else [["A",.99]]
    ocr.recognize_layout(content)
    ocr.recognize_layout(content)
    assert ocr.stats["full"] == 1
    ocr.recognize_layout(content,force=True)
    assert ocr.stats["full"] == 2


def test_selected_long_option_can_be_read_back_while_stem_is_scrolled_out():
    exam = FakeExam([question(1)])
    session = AutoSession(KnowledgeIndex(exam.questions))
    session.state="scan"
    session.started_page=0
    session._merge(exam.view())
    partial=replace(exam.view(),stem="",options=exam.view().options[:1])
    action=session.advance(partial,0)
    assert action.target=="option:A"
    exam.execute(action)
    selected=replace(exam.view(),stem="",options=exam.view().options[:1])
    action=session.advance(selected,1)
    assert not session.done and action.kind=="scroll"
    assert session.options["A"]["selected"] is True
