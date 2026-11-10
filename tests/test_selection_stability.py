"""Selecting an option restyles the card; it must not rewrite the answer."""
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


def question() -> Question:
    return Question(
        1, "单选",
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
    window.auto_scroll.setChecked(False)
    return window


def show(window, text, match, revision_seed=b"frame"):
    window.tracker.observe(revision_seed, 0)
    revision = window.tracker.begin()
    window.recognized(revision, (text, match, .1))


def test_weaker_reread_of_the_clicked_card_keeps_the_verified_answer(tmp_path, monkeypatch):
    q = question()
    window = build(tmp_path, monkeypatch, [q])
    try:
        text = (q.stem + "\nA. " + q.options["A"] + "\nB. " + q.options["B"])
        matched = window.index.lookup(text)
        assert matched.status == "matched"
        show(window, text, matched)
        assert window.answer.text() == "B"
        assert window.status.text() == "已核对网页选项"

        # The user ticks B: the page only restyles it, and the letter is lost
        # from the next read, so the matcher offers bank-order letters instead.
        degraded = Match(
            "reference",
            "题干与全部选项内容已核对；字母或换行未完整识别，以下字母和内容按题库顺序显示",
            q, q.answers, q.options, 1,
        )
        show(window, text, degraded, b"after-click")
        assert window.answer.text() == "B"
        assert window.status.text() == "已核对网页选项"
        assert "c62828" not in window.answer.styleSheet()
    finally:
        window.close()


def test_capture_keeps_the_answer_when_only_the_style_changed(tmp_path, monkeypatch):
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

        tick()                      # first frame: waits for the picture to settle
        tick()
        assert window.answer.text() == "B"
        state["frame"] = 1
        tick()
        assert window.answer.text() == "B"
        assert window.status.text() == "已核对网页选项"
    finally:
        window.close()


def test_different_question_replaces_the_verified_answer(tmp_path, monkeypatch):
    first = question()
    second = Question(2, "单选", "关于重要数据目录，下列说法正确的是（）",
                      {"A": "正确内容", "B": "其他内容"}, ("A",), (3,))
    window = build(tmp_path, monkeypatch, [first, second])
    try:
        text = (first.stem + "\nA. " + first.options["A"] + "\nB. " + first.options["B"])
        show(window, text, window.index.lookup(text))
        assert window.answer.text() == "B"

        next_text = (second.stem + "\nA. " + second.options["A"]
                     + "\nB. " + second.options["B"])
        show(window, next_text, window.index.lookup(next_text), b"next-card")
        assert window.answer.text() == "A"
        assert second.stem in window.answer_detail.toPlainText()
    finally:
        window.close()


def test_complete_reread_with_different_letters_still_updates(tmp_path, monkeypatch):
    q = question()
    window = build(tmp_path, monkeypatch, [q])
    try:
        text = (q.stem + "\nA. " + q.options["A"] + "\nB. " + q.options["B"])
        show(window, text, window.index.lookup(text))
        assert window.answer.text() == "B"

        # Same contents, reordered on the page: every option was read back, so
        # the mapped letter really is A now and must be shown.
        reordered = (q.stem + "\nA. " + q.options["B"] + "\nB. " + q.options["A"])
        match = window.index.lookup(reordered)
        assert match.status == "matched" and match.answers == ("A",)
        show(window, reordered, match, b"reordered")
        assert window.answer.text() == "A"
    finally:
        window.close()


def test_shared_stem_and_answer_letters_do_not_reuse_the_previous_question(tmp_path, monkeypatch):
    first = question()
    second = Question(2, "单选", first.stem,
                      {"A": "第二道题错误内容", "B": "第二道题正确内容"}, ("B",), (2,))
    window = build(tmp_path, monkeypatch, [first, second])
    try:
        for q, seed in [(first, b"first"), (second, b"second")]:
            text = q.stem + "\n" + "\n".join(f"{k}. {v}" for k, v in q.options.items())
            show(window, text, window.index.lookup(text), seed)
        assert second.options["B"] in window.answer_detail.toPlainText()
        assert first.options["B"] not in window.answer_detail.toPlainText()
        assert "第 2 题" in window.provenance.text()
    finally:
        window.close()


def test_similarity_metadata_updates_before_and_after_an_exact_match(tmp_path, monkeypatch):
    q = question()
    window = build(tmp_path, monkeypatch, [q])
    try:
        show(window, q.stem, Match("candidate", "请核对题干", q, score=.82))
        assert "82%" in window.provenance.text()
        show(window, q.stem, Match("candidate", "请核对题干", q, score=.93), b"clearer")
        assert "93%" in window.provenance.text() and "82%" not in window.provenance.text()
        text = q.stem + "\n" + "\n".join(f"{k}. {v}" for k, v in q.options.items())
        show(window, text, window.index.lookup(text), b"exact")
        assert "相似度" not in window.provenance.text()
        assert window.status.text() == "已核对网页选项"
        show(window, text.replace("属于", "不属于"), Match("candidate", "请核对题干差异", q, score=.75),
             b"changed-stem")
        assert window.status.text() == "相似题待核对"
        assert "75%" in window.provenance.text()
        assert window.answer.text().startswith("参考")
    finally:
        window.close()


def test_changed_negation_cannot_keep_an_old_verified_answer(tmp_path, monkeypatch):
    q = question()
    window = build(tmp_path, monkeypatch, [q])
    try:
        text = q.stem + "\n" + "\n".join(f"{k}. {v}" for k, v in q.options.items())
        show(window, text, window.index.lookup(text))
        altered = text.replace("属于", "不属于")
        result = window.index.lookup(altered)
        assert result.status == "candidate"
        show(window, altered, result, b"negation")
        assert window.status.text() == "相似题待核对"
        assert window.answer.text().startswith("参考")
        assert "请核对题干差异" in window.provenance.text()
    finally:
        window.close()


def test_unknown_similar_stem_clears_the_previous_verified_answer(tmp_path, monkeypatch):
    q = question()
    window = build(tmp_path, monkeypatch, [q])
    try:
        text = q.stem + "\n" + "\n".join(f"{k}. {v}" for k, v in q.options.items())
        show(window, text, window.index.lookup(text))
        show(window, q.stem + "另一项要求", Match("missing", "题库未收录"), b"unknown")
        assert window.answer.text() == "—"
        assert window.provenance.text() == ""
    finally:
        window.close()


def test_partial_reread_with_reordered_visible_options_does_not_keep_old_letters(tmp_path, monkeypatch):
    q = Question(1, "单选", "测试部分选项换序", {
        "A": "甲的完整内容", "B": "乙的完整内容", "C": "丙的完整内容", "D": "丁的完整内容",
    }, ("B",), (1,))
    window = build(tmp_path, monkeypatch, [q])
    try:
        text = q.stem + "\n" + "\n".join(f"{k}. {v}" for k, v in q.options.items())
        show(window, text, window.index.lookup(text))
        reordered = q.stem + "\nA. " + q.options["B"] + "\nB. " + q.options["A"]
        match = window.index.lookup(reordered)
        assert match.status == "matched" and match.answers == ("A",)
        show(window, reordered, match, b"partial-reordered")
        assert window.answer.text() == "A"
    finally:
        window.close()


def test_changed_partial_option_cannot_restore_an_old_verified_snapshot(tmp_path, monkeypatch):
    q = Question(1, "单选", "测试部分选项内容变化", {
        "A": "甲的完整内容", "B": "乙的完整内容", "C": "丙的完整内容", "D": "丁的完整内容",
    }, ("B",), (1,))
    window = build(tmp_path, monkeypatch, [q])
    try:
        text = q.stem + "\n" + "\n".join(f"{k}. {v}" for k, v in q.options.items())
        show(window, text, window.index.lookup(text))
        altered = text[:text.rfind("\nD.")].replace("甲的", "不是甲的")
        match = window.index.lookup(altered)
        assert match.status == "reference"
        show(window, altered, match, b"changed-partial-option")
        assert window.status.text() != "已核对网页选项"
        assert "题库顺序" in window.provenance.text()
    finally:
        window.close()
