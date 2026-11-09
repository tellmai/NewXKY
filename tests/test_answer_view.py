"""The answer pane only prints the question bank's own text and letters."""
from __future__ import annotations

from newxky.answer_view import NOTICE, banner, render
from newxky.models import Question


def question() -> Question:
    return Question(
        1, "单选",
        "下列哪一项属于依法行政的要求（）",
        {"A": "任意扩大权限", "B": "依照法定权限和程序履行职责"},
        ("B",), (1,),
    )


def test_render_lists_the_stem_and_every_option():
    body = render(question())
    assert "下列哪一项属于依法行政的要求" in body
    assert "A." in body and "任意扩大权限" in body
    assert "B." in body and "依照法定权限和程序履行职责" in body


def test_render_highlights_only_the_correct_option():
    body = render(question())
    rows = body.split("<div ")[1:]
    wrong = next(row for row in rows if "任意扩大权限" in row)
    correct = next(row for row in rows if "依照法定权限和程序履行职责" in row)
    assert "#eaf7f1" in correct
    assert "#eaf7f1" not in wrong


def test_render_escapes_question_text():
    odd = Question(2, "判断", "a < b 吗（）", {"A": "对", "B": "错"}, ("A",), (1,))
    body = render(odd)
    assert "a &lt; b" in body
    assert "<b>B.</b>" in body


def test_banner_always_carries_the_notice():
    assert NOTICE in banner("matched")
    assert NOTICE in banner("incomplete")
    assert "相似题" in banner("candidate")
    assert "相似题" in banner("unverified")
    assert "相似题" not in banner("reference")
