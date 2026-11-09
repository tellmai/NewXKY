"""Selecting an option restyles the exam card; the bank answer must stay put."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QPainter, QPixmap

from newxky.matching import Match
from newxky.models import Bank, Question
from newxky.monitor import same_text_signature, text_signature
from newxky.ui import MainWindow

FONT = Path("C:/Windows/Fonts/msyh.ttc")


class Manager:
    server_url = ""
    last_error = ""
    expired = False

    @property
    def can_use(self):
        return not self.expired

    def remaining_seconds(self):
        return 2399

    def reload_lease(self):
        pass

    def touch(self):
        pass

    def refresh(self):
        return 2399


def question(number: int = 1) -> Question:
    return Question(
        number, "单选",
        "下列哪一项属于依法行政的要求（）",
        {"A": "任意扩大权限", "B": "依照法定权限和程序履行职责"},
        ("B",), (1,),
    )


def card(*, selected: str | None = None, labels=("A", "B")):
    """Exam card whose badges sit in their own column, so a fill never reflows text."""
    font = ImageFont.truetype(str(FONT), 22)
    image = Image.new("RGB", (640, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.text((30, 20), "下列哪一项属于依法行政的要求（）", font=font, fill=(20, 20, 20))
    for index, letter in enumerate(labels):
        y = 80 + index * 66
        filled = letter == selected
        draw.ellipse((28, y, 64, y + 36),
                     fill=(11, 140, 120) if filled else "white", outline=(90, 90, 90))
        draw.text((38, y + 6), letter, font=font,
                  fill=(255, 255, 255) if filled else (30, 30, 30))
        draw.text((80, y + 6), f"{letter}. 选项{index + 1}", font=font, fill=(20, 20, 20))
    return np.asarray(image.convert("L"))


@pytest.mark.skipif(not FONT.exists(), reason="Windows Chinese font fixture")
def test_filled_badge_keeps_the_signature_but_a_new_letter_does_not():
    plain = text_signature(card())
    assert same_text_signature(plain, text_signature(card(selected="B")))
    assert same_text_signature(plain, text_signature(card(selected="A")))
    assert not same_text_signature(plain, text_signature(card(labels=("C", "B"))))


def build(tmp_path, monkeypatch, questions):
    monkeypatch.setattr(MainWindow, "warm_ocr", lambda self: None)
    monkeypatch.setattr(MainWindow, "start_license_refresh", lambda self: None)
    window = MainWindow(Manager(), Bank(questions), data_dir=tmp_path, app_dir=tmp_path)
    window.running = True
    return window


def show(window, text, match, revision_seed=b"frame"):
    window.tracker.observe(revision_seed, 0)
    revision = window.tracker.begin()
    window.recognized(revision, (text, match, .1))


def test_style_only_frame_change_keeps_the_bank_answer(tmp_path, monkeypatch):
    q = question()
    state = {"frame": 0, "time": 100.0}
    monkeypatch.setattr("newxky.ui.time.monotonic", lambda: state["time"])
    window = build(tmp_path, monkeypatch, [q])
    try:
        window.region = QRect(0, 0, 400, 300)
        text = (q.stem + "\nA. " + q.options["A"] + "\nB. " + q.options["B"])
        window.ocr.recognize = lambda content, **kwargs: text
        window.launch = lambda work, result, error: result(work(None))

        class Screen:
            def geometry(self):
                return QRect(0, 0, 800, 800)

            def grabWindow(self, *args):
                pixmap = QPixmap(400, 300)
                pixmap.fill(QColor("white"))
                if state["frame"]:
                    # Selecting B highlights its row: pixels change, text does not.
                    painter = QPainter(pixmap)
                    painter.fillRect(0, 60, 400, 40, QColor("#dff1ea"))
                    painter.end()
                return pixmap

        monkeypatch.setattr("newxky.ui.QGuiApplication.screenAt", lambda point: Screen())

        def tick():
            state["time"] += .6
            window.capture()

        tick()
        tick()
        body = window.answer_detail.toPlainText()
        assert q.stem in body
        state["frame"] = 1
        tick()
        assert window.answer_detail.toPlainText() == body
        assert "题库答案请注意实际考题顺序" in window.message.text()
    finally:
        window.close()


def test_weaker_reread_of_the_same_question_keeps_the_bank_answer(tmp_path, monkeypatch):
    q = question()
    window = build(tmp_path, monkeypatch, [q])
    try:
        text = (q.stem + "\nA. " + q.options["A"] + "\nB. " + q.options["B"])
        show(window, text, window.index.lookup(text))
        body = window.answer_detail.toPlainText()
        assert window.status.text() == "题库答案"

        degraded = Match(
            "reference", "题干与全部选项内容已核对；字母或换行未完整识别。",
            q, q.answers, q.options, 1,
        )
        show(window, text, degraded, b"after-click")
        assert window.answer_detail.toPlainText() == body
        assert window.status.text() == "题库答案"
        # No exam-page letters are ever printed, so nothing can be "wrong order".
        assert "B / " not in window.answer_detail.toPlainText()
    finally:
        window.close()


def test_different_question_replaces_the_answer_block(tmp_path, monkeypatch):
    first = question(1)
    second = Question(2, "单选", "关于重要数据目录，下列说法正确的是（）",
                      {"A": "正确内容", "B": "其他内容"}, ("A",), (3,))
    window = build(tmp_path, monkeypatch, [first, second])
    try:
        text = (first.stem + "\nA. " + first.options["A"] + "\nB. " + first.options["B"])
        show(window, text, window.index.lookup(text))
        assert first.stem in window.answer_detail.toPlainText()

        next_text = (second.stem + "\nA. " + second.options["A"]
                     + "\nB. " + second.options["B"])
        show(window, next_text, window.index.lookup(next_text), b"next-card")
        body = window.answer_detail.toPlainText()
        assert second.stem in body
        assert first.stem not in body
    finally:
        window.close()


def test_similar_question_is_marked_without_showing_letters(tmp_path, monkeypatch):
    q = question()
    window = build(tmp_path, monkeypatch, [q])
    try:
        match = Match("candidate", "未完全匹配：以下为相似题的题库答案，仅供参考。",
                      q, score=.82)
        show(window, q.stem, match)
        assert window.status.text() == "相似题"
        assert "相似题，请核对题干" in window.message.text()
        assert "题库答案请注意实际考题顺序" in window.message.text()
        assert "82%" in window.provenance.text()
        assert q.stem in window.answer_detail.toPlainText()
    finally:
        window.close()
