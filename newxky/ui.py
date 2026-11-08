"""NewXKY V1.0.7 desktop interface: region OCR, bank answer, 40-minute license."""
from __future__ import annotations

import json
import sys
import time
from difflib import SequenceMatcher
from collections import Counter
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QBuffer, QByteArray, QIODevice, QRect, Qt, QThreadPool, QTimer,
)
from PySide6.QtGui import QFont, QGuiApplication, QIcon, QImage
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QSizePolicy,
    QTextEdit, QVBoxLayout, QWidget,
)

from . import __version__
from .default_bank import SOURCE_LABEL, load_startup_bank
from .bank import normalized
from .keyword_search import SearchWindow
from .licensing import LicenseError, LicenseManager, LicenseState, format_remaining, valid_code
from .matching import KnowledgeIndex, clean_stem, screen_parts
from .models import Bank
from .monitor import FrameTracker
from .ocr import LocalOCR
from .region import RegionBorder, RegionSelector
from .text_format import emphasize_bank_order
from .workers import Worker


ASSETS = Path(__file__).resolve().parents[1] / "assets"

STYLE = """
QMainWindow, QWidget#root { background: #f3f6fa; color: #182c43; }
QWidget { font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 13px; color: #182c43; }
QFrame#card { background: white; border: 1px solid #e1e7ee; border-radius: 14px; }
QFrame#licenseBar { background: #ffffff; border: 1px solid #dce8e4; border-radius: 12px; }
QLabel#brand { font-size: 24px; font-weight: 700; color: #102a43; }
QLabel#title { font-size: 24px; font-weight: 700; }
QLabel#muted { color: #63778c; }
QLabel#eyebrow { color: #0b8c78; font-weight: 600; }
QLabel#bigCount { font-size: 34px; font-weight: 700; color: #102a43; }
QLabel#answer { font-size: 52px; font-weight: 700; color: #087c68; }
QLabel#status { background: #e8f5f1; color: #087c68; padding: 7px 12px; border-radius: 10px; }
QLabel#licenseBadge { background: #e8f5f1; color: #087c68; padding: 7px 12px; border-radius: 9px; font-weight: 700; }
QLabel#warning { color: #b42318; background: #fff4f2; border: 1px solid #f3c6c1; border-radius: 8px; padding: 8px 10px; }
QLabel#dialogStatus { color: #52667a; }
QLabel#version { color: #8b9bab; font-size: 12px; }
QPushButton { background: white; border: 1px solid #d8e1ea; border-radius: 8px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #edf5f6; border-color: #82bfb5; }
QPushButton:disabled { color: #a3afbb; background: #f2f4f7; }
QPushButton#primary { background: #087f70; color: white; border: 1px solid #087f70; }
QPushButton#primary:hover { background: #066c5f; }
QPushButton#primary:disabled { background: #b1c9c4; border-color: #b1c9c4; }
QPushButton#quiet { background: transparent; border: 0; color: #0b7f70; padding: 6px 8px; }
QPushButton#quiet:hover { background: #edf8f3; }
QPushButton#fallback { background:#fff4f2; color:#b42318; border:1px solid #f3c6c1; border-radius:8px; padding:7px 10px; font-weight:600; }
QPushButton#fallback:hover { background:#ffe9e6; }
QPushButton#searchAction { background:#0b8c78; color:white; border:1px solid #0b8c78; border-radius:10px; padding:10px 18px; font-size:14px; font-weight:700; }
QPushButton#searchAction:hover { background:#087f70; border-color:#087f70; }
QPushButton#searchAction:pressed { background:#066c5f; }
QDialog#searchDialog { background:#eef5f2; }
QFrame#searchHero { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #e7f6ef, stop:1 #f8fcfb); border:1px solid #cfe7dc; border-radius:16px; }
QLabel#searchHeroIcon { background:#0b8c78; color:white; border-radius:12px; font-size:25px; font-weight:700; }
QLabel#searchTitle { font-size:25px; font-weight:700; color:#102a43; }
QLabel#searchSubtitle { color:#5b7183; font-size:13px; }
QLabel#searchSourceChip { background:white; color:#087c68; border:1px solid #bfe3d7; border-radius:10px; padding:7px 11px; font-weight:600; }
QFrame#searchBarCard { background:white; border:1px solid #d7e7df; border-radius:12px; }
QLineEdit#searchInput { background:transparent; border:0; padding:7px 4px; font-size:15px; }
QPushButton#searchButton { background:#0b8c78; color:white; border:0; border-radius:8px; padding:10px 24px; font-weight:700; }
QPushButton#searchButton:hover { background:#087f70; }
QLabel#searchCount { background:#eaf7f1; color:#087c68; border-radius:8px; padding:6px 10px; font-weight:600; }
QLabel#searchHint { color:#7b8d9c; font-size:12px; }
QFrame#searchPanel { background:white; border:1px solid #dfe9e4; border-radius:12px; }
QLabel#searchPanelTitle { color:#102a43; font-weight:700; font-size:14px; }
QTableWidget#searchResults { border:0; background:white; alternate-background-color:#f7fbf9; gridline-color:transparent; }
QTableWidget#searchResults::item { padding:7px; border-bottom:1px solid #edf2ef; }
QTableWidget#searchResults::item:selected { background:#dff1ea; color:#0b4f45; }
QTableWidget#searchResults QHeaderView::section { background:#f1f8f5; color:#526b60; border:0; border-bottom:1px solid #dfe9e4; padding:9px 8px; font-weight:600; }
QTextEdit#searchDetail { background:#fbfdfc; border:0; padding:10px; selection-background-color:#d7ede7; }
QSplitter::handle { background:transparent; height:10px; }
QTextEdit, QLineEdit { background: white; border: 1px solid #e0e7ef; border-radius: 8px; padding: 8px; selection-background-color: #d7ede7; }
QTextEdit#answerDetail { border: 0; padding: 0; background: white; font-size: 14px; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: #f0f4f7; width: 10px; margin: 2px 0; border: 0; border-radius: 5px; }
QScrollBar::handle:vertical { background: #c1d1dc; min-height: 30px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #91b7ae; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: 0; background: transparent; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.PlainText)
    return widget


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(10)
    return frame, layout


class ActivationDialog(QDialog):
    """Modal activation before the main window, or after a lease expires."""

    def __init__(self, manager: LicenseManager, parent=None, *, title: str = "软件激活"):
        super().__init__(parent)
        self.manager = manager
        self.result_state: LicenseState | None = None
        self._busy = False
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self.setWindowTitle(f"NewXKY · {title}")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setModal(True)
        self.resize(560, 430)
        self.setMinimumWidth(520)
        self._build_ui(title)

    def _build_ui(self, title: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(12)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(QIcon(str(ASSETS / "NewXKY.ico")).pixmap(54, 54))
        brand_row.addWidget(icon)
        brand = QVBoxLayout()
        brand.setSpacing(0)
        brand.addWidget(label("NewXKY", "brand"))
        brand.addWidget(label(f"区域答题助手 · V{__version__}", "muted"))
        brand_row.addLayout(brand)
        layout.addLayout(brand_row)

        layout.addWidget(label(title, "title"))
        intro = label(
            "请输入软件验证码。每个验证码只能激活一台电脑，激活后可使用 40 分钟；"
            "在这 40 分钟内可以关闭并重新打开软件，到期后该验证码永久失效。",
            "muted", True,
        )
        layout.addWidget(intro)

        warning_text = ""
        if not self.manager.server_url:
            warning_text = "当前程序未配置授权服务器地址，无法激活。请联系软件提供者获取正式安装包。"
        elif self.manager.expired or self.manager.last_error:
            warning_text = self.manager.last_error or "授权已到期，请输入新的验证码。"
        if warning_text:
            layout.addWidget(label(warning_text, "warning", True))

        layout.addWidget(label("验证码", "eyebrow"))
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self.code_input.setAlignment(Qt.AlignCenter)
        self.code_input.setMaxLength(24)
        self.code_input.setMinimumHeight(44)
        self.code_input.setFont(QFont("Consolas", 16))
        self.code_input.returnPressed.connect(self.start_activation)
        layout.addWidget(self.code_input)

        self.status_label = label("验证码格式：16 位字母或数字，横线可省略。", "dialogStatus", True)
        layout.addWidget(self.status_label)
        layout.addStretch()

        buttons = QHBoxLayout()
        self.cancel_button = QPushButton("退出软件")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        self.activate_button = QPushButton("激活软件")
        self.activate_button.setObjectName("primary")
        self.activate_button.setMinimumWidth(120)
        self.activate_button.clicked.connect(self.start_activation)
        buttons.addWidget(self.activate_button)
        layout.addLayout(buttons)
        self.code_input.setFocus()

    def start_activation(self):
        if self._busy:
            return
        code = self.code_input.text().strip()
        if not valid_code(code):
            self._set_status("验证码格式不正确，请按 XXXX-XXXX-XXXX-XXXX 输入。", warning=True)
            self.code_input.setFocus()
            return
        self._busy = True
        self.activate_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.code_input.setEnabled(False)
        self._set_status("正在连接授权服务器…", warning=False)

        def work(_):
            try:
                return True, self.manager.activate(code)
            except LicenseError as error:
                return False, error
            except Exception as error:  # keep the dialog usable if a worker fails
                return False, LicenseError("server_error", f"激活失败：{error}")

        job = Worker(work)
        job.signals.result.connect(self.activation_finished)
        job.signals.error.connect(self.activation_worker_failed)
        job.signals.finished.connect(self._activation_job_finished)
        self._pool.start(job)

    def activation_finished(self, result):
        ok, payload = result
        if ok:
            self.result_state = payload
            self._busy = False
            self.accept()
            return
        error = payload
        self._busy = False
        self._restore_inputs()
        self._set_status(getattr(error, "message", str(error)), warning=True)
        self.code_input.setFocus()
        self.code_input.selectAll()

    def activation_worker_failed(self, message):
        self._busy = False
        self._restore_inputs()
        self._set_status(f"激活失败：{message}", warning=True)

    def _activation_job_finished(self):
        # Result/error handlers already re-enable or close the dialog.
        if self._busy:
            self._busy = False
            self._restore_inputs()

    def _restore_inputs(self):
        self.activate_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self.code_input.setEnabled(True)

    def _set_status(self, text: str, *, warning: bool):
        self.status_label.setText(text)
        self.status_label.setObjectName("warning" if warning else "dialogStatus")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def reject(self):
        if self._busy:
            return
        super().reject()

    def closeEvent(self, event):
        if self._busy:
            event.ignore()
            return
        super().closeEvent(event)


class MainWindow(QMainWindow):
    """The complete V1.0.7 UI: bank, region OCR and license countdown."""

    def __init__(self, manager: LicenseManager, bank: Bank, *, data_dir: Path | None = None,
                 app_dir: Path | None = None):
        super().__init__()
        self.manager = manager
        self.bank = bank
        self.index = KnowledgeIndex(bank.questions)
        self.app_dir = Path(app_dir) if app_dir is not None else Path(__file__).resolve().parents[1]
        self.data_dir = Path(data_dir) if data_dir is not None else self.app_dir / "data"
        self.ocr = LocalOCR()
        self.tracker = FrameTracker()
        self.region: QRect | None = None
        self.running = False
        self._selecting = False
        self._closing = False
        self._jobs: set[Worker] = set()
        self._selectors: list[RegionSelector] = []
        self._last_capture = None
        self._last_issue = ""
        self._last_refresh = time.monotonic()
        self._license_refresh_busy = False
        self._offline = False
        self._license_locked = False
        self._ocr_warming = False
        self._ocr_ready = False
        self.search_window = None
        self.last_text = ""
        self._incomplete_question = None
        self._scroll_question = None
        self._scroll_options = {}
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.border = RegionBorder()
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.capture)
        self.license_timer = QTimer(self)
        self.license_timer.setInterval(1000)
        self.license_timer.timeout.connect(self.license_tick)

        self.setWindowTitle(f"NewXKY · 区域答题助手 V{__version__}")
        self.resize(1080, 760)
        self.setMinimumSize(920, 650)
        self._build_ui()
        self._load_settings()
        self.show_bank()
        self.license_tick()
        self.refresh_controls()
        self.license_timer.start()
        QTimer.singleShot(1200, self.start_license_refresh)
        if self.bank.questions:
            QTimer.singleShot(200, self.warm_ocr)

    # ---------- layout ----------

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(24, 22, 24, 22)
        outer.setSpacing(20)

        sidebar = QWidget()
        sidebar.setFixedWidth(300)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(14)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)
        brand_row.addWidget(label("NewXKY", "brand"))
        version = label(f"V{__version__}", "version")
        brand_row.addWidget(version, 0, Qt.AlignBottom)
        brand_row.addStretch()
        side.addLayout(brand_row)
        side.addWidget(label("本地题库 · 屏幕区域识别", "muted"))

        bank_card, bank_layout = card()
        bank_layout.addWidget(label("01 / 题库", "eyebrow"))
        self.bank_count = label("0", "bigCount")
        bank_layout.addWidget(self.bank_count)
        self.bank_summary = label("题库未加载", "muted", True)
        bank_layout.addWidget(self.bank_summary)
        self.bank_source = label("", "muted", True)
        bank_layout.addWidget(self.bank_source)
        bank_layout.addWidget(label("内置题库 · 无需导入", "version", True))
        side.addWidget(bank_card)

        region_card, region_layout = card()
        region_layout.addWidget(label("02 / 识别区域", "eyebrow"))
        self.region_info = label("尚未选择屏幕区域", "muted", True)
        region_layout.addWidget(self.region_info)
        self.select_button = QPushButton("框选 / 重选区域")
        self.select_button.clicked.connect(self.select_region)
        region_layout.addWidget(self.select_button)
        self.start_button = QPushButton("开始识别")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.toggle_monitor)
        region_layout.addWidget(self.start_button)
        region_layout.addWidget(label(
            "框选一道题的完整题干和全部选项；把本窗口移到区域外，题目变化后答案会自动更新。",
            "muted", True,
        ))
        side.addWidget(region_card)
        side.addStretch()
        side.addWidget(label(
            "截图、OCR 和题库匹配均在本机完成，不上传网络。\n"
            "答案仅供参考，请以完整选项内容核对。",
            "muted", True,
        ))
        outer.addWidget(sidebar)

        main = QVBoxLayout()
        main.setSpacing(14)
        header = QHBoxLayout()
        header.setSpacing(10)
        headings = QVBoxLayout()
        headings.setSpacing(2)
        headings.addWidget(label("区域答题助手", "title"))
        headings.addWidget(label("框选当前题目，显示本地题库中的答案", "muted"))
        header.addLayout(headings)
        header.addStretch()
        self.search_button = QPushButton("关键词搜题")
        self.search_button.setObjectName("searchAction")
        self.search_button.setShortcut("Ctrl+F")
        self.search_button.setToolTip("在 2026知识库 中搜索题干或选项（Ctrl+F）")
        self.search_button.setMinimumHeight(40)
        self.search_button.setMinimumWidth(132)
        self.search_button.clicked.connect(self.show_search)
        header.addWidget(self.search_button, 0, Qt.AlignTop)
        self.status = label("准备就绪", "status")
        self.status.setMinimumWidth(130)
        self.status.setAlignment(Qt.AlignCenter)
        header.addWidget(self.status, 0, Qt.AlignTop)
        main.addLayout(header)

        license_bar = QFrame()
        license_bar.setObjectName("licenseBar")
        license_layout = QHBoxLayout(license_bar)
        license_layout.setContentsMargins(14, 10, 14, 10)
        license_layout.setSpacing(10)
        self.license_label = label("尚未验证", "licenseBadge")
        license_layout.addWidget(self.license_label)
        self.license_hint = label(
            "软件授权已生效。有效期内可随时开关，倒计时不暂停。",
            "muted", True,
        )
        license_layout.addWidget(self.license_hint, 1)
        self.renew_button = QPushButton("输入新验证码")
        self.renew_button.setObjectName("quiet")
        self.renew_button.clicked.connect(self.renew_license)
        self.renew_button.hide()
        license_layout.addWidget(self.renew_button)
        info_button = QPushButton("软件说明")
        info_button.setObjectName("quiet")
        info_button.clicked.connect(self.show_software_info)
        license_layout.addWidget(info_button)
        main.addWidget(license_bar)

        answer_card, answer_layout = card()
        self.answer_title = label("当前题目 / 答案", "eyebrow")
        self.answer_title.setTextFormat(Qt.RichText)
        answer_layout.addWidget(self.answer_title)
        self.answer = label("—", "answer")
        answer_layout.addWidget(self.answer)
        self.message = label("请先框选屏幕中的题目区域，然后点击“开始识别”。", "muted", True)
        self.message.setTextFormat(Qt.RichText)
        answer_layout.addWidget(self.message)
        self.bank_fallback_button = QPushButton("仍按题库顺序显示")
        self.bank_fallback_button.setObjectName("fallback")
        self.bank_fallback_button.hide()
        self.bank_fallback_button.clicked.connect(self.show_bank_reference)
        answer_layout.addWidget(self.bank_fallback_button, 0, Qt.AlignLeft)
        self.answer_detail = QTextEdit()
        self.answer_detail.setObjectName("answerDetail")
        self.answer_detail.setReadOnly(True)
        self.answer_detail.setPlaceholderText("识别到完整题目后，这里显示正确选项的完整内容。")
        self.answer_detail.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        answer_layout.addWidget(self.answer_detail, 1)
        self.provenance = label("", "muted", True)
        self.provenance.setTextFormat(Qt.RichText)
        answer_layout.addWidget(self.provenance)
        main.addWidget(answer_card, 1)

        footer_card, footer_layout = card()
        footer_layout.setContentsMargins(18, 12, 18, 12)
        footer = QHBoxLayout()
        self.timing = label("题目文字变化后自动更新", "muted", True)
        footer.addWidget(self.timing, 1)
        footer.addWidget(label("答案窗口请放在识别区域外", "version"))
        footer_layout.addLayout(footer)
        main.addWidget(footer_card)
        outer.addLayout(main, 1)

    # ---------- bank / license ----------

    def show_bank(self):
        count = len(self.bank.questions)
        self.bank_count.setText(f"{count:,}")
        kinds = Counter(q.kind for q in self.bank.questions)
        self.bank_summary.setText(" · ".join(f"{kind} {number}" for kind, number in kinds.items()) or "题库未加载")
        self.bank_source.setText(f"来源：{SOURCE_LABEL}")
        if not count:
            self.message.setText("内置题库未加载，请重新解压完整的软件安装包。")

    def license_tick(self):
        if self._closing:
            return
        self.manager.reload_lease()
        remaining = self.manager.remaining_seconds()
        if remaining <= 0:
            self.license_expired(self.manager.last_error or "授权已到期，请输入新的验证码。")
            return
        if self._license_locked:
            return
        prefix = "离线续用" if self._offline else "已验证"
        self.license_label.setText(f"{prefix} · 剩余 {format_remaining(remaining)}")
        self.license_label.setStyleSheet(
            "background:#e8f5f1;color:#087c68;padding:7px 12px;border-radius:9px;font-weight:700;"
        )
        if not self._offline:
            self.license_hint.setText("软件授权已生效。有效期内可随时开关，倒计时不暂停。")
        self.manager.touch()
        if not self._license_refresh_busy and time.monotonic() - self._last_refresh >= 60:
            self.start_license_refresh()

    def start_license_refresh(self):
        if self._closing or self._license_locked or self._license_refresh_busy:
            return
        if not self.manager.server_url:
            return
        self._license_refresh_busy = True
        self._last_refresh = time.monotonic()

        def work(_):
            try:
                return True, self.manager.refresh()
            except LicenseError as error:
                return False, (error.code, error.message)
            except Exception as error:
                return False, ("server_error", f"授权检查失败：{error}")

        self.launch(work, self.license_refreshed, self.license_refresh_failed)

    def license_refreshed(self, result):
        self._license_refresh_busy = False
        ok, payload = result
        if ok:
            self._offline = False
            self.license_hint.setText("软件授权已生效。有效期内可随时开关，倒计时不暂停。")
            return
        code, message = payload
        if code in {"expired", "already_used", "invalid_code", "disabled", "machine_mismatch"}:
            self.license_expired(message)
        else:
            self._offline = True
            self.license_hint.setText("暂时无法连接授权服务器，剩余时间按本机记录继续计算。")

    def license_refresh_failed(self, message):
        self._license_refresh_busy = False
        self._offline = True
        self.license_hint.setText("暂时无法连接授权服务器，剩余时间按本机记录继续计算。")

    def license_expired(self, message: str):
        if self._license_locked:
            return
        self._license_locked = True
        self.manager.expired = True
        self.stop_monitor("授权已到期")
        if self.search_window is not None:
            self.search_window.close()
        self.license_label.setText("授权已到期")
        self.license_label.setStyleSheet(
            "background:#fff1ef;color:#b42318;padding:7px 12px;border-radius:9px;font-weight:700;"
        )
        self.license_hint.setText(message + "  请输入新的验证码继续使用。")
        self.renew_button.show()
        self.status.setText("授权已到期")
        self.refresh_controls()

    def renew_license(self):
        dialog = ActivationDialog(self.manager, self, title="输入新的验证码")
        if dialog.exec() != QDialog.Accepted:
            return
        self._license_locked = False
        self._offline = False
        self._last_refresh = time.monotonic()
        self.renew_button.hide()
        self.license_tick()
        self.refresh_controls()
        self.status.setText("授权已更新")

    def show_software_info(self):
        remaining = format_remaining(self.manager.remaining_seconds())
        status = "授权已到期" if self._license_locked else "离线续用" if self._offline else "已验证"
        text = (
            f"NewXKY 区域答题助手 V{__version__}\n\n"
            "功能：框选屏幕中的一道题，使用本机 OCR 识别题干和选项，"
            "在本地题库中匹配正确答案。程序不自动点击网页、不操作浏览器。\n\n"
            "授权：每个验证码仅能激活一台电脑，有效 40 分钟；"
            "同一台电脑在 40 分钟内可以关闭并重新打开。到期后验证码失效，需要新的验证码。\n\n"
            "隐私：截图、文字识别和题库匹配均在本机完成，不上传网络。"
            f"\n\n当前状态：{status}，剩余 {remaining}。"
        )
        QMessageBox.information(self, "软件说明", text)

    def warm_ocr(self):
        if self._ocr_ready or self._ocr_warming or self._closing:
            return
        self._ocr_warming = True

        def work(_):
            self.ocr.warmup()
            return True

        self.launch(work, self.ocr_warmed, self.ocr_warm_failed)

    def ocr_warmed(self, _):
        self._ocr_warming = False
        self._ocr_ready = True

    def ocr_warm_failed(self, message):
        self._ocr_warming = False
        self.timing.setText(f"OCR 预加载未完成，开始识别时会重试：{message}")

    # ---------- region and OCR ----------

    def refresh_controls(self):
        available = (
            not self._closing
            and not self._license_locked
            and self.manager.can_use
            and bool(self.bank.questions)
        )
        self.select_button.setEnabled(available and not self._selecting)
        self.start_button.setEnabled(available and self.region is not None)
        self.start_button.setText("暂停识别" if self.running else "开始识别")
        self.search_button.setEnabled(available)

    def show_search(self):
        if not self.manager.can_use:
            self.license_expired("授权已到期，请输入新的验证码。")
            return
        if self.search_window is None:
            self.search_window = SearchWindow(self.index, self)
        else:
            self.search_window.set_index(self.index)
        self.search_window.show()
        self.search_window.raise_()
        self.search_window.activateWindow()
        self.search_window.query.setFocus()

    def select_region(self):
        if self._selecting:
            return
        if not self.manager.can_use:
            self.license_expired("授权已到期，请输入新的验证码。")
            return
        self._selecting = True
        self.stop_monitor("正在选择区域")
        self.hide()
        self.border.hide()
        self._discard_selectors()
        QTimer.singleShot(250, self._open_selectors)

    def _discard_selectors(self):
        for selector in self._selectors:
            selector.close()
            selector.deleteLater()
        self._selectors.clear()

    def _open_selectors(self):
        if self._closing:
            self._selecting = False
            return
        self._discard_selectors()
        self._selectors = [RegionSelector(screen) for screen in QGuiApplication.screens()]
        if not self._selectors:
            self._selecting = False
            self.cancel_selection()
            return
        for selector in self._selectors:
            selector.selected.connect(self.region_selected)
            selector.cancelled.connect(self.cancel_selection)
            selector.show()
        self._selectors[0].activateWindow()

    def _close_selectors(self):
        self._discard_selectors()
        self._selecting = False
        if not self._closing:
            self.show()
            self.activateWindow()

    def region_selected(self, rect):
        if self._closing:
            return
        self.region = QRect(rect)
        self._selecting = False
        self._close_selectors()
        self.region_info.setText(
            f"已选择区域\n位置 {rect.x()}, {rect.y()} · 大小 {rect.width()} × {rect.height()}"
        )
        self._save_settings()
        self.update_border()
        self.status.setText("区域已选择")
        self.message.setText("把题目放进框选区域，将本窗口移到区域外，然后点击“开始识别”。")
        self.refresh_controls()

    def cancel_selection(self):
        if self._closing:
            return
        self._selecting = False
        self._close_selectors()
        self.update_border()
        self.status.setText("已取消框选")

    def update_border(self):
        if self.region is not None:
            self.border.set_region(self.region)
        self.border.setVisible(
            self.region is not None
            and not self._selecting
            and not self._selectors
            and not self._closing
            and not self._license_locked
            and self.manager.can_use
        )

    def toggle_monitor(self):
        if self.running:
            self.stop_monitor("已暂停")
            return
        if not self.manager.can_use:
            self.license_expired("授权已到期，请输入新的验证码。")
            return
        if self.region is None or not self.bank.questions:
            return
        self.running = True
        self.tracker.invalidate()
        self._last_issue = ""
        self.clear_answer("正在检测画面…")
        self.status.setText("识别中")
        self.timer.start()
        self.refresh_controls()
        self.update_border()
        self.capture()

    def clear_answer(self, message: str):
        self.answer_title.setText("当前题目 / 答案")
        self.answer.setText("—")
        self.answer.setStyleSheet("")
        self.answer_detail.clear()
        self.provenance.clear()
        self.bank_fallback_button.hide()
        self._incomplete_question = None
        self._scroll_question = None
        self._scroll_options = {}
        self.message.setText(emphasize_bank_order(message))

    def stop_monitor(self, reason: str = "已暂停"):
        self.running = False
        self.timer.stop()
        self.tracker.invalidate()
        self.clear_answer(reason)
        self.status.setText(reason)
        self.refresh_controls()
        self.update_border()

    def capture(self):
        if not self.running or self.region is None or self._closing:
            return
        if not self.manager.can_use:
            self.license_expired("授权已到期，请输入新的验证码。")
            return
        issue = ""
        screen = QGuiApplication.screenAt(self.region.center())
        if screen is None or not screen.geometry().contains(self.region):
            issue = "显示器布局已变化，请重新框选单块显示器内的区域"
        elif self.isVisible() and not self.isMinimized() and self.frameGeometry().intersects(self.region):
            issue = "答案窗口遮挡识别区域，请把本窗口移到区域外"
        if issue:
            if issue != self._last_issue:
                self.tracker.invalidate()
                self.clear_answer(issue)
                self._last_issue = issue
                self.status.setText("等待调整区域")
            return
        self._last_issue = ""
        origin = screen.geometry().topLeft()
        pixmap = screen.grabWindow(
            0,
            self.region.x() - origin.x(),
            self.region.y() - origin.y(),
            self.region.width(),
            self.region.height(),
        )
        if pixmap.isNull():
            self.stop_monitor("截屏失败，请重新选择可见区域")
            return
        image = pixmap.toImage()
        from numpy import frombuffer, uint8
        gray = image.convertToFormat(QImage.Format_Grayscale8)
        pixels = frombuffer(gray.constBits(), dtype=uint8).reshape(
            gray.height(), gray.bytesPerLine()
        )[:, :gray.width()]
        now = time.monotonic()
        if self.tracker.observe_image(pixels, now):
            self.clear_answer("题目文字已变化，正在识别新题目…")
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
            match = index.lookup(text)
            # After the user scrolls, the stem may have left the region while
            # the lower options became visible. Recombine the cached stem and
            # already-seen options with this frame before falling back.
            if self._scroll_question is not None and match.status in (
                    "incomplete", "missing", "reference", "unverified"):
                merged = self._merge_scrolled(text, index)
                if merged is not None:
                    text, match = merged
            return text, match, time.monotonic() - started

        self.launch(
            recognize,
            lambda result: self.recognized(revision, result),
            lambda error: self.recognition_failed(revision, error),
        )

    def _merge_scrolled(self, text, index):
        question = self._scroll_question
        if question is None:
            return None
        stem_text, current = screen_parts(text)
        if not current:
            return None
        current_stem = normalized(clean_stem(stem_text))
        bank_stem = normalized(question.stem)
        if len(current_stem) >= 8:
            similar = (
                current_stem in bank_stem
                or bank_stem in current_stem
                or SequenceMatcher(None, current_stem, bank_stem, autojunk=False).ratio() >= .55
            )
            if not similar:
                return None
        merged = dict(self._scroll_options)
        changed = False
        for label, value in current.items():
            if value and len(value) > len(merged.get(label, "")):
                merged[label] = value
                changed = True
        if not changed and len(merged) < len(question.options):
            return None
        synthetic = question.stem + "\n" + "\n".join(
            f"{label}. {value}" for label, value in sorted(merged.items())
        )
        alternate = index.lookup(synthetic)
        if alternate.status in ("matched", "incomplete", "unverified", "reference"):
            return synthetic, alternate
        return None

    def recognized(self, revision, result):
        if not self.tracker.finish(revision) or not self.running:
            return
        text, match, elapsed = result
        self.last_text = text
        self.timing.setText(f"最近识别 {elapsed:.1f} 秒 · {datetime.now():%H:%M:%S}")
        self.clear_answer(match.message)
        self.status.setText({
            "matched": "已核对网页选项",
            "reference": "已找到题库答案",
            "candidate": "相似题待核对",
            "unverified": "网页选项待核对",
            "incomplete": "等待完整选项",
            "ambiguous": "匹配不唯一",
        }.get(match.status, "未找到答案"))
        if match.status == "incomplete" and match.question:
            question = match.question
            visible = "\n".join(
                f"{letter}. {value}" for letter, value in (match.options or {}).items()
            ) or "未识别到选项文字"
            self._incomplete_question = question
            self._scroll_question = question
            self._scroll_options = dict(match.options or {})
            self.answer_title.setText(emphasize_bank_order(
                "选项未显示完整 / 请向下滚动", warning=True
            ))
            self.answer.setText("待核对")
            self.answer.setStyleSheet("color:#b42318;font-size:34px;")
            self.message.setText(emphasize_bank_order(match.message, warning=True))
            self.answer_detail.setPlainText(
                f"已匹配题库第 {question.number} 题：\n{question.stem}\n\n"
                f"当前画面识别到的选项：\n{visible}\n\n"
                "请向下滚动考试页面，直到全部选项进入框选区域。"
            )
            self.provenance.setText(emphasize_bank_order(
                f"{SOURCE_LABEL} · {question.kind} · 第 {question.number} 题 · "
                f"第 {', '.join(map(str, question.pages))} 页\n"
                "尚未按题库顺序给答案；需要时可用下方按钮强制参考。",
                warning=True,
            ))
            self.bank_fallback_button.show()
        elif match.status in ("matched", "reference") and match.question:
            question = match.question
            options = match.options or question.options
            answers = match.answers or question.answers
            self.answer.setText(" / ".join(answers))
            self.answer_detail.setPlainText(
                f"{question.stem}\n\n" + "\n".join(f"{letter}. {options[letter]}" for letter in answers)
            )
            scope = (
                "答案字母已按当前画面选项顺序对应。"
                if match.status == "matched"
                else "题库顺序：网页可能调整选项顺序，请按选项内容核对。"
            )
            self.answer_title.setText(emphasize_bank_order(
                "当前题目 / 网页答案" if match.status == "matched"
                else "当前题目 / 题库答案（题库顺序）"
            ))
            if match.status == "reference":
                self.answer.setStyleSheet("color:#c62828;font-size:52px;")
                self.message.setText(emphasize_bank_order(match.message, warning=True))
            self.provenance.setText(emphasize_bank_order(
                f"{SOURCE_LABEL} · {question.kind} · 第 {question.number} 题 · "
                f"第 {', '.join(map(str, question.pages))} 页\n{scope}",
                warning=match.status == "reference",
            ))
        elif match.status in ("candidate", "unverified") and match.question:
            question = match.question
            reference = match.reference
            answers = reference.answers if reference else question.answers
            options = reference.options if reference else question.options
            screen_order = reference is not None and reference.screen_order
            title = "相似题参考" if match.status == "candidate" else "选项待核对"
            scope = "参考网页顺序" if screen_order else "题库顺序"
            self.answer_title.setText(emphasize_bank_order(f"{title} / {scope}", warning=True))
            self.answer.setText("参考 " + " / ".join(answers))
            self.answer.setStyleSheet("color:#c62828;font-size:36px;")
            self.message.setText(emphasize_bank_order(match.message, warning=True))
            correct = "\n".join(f"{letter}. {options[letter]}" for letter in answers)
            stem_title = "相似题题干" if match.status == "candidate" else "题库原题"
            self.answer_detail.setPlainText(f"{stem_title}：{question.stem}\n\n参考答案：\n{correct}")
            caution = (
                "选项文字尚未完全核对，请按完整内容确认。"
                if match.status == "unverified"
                else f"文字相似度 {match.score:.0%} · 请核对题干差异。"
            )
            self.provenance.setText(emphasize_bank_order(
                f"{SOURCE_LABEL} · {question.kind} · 第 {question.number} 题 · "
                f"第 {', '.join(map(str, question.pages))} 页\n"
                f"{scope} · 仅供参考 · {caution}", warning=True
            ))

    def show_bank_reference(self):
        """User explicitly chooses the bank-order fallback after a scroll prompt."""
        question = self._incomplete_question
        if question is None:
            return
        self.stop_monitor("已显示题库顺序参考")
        self.answer_title.setText(emphasize_bank_order("题库答案（题库顺序）", warning=True))
        self.answer.setText(" / ".join(question.answers))
        self.answer.setStyleSheet("color:#c62828;font-size:52px;")
        self.answer_detail.setPlainText(
            f"{question.stem}\n\n"
            + "\n".join(f"{letter}. {value}" for letter, value in question.options.items())
        )
        self.message.setText(emphasize_bank_order(
            "未显示完整选项，以下答案按题库顺序显示；请按选项内容核对网页。",
            warning=True,
        ))
        self.provenance.setText(emphasize_bank_order(
            f"{SOURCE_LABEL} · {question.kind} · 第 {question.number} 题 · "
            f"第 {', '.join(map(str, question.pages))} 页\n"
            "题库顺序参考 · 不是按当前画面选项对应的答案",
            warning=True,
        ))
        self.status.setText("题库顺序参考")
        self._incomplete_question = None
        self.bank_fallback_button.hide()

    def recognition_failed(self, revision, message):
        if not self.tracker.finish(revision) or not self.running:
            return
        self.stop_monitor("识别失败，可重试")
        self.message.setText(emphasize_bank_order(message))
        self.timing.setText(message)

    # ---------- background work ----------

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

    # ---------- settings / lifecycle ----------

    def _load_settings(self):
        try:
            data = json.loads((self.data_dir / "settings.json").read_text(encoding="utf-8"))
            rect = QRect(*data["region"]) if data.get("region") else QRect()
            if rect.width() >= 120 and rect.height() >= 80 and any(
                screen.geometry().contains(rect) for screen in QGuiApplication.screens()
            ):
                self.region = rect
                self.region_info.setText(
                    f"已恢复上次区域\n{rect.x()}, {rect.y()} · {rect.width()} × {rect.height()}"
                )
                self.update_border()
        except (OSError, ValueError, TypeError, KeyError):
            pass

    def _save_settings(self):
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            path = self.data_dir / "settings.json"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({"region": self.region.getRect() if self.region is not None else None}),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError:
            pass

    def closeEvent(self, event):
        self._closing = True
        self._selecting = False
        self.timer.stop()
        self.license_timer.stop()
        self.running = False
        self.tracker.invalidate()
        self._discard_selectors()
        self.border.hide()
        self.border.close()
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
    app.setApplicationVersion(__version__)
    app.setOrganizationName("NewXKY")
    app.setWindowIcon(QIcon(str(ASSETS / "NewXKY.ico")))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE)

    root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    data = Path(data_dir) if data_dir else root / "data"
    try:
        data.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        QMessageBox.critical(None, "NewXKY", f"无法创建数据目录：\n{data}\n\n{error}")
        return 1

    bank, notes = load_startup_bank(root)
    if not bank.questions:
        QMessageBox.critical(None, "NewXKY · 题库缺失", "\n".join(notes) or "内置题库未加载。")
        return 1

    manager = LicenseManager(data)
    if not manager.restore():
        dialog = ActivationDialog(manager)
        if dialog.exec() != QDialog.Accepted:
            return 0

    window = MainWindow(manager, bank, data_dir=data, app_dir=root)
    if hide_console and sys.platform == "win32":
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
