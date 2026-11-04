"""Verify background import, persisted restore, region selection and floating UI."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from newxky.bank import read_bank
from newxky.ui import MainWindow, STYLE


def main():
    app = QApplication([])
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE)
    output = Path("tmp/validation/controls")
    window = MainWindow(output)
    window.show()
    state = {"stage": 0, "start": time.monotonic(), "ticks": 0}

    def tick():
        state["ticks"] += 1
        if time.monotonic() - state["start"] > 60:
            raise RuntimeError("UI validation timed out")
        if window.loading:
            return
        if state["stage"] == 0:
            window.import_paths([sys.argv[1]])
            state["stage"] = 1
        elif state["stage"] == 1 and not window.importing:
            assert len(window.bank.questions) == 1291
            assert len(read_bank(output / "bank.json").questions) == 1291
            assert state["ticks"] > 10, "Event loop must stay responsive during PDF import"
            window.select_region()
            state["stage"] = 2
        elif state["stage"] == 2 and window._selectors:
            selector = window._selectors[0]
            selector.activateWindow()
            QTest.mousePress(selector, Qt.LeftButton, pos=QPoint(80, 420))
            QTest.mouseMove(selector, QPoint(1000, 1000))
            QTest.mouseRelease(selector, Qt.LeftButton, pos=QPoint(1000, 1000))
            assert window.region == QRect(80, 420, 921, 581)
            window.show_floating()
            assert window.floating.isVisible() and window.isMinimized()
            window.expand_main()
            assert not window.floating.isVisible() and not window.isMinimized()
            window.running = True
            window.tracker.observe(b"test", 0)
            revision = window.tracker.begin()
            q = window.bank.questions[829]
            match = window.index.lookup(q.stem)
            window.recognized(revision, (q.stem, match, .1))
            assert window.answer.text() == "A / B / C"
            assert "题库顺序" in window.answer_title.text()
            assert "森林火灾" in window.answer_detail.text()
            window.grab().save("tmp/validation/ui-bank-reference.png")
            window.show_floating()
            assert window.floating.answer.text() == "A / B / C"
            window.floating.grab().save("tmp/validation/ui-floating.png")
            window.stop_monitor("已暂停")
            assert window.floating.answer.text() == "—"
            window.close()
            print("IMPORT_PERSIST_REGION_FLOATING_PASSED", flush=True)
            app.quit()

    timer = QTimer()
    timer.setInterval(100)
    timer.timeout.connect(tick)
    timer.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
