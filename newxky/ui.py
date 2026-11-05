import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt, QThreadPool, QTimer
from PySide6.QtGui import QFont, QGuiApplication, QIcon, QImage
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget, QHeaderView, QListView,
)

from .bank import load_pdf, merge_banks, read_bank, save_bank
from .floating import FloatingAnswer
from .matching import KnowledgeIndex
from .models import Bank
from .monitor import FrameTracker
from .ocr import LocalOCR
from .region import RegionBorder, RegionSelector
from .search import SearchWindow
from .text_format import emphasize_bank_order
from .workers import Worker


STYLE = """
QMainWindow, QWidget#root { background: #f3f6fa; color: #182c43; }
QWidget { font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 13px; color: #182c43; }
QFrame#card { background: white; border: 1px solid #e1e7ee; border-radius: 14px; }
QLabel#brand { font-size: 22px; font-weight: 700; color: #102a43; }
QLabel#title { font-size: 25px; font-weight: 700; }
QLabel#muted { color: #63778c; }
QLabel#eyebrow { color: #0b8c78; font-weight: 600; }
QLabel#number { font-size: 38px; font-weight: 700; }
QLabel#answer { font-size: 50px; font-weight: 700; color: #087c68; }
QLabel#status { background: #e8f5f1; color: #087c68; padding: 7px 12px; border-radius: 10px; }
QPushButton { background: white; border: 1px solid #d8e1ea; border-radius: 8px; padding: 10px 14px; font-weight: 600; }
QPushButton:hover { background: #edf5f6; border-color: #82bfb5; }
QPushButton:disabled { color: #a3afbb; background: #f2f4f7; }
QPushButton#primary { background: #087f70; color: white; border: 1px solid #087f70; }
QPushButton#primary:hover { background: #066c5f; }
QPushButton#primary:disabled { background: #b1c9c4; border-color: #b1c9c4; }
QTextEdit, QTableWidget, QLineEdit { background: white; border: 1px solid #e0e7ef; border-radius: 8px; padding: 8px; selection-background-color: #d7ede7; }
QTableWidget::item:selected { background: #d7ede7; color: #182c43; }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 10px 14px; color: #6b7e90; }
QTabBar::tab:selected { color: #087f70; border-bottom: 2px solid #087f70; }
QProgressBar { border: 0; background: #e4ebeF; border-radius: 4px; height: 8px; }
QProgressBar::chunk { background: #12ad90; border-radius: 4px; }
QComboBox { border: 1px solid #d8e1ea; padding: 6px; border-radius: 6px; background: white; }
QComboBox#captureInterval { background: #f7fcfa; color: #126658; border: 1px solid #bfdbd2; border-radius: 8px; padding: 8px 28px 8px 10px; font-weight: 600; }
QComboBox#captureInterval:hover { background: #edf8f3; border-color: #69b8a5; }
QComboBox#captureInterval:focus, QComboBox#captureInterval:on { background: white; border-color: #0b8c77; }
QComboBox#captureInterval::drop-down { width: 26px; border: 0; subcontrol-origin: padding; subcontrol-position: top right; }
QComboBox#captureInterval::down-arrow { image: url('__CAPTURE_CHEVRON__'); width: 14px; height: 14px; }
QComboBox#captureInterval QAbstractItemView { background: white; color: #182c43; border: 1px solid #bfdbd2; border-radius: 8px; padding: 4px; outline: 0; selection-background-color: #dcefe7; selection-color: #075e50; }
QComboBox#captureInterval QAbstractItemView::item { min-height: 28px; padding: 5px 8px; border-radius: 5px; }
QComboBox#captureInterval QAbstractItemView::item:selected { background: #dcefe7; color: #075e50; }
QHeaderView::section { background: #f4f7fa; border: 0; padding: 8px; }
QSplitter::handle { background: transparent; height: 10px; }
"""
ASSETS = Path(__file__).resolve().parents[1] / "assets"
STYLE = STYLE.replace("__CAPTURE_CHEVRON__", (ASSETS / "chevron-down.svg").as_posix())


def label(text, name="", wrap=False):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.PlainText)
    return widget


def card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(12)
    return frame, layout


