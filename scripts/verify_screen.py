"""Visible desktop integration: real screen capture -> OCR -> current answer.

Uses only this application's widgets as a deterministic visible-page fixture.
It never interacts with a user's browser or other application.
Run from the repository root after importing the validation bank.
"""
import json
import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QFont, QPainter, QColor
from PySide6.QtWidgets import QApplication, QWidget

from newxky.bank import read_bank
from newxky.ui import MainWindow, STYLE


OUTPUT = Path("tmp/validation")


class Page(QWidget):
    def __init__(self):
        super().__init__()
        self.lines = []
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setWindowTitle("NewXKY 本地测试题目")
        self.setGeometry(30, 40, 1000, 1000)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("white"))
        painter.setPen(QColor("#222222"))
        painter.setFont(QFont("Microsoft YaHei", 17))
        y = 24
        for line in self.lines:
            rect = painter.boundingRect(QRect(24, y, 950, 900), Qt.TextWordWrap, line)
            painter.drawText(QRect(24, y, 950, rect.height() + 10), Qt.TextWordWrap, line)
            y += rect.height() + 22

    def question(self, q, order):
        self.lines = [f"1. {q.kind}题", q.stem]
        self.lines.extend(f"{label}. {q.options[old]}" for label, old in zip(q.options, order))
        self.update()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=int, default=0)
    args = parser.parse_args()
    app = QApplication([])
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE)
    bank = read_bank(OUTPUT / "bank.json")
    window = MainWindow(OUTPUT)
    window.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    origin = app.screens()[args.screen].geometry().topLeft()
    window.move(origin.x() + 1140, origin.y() + 40)
    window.resize(1120, 1000)
    page = Page()
    page.move(origin.x() + 30, origin.y() + 40)
    page.show()
    window.show()
    q1 = bank.questions[0]
    q2 = bank.questions[1]
    multi = next(q for q in bank.questions if q.kind == "多选")
    judgment = next(q for q in bank.questions if q.kind == "判断")
    cases = [(q1, tuple(q1.options)), (q2, tuple(reversed(q2.options))),
             (multi, tuple(reversed(multi.options))), (judgment, tuple(reversed(judgment.options)))]
    state = {"stage": -1, "started": time.monotonic(), "results": [], "changed": 0.0, "cleared": False}

    def finish(code, message):
        print(message, flush=True)
        (OUTPUT / "screen-results.json").write_text(json.dumps(state["results"], ensure_ascii=False, indent=2), encoding="utf-8")
        window.stop_monitor("测试完成")
        window.close()
        page.close()
        app.exit(code)

    def advance():
        state["stage"] += 1
        state["changed"] = time.monotonic()
        state["cleared"] = False
        if state["stage"] < len(cases):
            q, order = cases[state["stage"]]
            page.question(q, order)
        else:
            page.lines = ["1. 这是没有收录在题库中的测试题目", "A. 未知甲", "B. 未知乙"]
            page.update()

    def tick():
        if time.monotonic() - state["started"] > 65:
            window.grab().save(str(OUTPUT / "ui-failed.png"))
            if window._last_capture:
                window._last_capture.save(str(OUTPUT / "screen-failed.png"))
            print(window.message.text(), window.ocr_text.toPlainText(), flush=True)
            finish(1, "TIMEOUT")
            return
        if window.loading:
            return
        if state["stage"] == -1:
            window.region_selected(QRect(page.mapToGlobal(page.rect().topLeft()), page.size()))
            advance()
            window.toggle_monitor()
            return
        if window.answer.text() == "—" and state["stage"] > 0:
            state["cleared"] = True
        if state["stage"] < len(cases):
            q, order = cases[state["stage"]]
            expected = " / ".join(label for label, old in zip(q.options, order) if old in q.answers)
            if window.answer.text() == expected and str(q.number) in window.provenance.text():
                if state["stage"] > 0 and not state["cleared"]:
                    finish(1, "OLD ANSWER WAS NOT CLEARED")
                    return
                result = {"kind": q.kind, "question": q.number, "answer": expected, "seconds": round(time.monotonic() - state["changed"], 2)}
                state["results"].append(result)
                print(result, flush=True)
                window.grab().save(str(OUTPUT / f"ui-matched-{state['stage']}.png"))
                advance()
        elif window.status.text() == "未找到答案" and window.ocr_text.toPlainText():
            assert window.answer.text() == "—"
            state["results"].append({"unknown": "no answer", "cleared_previous": state["cleared"]})
            window.grab().save(str(OUTPUT / "ui-unknown.png"))
            finish(0, "SCREEN_PIPELINE_PASSED")

    timer = QTimer()
    timer.setInterval(50)
    timer.timeout.connect(tick)
    timer.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