class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path):
        super().__init__()
        self.data_dir = data_dir
        self.bank = Bank()
        self.index = KnowledgeIndex([])
        self.ocr = LocalOCR()
        self.tracker = FrameTracker()
        self.region = None
        self.running = False
        self.importing = False
        self.loading = False
        self._jobs = set()
        self._selectors = []
        self._closing = False
        self._last_issue = ""
        self._last_capture = None
        self.search_window = None
        self._ocr_warming = False
        self._ocr_ready = False
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.border = RegionBorder()
        self.floating = FloatingAnswer()
        self.floating.expand.connect(self.expand_main)
        self.floating.toggle.connect(self.toggle_monitor)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.capture)
        self.setWindowTitle("NewXKY · 区域答题助手")
        self.resize(1120, 850)
        self.setMinimumSize(960, 730)
        self._build_ui()
        self._read_settings()
        QTimer.singleShot(0, self.restore_bank)

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(20)
        sidebar = QVBoxLayout()
        sidebar.setSpacing(16)
        sidebar.addWidget(label("NewXKY", "brand"))
        sidebar.addWidget(label("本地题库 · 屏幕区域识别", "muted"))
        bank_card, bank_layout = card()
        bank_card.setFixedWidth(260)
        bank_layout.addWidget(label("01 / 题库", "eyebrow"))
        self.count = label("0", "number")
        bank_layout.addWidget(self.count)
        self.bank_summary = label("尚未导入题库", "muted", True)
        bank_layout.addWidget(self.bank_summary)
        self.import_button = QPushButton("＋ 导入 PDF 题库")
        self.import_button.setObjectName("primary")
        self.import_button.clicked.connect(self.import_files)
        bank_layout.addWidget(self.import_button)
        self.clear_button = QPushButton("清空题库")
        self.clear_button.clicked.connect(self.clear_bank)
        bank_layout.addWidget(self.clear_button)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        bank_layout.addWidget(self.progress)
        self.import_status = label("支持多份 PDF；自动保存、去重", "muted", True)
        bank_layout.addWidget(self.import_status)
        sidebar.addWidget(bank_card)
        region_card, region_layout = card()
        region_layout.addWidget(label("02 / 识别区域", "eyebrow"))
        self.region_info = label("尚未选择屏幕区域", "muted", True)
        region_layout.addWidget(self.region_info)
        self.select_button = QPushButton("框选 / 重选区域")
        self.select_button.clicked.connect(self.select_region)
        region_layout.addWidget(self.select_button)
        speed_row = QHBoxLayout()
        speed_row.addWidget(label("画面检测"))
        self.interval = QComboBox()
        self.interval.setObjectName("captureInterval")
        self.interval.setMinimumWidth(146)
        self.interval.setMaxVisibleItems(4)
        interval_view = QListView(self.interval)
        interval_view.setSpacing(3)
        interval_view.setMinimumWidth(162)
        self.interval.setView(interval_view)
        self.interval.addItem("100 毫秒（快）", 100)
        self.interval.addItem("250 毫秒", 250)
        self.interval.addItem("500 毫秒", 500)
        self.interval.addItem("1000 毫秒", 1000)
        self.interval.currentIndexChanged.connect(lambda: self.timer.setInterval(self.interval.currentData()))
        speed_row.addWidget(self.interval)
        region_layout.addLayout(speed_row)
        self.border_check = QCheckBox("显示区域边框")
        self.border_check.setChecked(True)
        self.border_check.toggled.connect(self.update_border)
        region_layout.addWidget(self.border_check)
        self.pin_check = QCheckBox("答案窗口置顶")
        self.pin_check.toggled.connect(self.pin_window)
        region_layout.addWidget(self.pin_check)
        sidebar.addWidget(region_card)
        sidebar.addStretch()
        sidebar.addWidget(label("先导入题库，再框选完整题目。\n浏览器需保持可见，答案窗口放在区域外。\n\n识别和匹配均在本机完成。", "muted", True))
        sidebar.setSizeConstraint(QVBoxLayout.SetMinimumSize)
        sidebar_widget = QWidget()
        sidebar_widget.setLayout(sidebar)
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setFrameShape(QFrame.NoFrame)
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setFixedWidth(280)
        sidebar_scroll.setWidget(sidebar_widget)
        outer.addWidget(sidebar_scroll)
        main = QVBoxLayout()
        main.setSpacing(16)
        header = QHBoxLayout()
        headings = QVBoxLayout()
        headings.addWidget(label("区域答题助手", "title"))
        headings.addWidget(label("识别当前题目，核对题库中的正确答案", "muted"))
        header.addLayout(headings)
        header.addStretch()
        self.status = label("准备就绪", "status")
        self.status.setMinimumWidth(140)
        self.status.setAlignment(Qt.AlignCenter)
        header.addWidget(self.status, 0, Qt.AlignTop)
        main.addLayout(header)
        actions = QHBoxLayout()
        self.start_button = QPushButton("开始识别")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.toggle_monitor)
        actions.addWidget(self.start_button)
        self.retry_button = QPushButton("重新识别当前画面")
        self.retry_button.clicked.connect(self.retry)
        actions.addWidget(self.retry_button)
        float_button = QPushButton("悬浮答案")
        float_button.clicked.connect(self.show_floating)
        actions.addWidget(float_button)
        self.search_button = QPushButton("关键词查答案")
        self.search_button.setShortcut("Ctrl+F")
        self.search_button.setToolTip("搜索题干或选项关键词（Ctrl+F）")
        self.search_button.clicked.connect(self.show_search)
        actions.addWidget(self.search_button)
        actions.addStretch()
        self.timing = label("题目文字变化后自动更新", "muted")
        self.timing.setWordWrap(True)
        main.addLayout(actions)
        main.addWidget(self.timing)
        answer_card, answer_layout = card()
        self.answer_title = label("当前题目 / 答案", "eyebrow")
        self.answer_title.setTextFormat(Qt.RichText)
        answer_layout.addWidget(self.answer_title)
        self.answer = label("—", "answer")
        answer_layout.addWidget(self.answer)
        self.message = label("导入题库并选择区域后，点击“开始识别”。", "muted", True)
        self.message.setTextFormat(Qt.RichText)
        answer_layout.addWidget(self.message)
        self.answer_detail = label("", wrap=True)
        self.answer_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        answer_layout.addWidget(self.answer_detail)
        self.provenance = label("", "muted", True)
        self.provenance.setTextFormat(Qt.RichText)
        answer_layout.addWidget(self.provenance)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(answer_card)
        scroll.setMinimumHeight(230)
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(scroll)
        tabs = QTabWidget()
        self.ocr_text = QTextEdit()
        self.ocr_text.setReadOnly(True)
        self.ocr_text.setPlaceholderText("这里显示本地 OCR 识别到的文字，方便检查是否漏掉题干或选项。")
        tabs.addTab(self.ocr_text, "识别文字")
        self.question_text = QTextEdit()
        self.question_text.setReadOnly(True)
        self.question_text.setPlaceholderText("匹配后显示 PDF 中的完整题目及来源。")
        tabs.addTab(self.question_text, "题库原文")
        self.bank_table = QTableWidget(0, 4)
        self.bank_table.setHorizontalHeaderLabels(["文件", "页数", "有效题目", "异常"])
        self.bank_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.bank_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.bank_table.setSelectionBehavior(QTableWidget.SelectRows)
        tabs.addTab(self.bank_table, "已导入题库")
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        tabs.addTab(self.logs, "导入 / 运行记录")
        splitter.addWidget(tabs)
        splitter.setSizes([360, 300])
        main.addWidget(splitter, 1)
        outer.addLayout(main, 1)
        self.refresh_controls()

    def log(self, text):
        self.logs.append(f"[{datetime.now():%H:%M:%S}] {text}".replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    def launch(self, function, result, error, progress=None):
        job = Worker(function)
        self._jobs.add(job)
        job.signals.result.connect(result)
        job.signals.error.connect(error)
        if progress:
            job.signals.progress.connect(progress)
        job.signals.finished.connect(lambda: self._job_finished(job))
        self.pool.start(job)

    def _job_finished(self, job):
        self._jobs.discard(job)
        if self._closing and not self._jobs:
            self.close()

    def restore_bank(self):
        self.loading = True
        self.refresh_controls()
        self.launch(lambda _: (lambda bank: (bank, KnowledgeIndex(bank.questions)))(read_bank(self.data_dir / "bank.json")),
                    self.bank_restored, self.restore_failed)

    def bank_restored(self, result):
        self.bank, self.index = result
        self.loading = False
        self.show_bank()
        self.log(f"已恢复 {len(self.bank.questions)} 道题。" if self.bank.questions else "请导入 PDF 题库。")

    def restore_failed(self, message):
        self.loading = False
        self.log(f"题库读取失败：{message}")
        self.import_status.setText("题库缓存读取失败，可重新导入。")
        self.refresh_controls()

    def show_bank(self):
        self.count.setText(f"{len(self.bank.questions):,}")
        kinds = Counter(q.kind for q in self.bank.questions)
        self.bank_summary.setText(" · ".join(f"{kind} {count}" for kind, count in kinds.items()) or "尚未导入题库")
        names = list(dict.fromkeys(Path(p).name for p in self.bank.sources))
        self.bank_table.setRowCount(len(names))
        for row, name in enumerate(names):
            questions = [q for q in self.bank.questions if q.source == name]
            pages = {page for q in questions for page in q.pages}
            issues = sum(name in issue for issue in self.bank.issues)
            for column, value in enumerate((name, f"至少 {max(pages, default=0)}", str(len(questions)), str(issues))):
                self.bank_table.setItem(row, column, QTableWidgetItem(value))
        if self.search_window is not None:
            self.search_window.set_index(self.index)
        self.refresh_controls()
        if self.bank.questions and not self._ocr_ready and not self._ocr_warming and not self._closing:
            self._ocr_warming = True
            self.launch(lambda _: self.ocr.warmup(), self.ocr_prepared, self.ocr_prepare_failed)

    def ocr_prepared(self, _):
        self._ocr_warming = False
        self._ocr_ready = True
        self.log("本地 OCR 已预加载，开始识别时无需再次加载模型。")

    def ocr_prepare_failed(self, message):
        self._ocr_warming = False
        self.log(f"OCR 预加载未完成，开始识别时将重试：{message}")

    def refresh_controls(self):
        ready = not self.importing and not self.loading and not self._closing
        self.import_button.setEnabled(ready)
        self.clear_button.setEnabled(ready and bool(self.bank.questions))
        self.start_button.setEnabled(ready and bool(self.bank.questions) and self.region is not None)
        self.retry_button.setEnabled(ready and self.running)
        self.select_button.setEnabled(ready)
        self.search_button.setEnabled(not self._closing)
        self.start_button.setText("暂停识别" if self.running else "开始识别")
        self.floating.toggle_button.setText(self.start_button.text())
        self.floating.toggle_button.setEnabled(self.start_button.isEnabled())

    def show_search(self):
        if self.search_window is None:
            self.search_window = SearchWindow(self.index, self)
        self.search_window.show()
        self.search_window.raise_()
        self.search_window.activateWindow()
        self.search_window.query.setFocus()

    def show_floating(self):
        screen = QGuiApplication.screenAt(self.region.center()) if self.region is not None else self.screen()
        geometry = screen.availableGeometry()
        self.floating.move(geometry.right() - self.floating.width() - 20, geometry.top() + 20)
        self.sync_floating()
        self.showMinimized()
        self.floating.show()
        self.floating.raise_()

    def expand_main(self):
        self.floating.hide()
        if not self._closing:
            self.showNormal()
            self.activateWindow()

    def sync_floating(self):
        self.floating.answer.setText(self.answer.text())
        self.floating.answer.setStyleSheet(self.answer.styleSheet())
        self.floating.message.setText(self.message.text())
        self.floating.detail.setText(self.answer_detail.text())

    def import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "导入 PDF 题库（可多选）", "", "PDF 题库 (*.pdf *.PDF)")
        if paths:
            self.import_paths(paths)

    def import_paths(self, paths):
        self.stop_monitor("正在导入题库")
        self.importing = True
        self.progress.show()
        self.progress.setValue(0)
        self.refresh_controls()
        old_bank = self.bank
        def run(progress):
            banks = [old_bank]
            for index, path in enumerate(paths):
                def report(page, total, message):
                    progress(int((index + page / total) * 1000 / len(paths)), 1000, message)
                bank = load_pdf(path, report)
                if not bank.questions:
                    raise ValueError("\n".join(bank.issues[:8]))
                banks.append(bank)
            combined = merge_banks(banks)
            index = KnowledgeIndex(combined.questions)
            save_bank(combined, self.data_dir / "bank.json")
            return combined, index
        self.launch(run, self.import_complete, self.import_failed, self.import_progress)

    def import_progress(self, value, total, message):
        self.progress.setMaximum(total)
        self.progress.setValue(value)
        self.import_status.setText(message)

    def import_complete(self, result):
        self.bank, self.index = result
        self.importing = False
        self.progress.hide()
        self.show_bank()
        self.status.setText("题库已就绪")
        self.import_status.setText(f"共 {len(self.bank.questions)} 题 · 去重 {self.bank.duplicates} 题 · 异常 {len(self.bank.issues)} 条")
        self.log(self.import_status.text())
        for issue in self.bank.issues:
            self.log(issue)
        if self.bank.issues:
            QMessageBox.information(self, "导入完成，请检查异常", f"已导入 {len(self.bank.questions)} 道有效题目。\n{len(self.bank.issues)} 条异常未导入，详情见“导入 / 运行记录”。")
        self.message.setText("题库已保存；选择区域并开始识别。")

    def import_failed(self, message):
        self.importing = False
        self.progress.hide()
        self.import_status.setText("导入失败，原题库已保留")
        self.log(message)
        self.refresh_controls()
        QMessageBox.warning(self, "导入失败", message)

    def clear_bank(self):
        if QMessageBox.question(self, "清空题库", "清空本软件保存的题库？原 PDF 文件不受影响。") != QMessageBox.Yes:
            return
        self.stop_monitor("题库已清空")
        try:
            save_bank(Bank(), self.data_dir / "bank.json")
        except OSError as error:
            QMessageBox.warning(self, "清空失败", str(error))
            return
        self.bank = Bank()
        self.index = KnowledgeIndex([])
        self.import_status.setText("请选择 PDF 题库")
        self.show_bank()

    def select_region(self):
        self.stop_monitor("正在选择区域")
        self.hide()
        self.border.hide()
        QTimer.singleShot(250, self._open_selectors)

    def _open_selectors(self):
        self._selectors = [RegionSelector(screen) for screen in QGuiApplication.screens()]
        for selector in self._selectors:
            selector.selected.connect(self.region_selected)
            selector.cancelled.connect(self.cancel_selection)
            selector.show()
        if self._selectors:
            self._selectors[0].activateWindow()

    def _close_selectors(self):
        for selector in self._selectors:
            selector.close()
            selector.deleteLater()
        self._selectors.clear()
        self.show()
        self.activateWindow()

    def region_selected(self, rect):
        self.region = QRect(rect)
        self._close_selectors()
        self.region_info.setText(f"位置 {rect.x()}, {rect.y()}\n大小 {rect.width()} × {rect.height()}")
        self._save_settings()
        self.status.setText("区域已选择")
        self.message.setText("请把浏览器题目放进框选区域，将本窗口移到区域外，然后开始识别。")
        self.refresh_controls()
        self.update_border()

    def cancel_selection(self):
        self._close_selectors()
        self.status.setText("已取消框选")
        self.update_border()

    def pin_window(self, checked):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        self.show()

    def update_border(self):
        if self.region is not None:
            self.border.set_region(self.region)
        self.border.setVisible(self.region is not None and self.border_check.isChecked() and not self._selectors and not self._closing)

    def toggle_monitor(self):
        if self.running:
            self.stop_monitor("已暂停")
        elif self.region is not None and self.bank.questions:
            self.running = True
            self.tracker.invalidate()
            self._last_issue = ""
            self.clear_answer("正在检测画面…")
            self.status.setText("识别中")
            self.timer.start()
            self.refresh_controls()
            self.capture()

    def clear_answer(self, message):
        self.answer_title.setText("当前题目 / 答案")
        self.answer.setText("—")
        self.answer.setStyleSheet("")
        self.answer_detail.clear()
        self.provenance.clear()
        self.message.setText(emphasize_bank_order(message))
        self.question_text.clear()
        self.sync_floating()

    def stop_monitor(self, reason="已暂停"):
        self.running = False
        self.timer.stop()
        self.tracker.invalidate()
        self.clear_answer(reason)
        self.ocr_text.clear()
        self.status.setText(reason)
        self.refresh_controls()

    def retry(self):
        self.tracker.invalidate()
        self.clear_answer("正在重新识别…")
        self.ocr_text.clear()
        self.capture()

    def capture(self):
        if not self.running or self.region is None or self._closing:
            return
        issue = ""
        screen = QGuiApplication.screenAt(self.region.center())
        if screen is None or not screen.geometry().contains(self.region):
            issue = "显示器布局已变化，请重新框选单块显示器内的区域"
        elif self.isVisible() and not self.isMinimized() and self.frameGeometry().intersects(self.region):
            issue = "答案窗口遮挡识别区域，请把本窗口移到区域外"
        elif self.floating.isVisible() and self.floating.frameGeometry().intersects(self.region):
            issue = "悬浮答案遮挡识别区域，请将悬浮窗移到区域外"
        elif (self.search_window is not None and self.search_window.isVisible()
              and not self.search_window.isMinimized() and self.search_window.frameGeometry().intersects(self.region)):
            issue = "搜索窗口遮挡识别区域，请将搜索窗口移到区域外"
        if issue:
            if issue != self._last_issue:
                self.tracker.invalidate()
                self.clear_answer(issue)
                self.ocr_text.clear()
                self._last_issue = issue
                self.status.setText("等待调整区域")
            return
        self._last_issue = ""
        # QScreen capture uses screen-local logical coordinates. Keep native pixel
        # resolution in the PNG so Windows scaling does not blur OCR input.
        origin = screen.geometry().topLeft()
        pixmap = screen.grabWindow(0, self.region.x() - origin.x(), self.region.y() - origin.y(), self.region.width(), self.region.height())
        if pixmap.isNull():
            self.stop_monitor("截屏失败，请重新选择可见区域")
            return
        image = pixmap.toImage()
        from numpy import frombuffer, uint8
        gray = image.convertToFormat(QImage.Format_Grayscale8)
        pixels = frombuffer(gray.constBits(), dtype=uint8).reshape(gray.height(), gray.bytesPerLine())[:, :gray.width()]
        now = time.monotonic()
        if self.tracker.observe_image(pixels, now):
            self.clear_answer("题目文字已变化，正在识别新题目…")
            self.ocr_text.clear()
            self.status.setText("等待画面稳定")
            self._last_capture = image
        if not self.tracker.ready(now):
            return
        revision = self.tracker.begin()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        self._last_capture.save(buffer, "PNG")
        buffer.close()
        content = bytes(data)
        index = self.index
        self.status.setText("正在识别")
        started = time.monotonic()
        def recognize(_):
            text = self.ocr.recognize(content)
            return text, index.lookup(text), time.monotonic() - started
        self.launch(recognize, lambda result: self.recognized(revision, result), lambda error: self.recognition_failed(revision, error))

    def recognized(self, revision, result):
        if not self.tracker.finish(revision) or not self.running:
            return
        text, match, elapsed = result
        self.ocr_text.setPlainText(text)
        self.timing.setText(f"最近识别 {elapsed:.1f} 秒 · {datetime.now():%H:%M:%S}")
        self.clear_answer(match.message)
        self.status.setText({"matched": "已核对网页选项", "reference": "已找到题库答案", "candidate": "相似题待核对", "unverified": "网页选项待核对", "incomplete": "等待完整选项", "ambiguous": "匹配不唯一"}.get(match.status, "未找到答案"))
        if match.status in ("matched", "reference"):
            self.answer.setText(" / ".join(match.answers))
            self.answer_detail.setText("\n".join(f"{letter}. {match.options[letter]}" for letter in match.answers))
            q = match.question
            scope = "答案字母已按当前画面选项顺序对应。" if match.status == "matched" else "题库顺序：网页可能调整选项顺序，请按选项内容核对。"
            self.answer_title.setText(emphasize_bank_order("当前题目 / 网页答案" if match.status == "matched" else "当前题目 / 题库答案（题库顺序）"))
            self.provenance.setText(emphasize_bank_order(f"{q.kind} · {q.source} · 第 {q.number} 题 · PDF 第 {', '.join(map(str, q.pages))} 页\n{scope}"))
        elif match.status in ("candidate", "unverified") and match.question:
            q = match.question
            reference = match.reference
            answers = reference.answers if reference else q.answers
            options = reference.options if reference else q.options
            screen_order = reference is not None and reference.screen_order
            title = "相似题参考" if match.status == "candidate" else "选项待核对"
            scope = "参考网页顺序" if screen_order else "题库顺序"
            self.answer_title.setText(emphasize_bank_order(f"{title} / {scope}", warning=True))
            self.answer.setText("参考 " + " / ".join(answers))
            self.answer.setStyleSheet("color:#c62828;font-size:36px;")
            self.message.setText(emphasize_bank_order(match.message, warning=True))
            correct = "\n".join(f"{letter}. {options[letter]}" for letter in answers)
            stem_title = "相似题题干" if match.status == "candidate" else "题库原题"
            self.answer_detail.setText(f"{stem_title}：{q.stem}\n\n参考答案：\n{correct}")
            caution = ("选项文字尚未完全核对，请按完整内容确认。" if match.status == "unverified"
                       else f"文字相似度 {match.score:.0%} · 请核对题干差异。")
            self.provenance.setText(emphasize_bank_order(
                f"{q.kind} · {q.source} · 第 {q.number} 题 · PDF 第 {', '.join(map(str, q.pages))} 页\n"
                f"{scope} · 仅供参考 · {caution}", warning=True))
        if match.question:
            q = match.question
            # Keep the source question available to compare with the current OCR.
            self.question_text.setPlainText(f"{q.source} · 第 {q.number} 题 · PDF 页 {', '.join(map(str, q.pages))}\n\n{q.stem}\n\n" + "\n".join(f"{k}. {v}" for k, v in q.options.items()))
        self.sync_floating()

    def recognition_failed(self, revision, message):
        if not self.tracker.finish(revision) or not self.running:
            return
        self.stop_monitor("识别失败，可重试")
        self.message.setText(emphasize_bank_order(message))
        self.sync_floating()
        self.log(message)

    def _read_settings(self):
        try:
            data = json.loads((self.data_dir / "settings.json").read_text(encoding="utf-8"))
            rect = QRect(*data["region"])
            if rect.width() >= 120 and rect.height() >= 80 and any(s.geometry().contains(rect) for s in QGuiApplication.screens()):
                self.region = rect
                self.region_info.setText(f"已恢复上次区域\n{rect.x()}, {rect.y()} · {rect.width()} × {rect.height()}")
                self.update_border()
        except (OSError, ValueError, TypeError, KeyError):
            pass

    def _save_settings(self):
        if self.region is None:
            return
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            path = self.data_dir / "settings.json"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"region": self.region.getRect()}), encoding="utf-8")
            temporary.replace(path)
        except OSError as error:
            self.log(f"区域设置未保存：{error}")

    def closeEvent(self, event):
        self.timer.stop()
        self.running = False
        self.tracker.invalidate()
        self._closing = True
        self.border.close()
        self.floating.close()
        if self.search_window is not None:
            self.search_window.close()
        self._save_settings()
        if self._jobs:
            self.setEnabled(False)
            self.status.setText("正在完成后台任务后退出…")
            event.ignore()
        else:
            event.accept()


def run(data_dir=None, *, hide_console=False):
    app = QApplication(sys.argv)
    app.setApplicationName("NewXKY")
    app.setOrganizationName("NewXKY")
    app.setWindowIcon(QIcon(str(ASSETS / "NewXKY.ico")))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE)
    root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    window = MainWindow(Path(data_dir) if data_dir else root / "data")
    if hide_console and sys.platform == "win32":
        # Only hide this GUI application's own launch console. Other windows
        # and system settings are never touched; CLI diagnostics stay visible.
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        user = ctypes.WinDLL("user32", use_last_error=True)
        kernel.GetConsoleWindow.restype = ctypes.c_void_p
        user.ShowWindow.argtypes = (ctypes.c_void_p, ctypes.c_int)
        console = kernel.GetConsoleWindow()
        if console:
            user.ShowWindow(console, 0)
    window.show()
    return app.exec()
