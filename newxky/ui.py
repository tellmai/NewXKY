import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QFont, QGuiApplication, QIcon, QImage, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget, QHeaderView, QListView, QDialog, QLineEdit,
    QListWidget, QListWidgetItem, QAbstractItemView, QMenu,
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
from .auto_controller import AutoController
from .browser_bridge import BrowserBridge
from .browsers import browser_path_key, discover_browsers
from .identities import ExamQueue, SiteConfig, load_identities
from .personnel_controller import PersonnelWorker
from .personnel_results import PersonnelResults


STYLE = """
QMainWindow, QWidget#root { background: #f3f6fa; color: #182c43; }
QWidget { font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 13px; color: #182c43; }
QFrame#card { background: white; border: 1px solid #e1e7ee; border-radius: 14px; }
QFrame#workspace { background: white; border: 1px solid #d8e3ed; border-radius: 14px; }
QFrame#rosterPanel { background: #f7fafc; border: 1px solid #e1e8ef; border-radius: 10px; }
QLabel#resultSummary { color: #087f70; background: #edf7f3; border-radius: 6px; padding: 6px 8px; font-size: 12px; }
QPushButton#compact { padding: 6px 10px; font-size: 12px; }
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
QTextEdit, QTableWidget, QLineEdit, QListWidget { background: white; border: 1px solid #e0e7ef; border-radius: 8px; padding: 8px; selection-background-color: #d7ede7; }
QListWidget::item { padding: 7px 8px; border-radius: 5px; }
QListWidget::item:selected { background: #d7ede7; color: #075e50; }
QListWidget::item:hover { background: #edf8f3; }
QTableWidget::item:selected { background: #d7ede7; color: #182c43; }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 10px 14px; color: #6b7e90; }
QTabBar::tab:selected { color: #087f70; border-bottom: 2px solid #087f70; }
QTabWidget#workspaceTabs::pane { border: 0; background: white; margin-top: 10px; }
QTabBar#workspaceTabBar::tab { color: #63778c; background: #f3f6f9; border: 1px solid #e7edf3; border-radius: 7px; padding: 8px 10px; margin-right: 4px; }
QTabBar#workspaceTabBar::tab:hover { color: #087f70; background: #edf8f3; border-color: #cbe5dc; }
QTabBar#workspaceTabBar::tab:selected { color: #076d5e; background: #e4f3ed; border: 1px solid #abd6c7; font-weight: 600; }
QTabBar#workspaceTabBar QToolButton { background: #f3f6f9; border: 0; width: 22px; }
QScrollArea#rosterArea, QWidget#rosterContent { background: white; border: 0; }
QProgressBar { border: 0; background: #e4ebeF; border-radius: 4px; height: 8px; }
QProgressBar::chunk { background: #12ad90; border-radius: 4px; }
QComboBox { border: 1px solid #d8e1ea; padding: 6px; border-radius: 6px; background: white; }
QComboBox#captureInterval, QComboBox#autoMode, QComboBox#browserChoice { background: #f7fcfa; color: #126658; border: 1px solid #bfdbd2; border-radius: 8px; padding: 9px 34px 9px 12px; font-weight: 600; }
QComboBox#captureInterval:hover, QComboBox#autoMode:hover, QComboBox#browserChoice:hover { background: #edf8f3; border-color: #69b8a5; }
QComboBox#captureInterval:focus, QComboBox#captureInterval:on, QComboBox#autoMode:focus, QComboBox#autoMode:on, QComboBox#browserChoice:focus, QComboBox#browserChoice:on { background: white; border-color: #0b8c77; }
QComboBox#captureInterval::drop-down, QComboBox#autoMode::drop-down, QComboBox#browserChoice::drop-down { width: 30px; border: 0; subcontrol-origin: padding; subcontrol-position: top right; }
QComboBox#captureInterval::down-arrow, QComboBox#autoMode::down-arrow, QComboBox#browserChoice::down-arrow { image: url('__CAPTURE_CHEVRON__'); width: 14px; height: 14px; }
QComboBox#captureInterval QAbstractItemView, QComboBox#autoMode QAbstractItemView, QComboBox#browserChoice QAbstractItemView { background: white; color: #182c43; border: 1px solid #bfdbd2; border-radius: 8px; padding: 5px; outline: 0; selection-background-color: #dcefe7; selection-color: #075e50; }
QComboBox#captureInterval QAbstractItemView::item, QComboBox#autoMode QAbstractItemView::item, QComboBox#browserChoice QAbstractItemView::item { min-height: 30px; padding: 6px 10px; border-radius: 5px; }
QComboBox#captureInterval QAbstractItemView::item:selected, QComboBox#autoMode QAbstractItemView::item:selected, QComboBox#browserChoice QAbstractItemView::item:selected { background: #dcefe7; color: #075e50; }
QComboBox:disabled { color: #96aaa4; background: #edf2f0; border-color: #dce6e1; }
QComboBox QAbstractItemView::item:disabled { color: #9da9b4; }
QHeaderView::section { background: #f4f7fa; border: 0; padding: 8px; }
QSplitter::handle { background: transparent; height: 10px; }
QScrollBar:vertical { background: #f0f4f7; width: 10px; margin: 2px 0; border: 0; border-radius: 5px; }
QScrollBar::handle:vertical { background: #c1d1dc; min-height: 30px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #91b7ae; }
QScrollBar::handle:vertical:pressed { background: #5c9d8e; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: 0; background: transparent; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: #f0f4f7; height: 10px; margin: 0 2px; border: 0; border-radius: 5px; }
QScrollBar::handle:horizontal { background: #c1d1dc; min-width: 30px; border-radius: 5px; }
QScrollBar::handle:horizontal:hover { background: #91b7ae; }
QScrollBar::handle:horizontal:pressed { background: #5c9d8e; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; border: 0; background: transparent; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QScrollBar::up-arrow, QScrollBar::down-arrow, QScrollBar::left-arrow, QScrollBar::right-arrow { image: none; border: 0; width: 0; height: 0; }
QMenu { background: white; border: 1px solid #d8e3ed; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 8px 16px; border-radius: 5px; }
QMenu::item:selected { background: #e4f3ed; color: #076d5e; }
QMenu::item:disabled { color: #a3afbb; }
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
        self.people = ExamQueue()
        self.candidates = []
        self.personnel_worker = None
        self.personnel_importing = False
        self._browser_handles = []
        self._auto_person_position = None
        self.results_store = None
        self.results_directory = None
        self._pending_result_exports = {}
        self._result_export_busy = False
        self._browser_connection_message = "网页直连需先连接答题标签页"
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.border = RegionBorder()
        self.floating = FloatingAnswer()
        self.floating.expand.connect(self.expand_main)
        self.floating.toggle.connect(self.toggle_monitor)
        self.floating.auto_toggle.connect(self.toggle_auto)
        self.browser_bridge=BrowserBridge(self)
        self.browser_bridge.changed.connect(self.browser_connection_changed)
        self.auto = AutoController(self.ocr,self,bridge=self.browser_bridge)
        self.auto.status.connect(self.auto_status)
        self.auto.observation.connect(self.auto_observed)
        self.auto.finished.connect(self.auto_finished)
        self.auto.idle.connect(self._auto_idle)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.capture)
        self.setWindowTitle("NewXKY · 区域答题助手")
        self.resize(1240, 940)
        self.setMinimumSize(1060, 800)
        self._build_ui()
        self._read_settings()
        self.refresh_controls()
        QTimer.singleShot(0, self.restore_bank)

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(20)
        sidebar = QVBoxLayout()
        sidebar.setContentsMargins(0, 0, 0, 0)
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
        self.auto_button = QPushButton("启动自动答题")
        self.auto_button.setObjectName("primary")
        self.auto_button.clicked.connect(self.toggle_auto)
        self.auto_mode=QComboBox()
        self.auto_mode.setObjectName("autoMode")
        self.auto_mode.setAccessibleName("自动答题方式")
        self.auto_mode.setMinimumWidth(220)
        self.auto_mode.setView(QListView(self.auto_mode))
        self.auto_mode.view().setSpacing(3)
        self.auto_mode.addItem("网页直连（不占鼠标）","dom")
        self.auto_mode.addItem("屏幕区域（鼠标兼容）","screen")
        self.auto_mode.setCurrentIndex(self.auto_mode.findData("screen"))
        self.auto_mode.currentIndexChanged.connect(self.refresh_controls)
        self.browser_connect_button=QPushButton("连接浏览器…")
        self.browser_connect_button.clicked.connect(self.connect_browser)
        self.browser_status=label("网页直连需先连接答题标签页", "muted",True)
        region_layout.addWidget(label("从当前题往后答；暂停后可继续。\n网页直连无需框选、不占鼠标。\nEsc 暂停；未完成题目不交卷。", "muted", True))
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
        people_card, people_layout = card()
        people_layout.setContentsMargins(18, 14, 18, 14)
        people_header = QHBoxLayout()
        people_header.addWidget(label("人员考试 / 逐人加载", "eyebrow"))
        people_header.addStretch()
        self.people_import_button = QPushButton("导入人员信息…")
        self.people_import_button.clicked.connect(self.import_people)
        people_header.addWidget(self.people_import_button)
        people_layout.addLayout(people_header)
        browser_row = QHBoxLayout()
        browser_row.addWidget(label("考试浏览器"))
        self.browser_combo = QComboBox()
        self.browser_combo.setObjectName("browserChoice")
        self.browser_combo.setAccessibleName("选择考试浏览器")
        self.browser_combo.setMinimumWidth(220)
        self.browser_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.browser_combo.setView(QListView(self.browser_combo))
        self.browser_combo.view().setSpacing(3)
        self.browser_combo.setToolTip("下次加载人员时使用此浏览器；此前打开的考试窗口会保留")
        self.browser_refresh = QPushButton("刷新列表")
        self.browser_refresh.clicked.connect(self.refresh_browsers)
        self.browser_browse = QPushButton("浏览…")
        self.browser_browse.clicked.connect(self.browse_browser)
        browser_row.addWidget(self.browser_combo, 1)
        browser_row.addWidget(self.browser_refresh)
        browser_row.addWidget(self.browser_browse)
        people_layout.addLayout(browser_row)
        person_row = QHBoxLayout()
        self.person_info = label("尚未导入人员信息", "muted", True)
        person_row.addWidget(self.person_info, 1)
        self.person_button = QPushButton("加载人员信息")
        self.person_button.setObjectName("primary")
        self.person_button.clicked.connect(self.load_person)
        person_row.addWidget(self.person_button)
        self.person_cancel = QPushButton("停止加载")
        self.person_cancel.clicked.connect(self.cancel_person_loading)
        self.person_cancel.hide()
        person_row.addWidget(self.person_cancel)
        self.person_skip = QPushButton("跳过当前人员")
        self.person_skip.clicked.connect(self.skip_person)
        person_row.addWidget(self.person_skip)
        people_layout.addLayout(person_row)
        self.person_hint = label("导入备选人员 → 添加待考 → 加载至登录主页 → 手动进入考试并验证 → 框选并启动自动答题", "muted", True)
        people_layout.addWidget(self.person_hint)
        main.addWidget(people_card)
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
        auto_actions=QHBoxLayout()
        auto_actions.addWidget(label("自动答题"))
        auto_actions.addWidget(self.auto_mode)
        auto_actions.addWidget(self.browser_connect_button)
        auto_actions.addWidget(self.auto_button)
        auto_actions.addStretch()
        main.addLayout(auto_actions)
        self.workspace, workspace_layout = card()
        self.workspace.setObjectName("workspace")
        workspace_layout.setContentsMargins(16, 14, 16, 16)
        workspace_layout.setSpacing(12)
        workspace_header = QHBoxLayout()
        workspace_header.setSpacing(10)
        self.browser_status.setMaximumHeight(44)
        workspace_header.addWidget(self.browser_status, 1)
        self.results_summary = label("人员结果尚未生成", "resultSummary")
        workspace_header.addWidget(self.results_summary)
        self.results_retry = QPushButton("重新保存")
        self.results_retry.setObjectName("compact")
        self.results_retry.clicked.connect(self.save_people_results)
        self.results_retry.hide()
        workspace_header.addWidget(self.results_retry)
        self.results_open = QPushButton("结果文件夹")
        self.results_open.setObjectName("compact")
        self.results_open.clicked.connect(self.open_people_results)
        self.results_open.setEnabled(False)
        workspace_header.addWidget(self.results_open)
        workspace_layout.addLayout(workspace_header)
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
        self.answer_scroll = scroll
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(scroll)
        tabs = QTabWidget()
        tabs.setObjectName("workspaceTabs")
        tabs.setDocumentMode(True)
        tabs.tabBar().setObjectName("workspaceTabBar")
        tabs.tabBar().setDrawBase(False)
        self.detail_tabs = tabs
        self.roster_widget = QScrollArea()
        self.roster_widget.setObjectName("rosterArea")
        self.roster_widget.setFrameShape(QFrame.NoFrame)
        self.roster_widget.setWidgetResizable(True)
        roster_content = QWidget()
        roster_content.setObjectName("rosterContent")
        roster_content.setMinimumHeight(300)
        self.roster_widget.setWidget(roster_content)
        roster_layout = QHBoxLayout(roster_content)
        roster_layout.setContentsMargins(0, 0, 0, 0)
        roster_layout.setSpacing(14)
        self.pool_panel = QFrame()
        self.pool_panel.setObjectName("rosterPanel")
        pool_layout = QVBoxLayout(self.pool_panel)
        pool_layout.setContentsMargins(12, 12, 12, 12)
        pool_layout.setSpacing(10)
        self.pool_title = label("备选人员 · 0 人", "eyebrow")
        pool_layout.addWidget(self.pool_title)
        self.people_search = QLineEdit()
        self.people_search.setPlaceholderText("输入姓名搜索备选人员")
        self.people_search.setClearButtonEnabled(True)
        self.people_search.textChanged.connect(self.refresh_candidate_pool)
        pool_layout.addWidget(self.people_search)
        self.candidate_list = QListWidget()
        self.candidate_list.setAccessibleName("备选人员")
        self.candidate_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.candidate_list.setAlternatingRowColors(True)
        self.candidate_list.setMinimumHeight(120)
        self.candidate_list.itemDoubleClicked.connect(lambda _: self.add_waiting_people())
        pool_layout.addWidget(self.candidate_list, 1)
        self.add_people_button = QPushButton("添加选中人员至待考 →")
        self.add_people_button.clicked.connect(self.add_waiting_people)
        pool_layout.addWidget(self.add_people_button)
        roster_layout.addWidget(self.pool_panel, 1)
        self.waiting_panel = QFrame()
        self.waiting_panel.setObjectName("rosterPanel")
        waiting_layout = QVBoxLayout(self.waiting_panel)
        waiting_layout.setContentsMargins(12, 12, 12, 12)
        waiting_layout.setSpacing(10)
        self.waiting_title = label("待考人员 · 0 人", "eyebrow")
        waiting_layout.addWidget(self.waiting_title)
        waiting_layout.addWidget(label("鼠标拖拽排序，始终先进行最上方就绪人员的考试", "muted", True))
        self.waiting_list = QListWidget()
        self.waiting_list.setAccessibleName("待考人员，拖拽可排序")
        self.waiting_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.waiting_list.setDefaultDropAction(Qt.MoveAction)
        self.waiting_list.setDragDropOverwriteMode(False)
        self.waiting_list.setDropIndicatorShown(True)
        self.waiting_list.setAlternatingRowColors(True)
        self.waiting_list.setMinimumHeight(120)
        self.waiting_list.model().rowsMoved.connect(self.waiting_people_moved)
        waiting_layout.addWidget(self.waiting_list, 1)
        self.remove_people_button = QPushButton("移回备选人员")
        self.remove_people_button.clicked.connect(self.remove_waiting_people)
        waiting_layout.addWidget(self.remove_people_button)
        roster_layout.addWidget(self.waiting_panel, 1)
        tabs.addTab(self.roster_widget, "备选 / 待考人员")
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
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.auto_report = QTextEdit()
        self.auto_report.setReadOnly(True)
        self.auto_report.setPlaceholderText("自动答题进度和未完成题目将显示在这里。")
        tabs.addTab(self.auto_report,"自动答题记录")
        self.people_table = QTableWidget(0, 5)
        self.people_table.setHorizontalHeaderLabels(["姓名", "所在区县", "身份证号", "状态", "结果 / 说明"])
        self.people_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.people_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.people_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.people_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.people_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.people_table.customContextMenuRequested.connect(self.people_progress_menu)
        self.people_table.setToolTip("右键可将选中的人员添加回备选人员，并同步更新两份人员结果 Excel")
        tabs.insertTab(1, self.people_table, "人员考试进度")
        tabs.addTab(self.bank_table, "已导入题库")
        tabs.addTab(self.logs, "导入 / 运行记录")
        splitter.addWidget(tabs)
        splitter.setSizes([360, 300])
        tabs.currentChanged.connect(self.detail_tab_changed)
        self.detail_tab_changed()
        workspace_layout.addWidget(splitter, 1)
        main.addWidget(self.workspace, 1)
        outer.addLayout(main, 1)
        self.refresh_browsers()
        self.browser_combo.currentIndexChanged.connect(self._save_settings)
        self.refresh_people()
        self.refresh_controls()

    def detail_tab_changed(self, *args):
        self.answer_scroll.setVisible(self.detail_tabs.currentWidget() not in (self.roster_widget, self.people_table))

    def refresh_browsers(self, selected=None):
        path = selected if isinstance(selected, str) else (self.browser_combo.currentData() or "")
        previous = self.browser_combo.blockSignals(True)
        try:
            self.browser_combo.clear()
            self.browser_combo.addItem("自动选择（优先 Chrome / Edge）", "")
            for choice in discover_browsers(include_unsupported=True):
                index = self.browser_combo.count()
                caption = choice.name + ("（不支持自动登录）" if not choice.compatible else "")
                self.browser_combo.addItem(caption, choice.path)
                self.browser_combo.setItemData(index, choice.path, Qt.ToolTipRole)
                self.browser_combo.model().item(index).setEnabled(choice.compatible)
            index = next((i for i in range(self.browser_combo.count())
                          if browser_path_key(self.browser_combo.itemData(i)) == browser_path_key(path)), -1)
            if index < 0:
                suffix = "" if Path(path).is_file() else "（文件不存在）"
                self.browser_combo.addItem("自定义浏览器" + suffix, path)
                index = self.browser_combo.count() - 1
                self.browser_combo.setItemData(index, path, Qt.ToolTipRole)
            self.browser_combo.setCurrentIndex(index)
        finally:
            self.browser_combo.blockSignals(previous)

    def browse_browser(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择考试浏览器程序", "", "浏览器程序 (*.exe)")
        if path:
            self.refresh_browsers(path)
            self._save_settings()

    def import_people(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入人员信息", "", "Excel 人员信息 (*.xlsx)")
        if path:
            self.import_people_path(path)

    def import_people_path(self, path):
        if self.personnel_worker or self.personnel_importing or self.auto.active or self._closing:
            return
        self.personnel_importing = True
        self.refresh_controls()
        self.launch(lambda _: load_identities(path), self.people_imported, self.people_import_failed)

    def people_imported(self, result):
        self.personnel_importing = False
        if not result.candidates:
            self.people_import_failed("未发现有效人员。" + "；".join(result.issues[:5]))
            return
        self.stop_monitor("已导入人员信息")
        self.auto.session = None
        self._auto_person_position = None
        self.candidates = result.candidates
        self.people = ExamQueue()
        self.results_store = PersonnelResults(self.data_dir, self.candidates)
        self.results_directory = None
        self.results_summary.setText("正在保存人员结果…")
        self.results_open.setEnabled(False)
        self.results_retry.hide()
        self.save_people_results()
        self.people_search.clear()
        self.detail_tabs.setCurrentWidget(self.roster_widget)
        self.person_hint.setText(f"已导入 {len(result.candidates)} 位备选人员；请按姓名搜索并添加到待考列表，拖拽调整考试顺序。")
        self.log(f"人员导入完成：{len(result.candidates)} 人，跳过 {len(result.issues)} 条异常或重复记录。")
        for issue in result.issues:
            self.log(issue)
        self.refresh_people()
        self.refresh_controls()

    def people_import_failed(self, message):
        self.personnel_importing = False
        self.log(f"人员导入失败：{message}")
        self.person_hint.setText(message)
        self.refresh_controls()

    def refresh_people(self):
        self.people_table.setRowCount(len(self.people.records))
        for row, record in enumerate(self.people.records):
            c = record.candidate
            for column, value in enumerate((c.name, c.district, c.masked_id, record.status, record.detail)):
                self.people_table.setItem(row, column, QTableWidgetItem(value))
        self.refresh_candidate_pool()
        previous = self.waiting_list.currentItem()
        selected_row = previous.data(Qt.UserRole) if previous else None
        self.waiting_list.clear()
        for record in self.people.pending:
            c = record.candidate
            item = QListWidgetItem(f"{c.name} · {c.district} · {record.status}")
            item.setData(Qt.UserRole, c.row)
            item.setToolTip("拖动调整顺序；软件始终从最上方的就绪人员开始")
            if record.status not in {"待考试", "加载失败"}:
                item.setFlags(item.flags() & ~Qt.ItemIsDragEnabled)
            self.waiting_list.addItem(item)
            if c.row == selected_row:
                self.waiting_list.setCurrentItem(item)
        self.waiting_title.setText(f"待考人员 · {len(self.people.pending)} 人")
        current = self.people.current
        if current:
            c = current.candidate
            self.person_info.setText(f"当前首位 · {c.name} · {current.status} / 待考 {len(self.people.pending)} 人")
        else:
            self.person_info.setText("待考列表为空，请从备选人员添加" if self.candidates else "尚未导入人员信息")

    def refresh_candidate_pool(self):
        queued = {r.candidate.row for r in self.people.records}
        available = [c for c in self.candidates if c.row not in queued]
        query = self.people_search.text().strip().casefold()
        selected = {item.data(Qt.UserRole) for item in self.candidate_list.selectedItems()}
        self.candidate_list.clear()
        for candidate in available:
            if query and query not in candidate.name.casefold():
                continue
            item = QListWidgetItem(f"{candidate.name} · {candidate.district}")
            item.setData(Qt.UserRole, candidate.row)
            item.setToolTip(candidate.masked_id)
            self.candidate_list.addItem(item)
            item.setSelected(candidate.row in selected)
        self.pool_title.setText(f"备选人员 · {len(available)} 人 / 搜索结果 {self.candidate_list.count()} 人")

    def add_waiting_people(self):
        if self.personnel_worker or self.personnel_importing or self.auto.active or self._closing:
            return
        rows = {item.data(Qt.UserRole) for item in self.candidate_list.selectedItems()}
        self.people.add(c for c in self.candidates if c.row in rows)
        if rows:
            self.person_hint.setText("已添加到待考列表；可拖拽排序，再点击进行最上方人员的考试。")
        self.refresh_people()
        self.refresh_controls()

    def remove_waiting_people(self):
        if self.personnel_worker or self.auto.active or self.auto.busy or self._closing:
            return
        rows = [item.data(Qt.UserRole) for item in self.waiting_list.selectedItems()]
        self.people.remove(rows)
        self.refresh_people()
        self.refresh_controls()

    def waiting_people_moved(self, *args):
        rows = [self.waiting_list.item(i).data(Qt.UserRole) for i in range(self.waiting_list.count())]
        try:
            self.people.reorder(rows)
        except ValueError as error:
            self.person_hint.setText(str(error))
        QTimer.singleShot(0, self.refresh_people)
        self.refresh_controls()

    def load_person(self):
        if self.personnel_worker or self.personnel_importing or self.auto.active or self.auto.busy or self._closing:
            return
        try:
            config = SiteConfig(chrome_path=self.browser_combo.currentData() or "")
            config.validate()
            candidate = self.people.begin()
        except ValueError as error:
            self.person_hint.setText(str(error))
            return
        self.stop_monitor("正在加载人员信息")
        self.auto.session = None
        self._auto_person_position = None
        self.auto_report.clear()
        self.region = None
        self.region_info.setText("手动进入考试并完成验证后，请框选当前浏览器的题目区域")
        self.update_border()
        self.auto_mode.setCurrentIndex(self.auto_mode.findData("screen"))
        worker = PersonnelWorker(self.data_dir, candidate, config, self)
        self.personnel_worker = worker
        worker.progress.connect(self.person_progress)
        worker.ready.connect(self.person_ready)
        worker.failed.connect(self.person_failed)
        worker.finished.connect(self.person_worker_finished)
        worker.start()
        self.refresh_people()
        self.refresh_controls()

    def person_progress(self, message):
        self.person_hint.setText(message)
        self.status.setText("正在加载人员")
        self.log(message)

    def person_ready(self, result):
        self._browser_handles.append(result["handle"])
        if self.people.current is not None:
            self.people.current.status = result["stage"]
        self.person_hint.setText("已停留在登录主页。请手动点击“进入考试”并完成人员验证，再框选区域、启动自动答题。")
        self.status.setText(result["stage"])
        self.refresh_people()

    def person_failed(self, message):
        if self.people.current is not None:
            self.people.current.status, self.people.current.detail = "加载失败", message
        self.person_hint.setText(message + "；可重试加载或跳过当前人员。")
        self.status.setText("人员加载已停止")
        self.log(message)
        self.refresh_people()

    def person_worker_finished(self):
        worker = self.personnel_worker
        self.personnel_worker = None
        if worker:
            worker.deleteLater()
        if self._closing:
            self.close()
        else:
            self.refresh_controls()

    def save_people_results(self):
        if self.results_store is None:
            return
        completed = frozenset(r.candidate.id_number for r in self.people.records if r.status == "已完成")
        self._pending_result_exports[self.results_store] = completed
        self._start_result_export()

    def _start_result_export(self):
        if self._result_export_busy or not self._pending_result_exports:
            return
        store = next(iter(self._pending_result_exports))
        completed = self._pending_result_exports.pop(store)
        self._result_export_busy = True
        self.launch(lambda _: store.save(completed),
                    lambda result: self._people_results_saved(store, result),
                    lambda message: self._people_results_failed(store, message))

    def _people_results_saved(self, store, result):
        self._result_export_busy = False
        if store is self.results_store:
            self.results_directory = result["directory"]
            self.results_summary.setText(f"已完成 {result['completed']} · 未完成 {result['incomplete']}")
            self.results_summary.setToolTip(str(self.results_directory))
            self.results_open.setEnabled(True)
            self.results_retry.hide()
            if result["saved_copy"]:
                self.log(f"原结果文件正在使用，最新两份人员结果已另存：{self.results_directory}")
            else:
                self.log(f"人员结果已保存：已完成 {result['completed']} 人，未完成 {result['incomplete']} 人。")
        self._start_result_export()

    def _people_results_failed(self, store, message):
        self._result_export_busy = False
        if store is self.results_store:
            self.results_summary.setText("人员结果未保存")
            self.results_summary.setToolTip(message)
            self.results_retry.show()
        self.log(f"人员结果保存失败：{message}")
        self._start_result_export()

    def open_people_results(self):
        if self.results_directory is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.results_directory.resolve())))

    def create_people_progress_menu(self, position):
        item = self.people_table.itemAt(position)
        if item is None:
            return None
        selected = {index.row() for index in self.people_table.selectionModel().selectedRows()}
        if item.row() not in selected:
            self.people_table.clearSelection()
            self.people_table.selectRow(item.row())
            selected = {item.row()}
        rows = [self.people.records[index].candidate.row for index in sorted(selected)
                if index < len(self.people.records)]
        menu = QMenu(self)
        action = menu.addAction("添加到备选人员")
        action.setEnabled(not self.personnel_worker and not self.personnel_importing
                          and not self.auto.active and not self.auto.busy and not self._closing)
        action.triggered.connect(lambda: self.return_progress_people(rows))
        return menu

    def people_progress_menu(self, position):
        menu = self.create_people_progress_menu(position)
        if menu is not None:
            menu.exec(self.people_table.viewport().mapToGlobal(position))
            menu.deleteLater()

    def return_progress_people(self, rows):
        if self.personnel_worker or self.personnel_importing or self.auto.active or self.auto.busy or self._closing:
            return
        previous = self.people.current
        associated = self._auto_person_position is not None
        removed = self.people.return_to_pool(rows)
        if not removed:
            return
        if self.people.current is not previous:
            self.stop_monitor("已将当前人员移回备选，浏览器保留")
            self.auto.session = None
            self._auto_person_position = None
        elif associated:
            self._auto_person_position = self.people.position
        self.people_search.clear()
        self.refresh_people()
        returned = {r.candidate.row for r in removed}
        for index in range(self.candidate_list.count()):
            item = self.candidate_list.item(index)
            item.setSelected(item.data(Qt.UserRole) in returned)
        self.save_people_results()
        self.detail_tabs.setCurrentWidget(self.roster_widget)
        self.person_hint.setText(f"已将 {len(removed)} 人移回备选并重置本次结果；需要再次考试时，请重新添加至待考列表。")
        self.log(f"{len(removed)} 人已移回备选，已完成与未完成人员 Excel 正在同步更新。")
        self.refresh_controls()

    def cancel_person_loading(self):
        if self.personnel_worker:
            self.personnel_worker.cancel()
            self.person_cancel.setEnabled(False)
            self.person_hint.setText("正在停止加载，已打开的浏览器会保留…")

    def skip_person(self):
        if self.personnel_worker or self.auto.active or self.auto.busy or self._closing:
            return
        self.stop_monitor("已跳过当前人员，浏览器保留")
        self.people.skip()
        self.auto.session = None
        self._auto_person_position = None
        self.refresh_people()
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
        personnel_busy = self.personnel_worker is not None or self.personnel_importing
        ready = not self.importing and not self.loading and not self._closing and not self.auto.active and not personnel_busy
        self.import_button.setEnabled(ready)
        self.clear_button.setEnabled(ready and bool(self.bank.questions))
        self.start_button.setEnabled(ready and bool(self.bank.questions) and self.region is not None)
        self.retry_button.setEnabled(ready and self.running)
        self.select_button.setEnabled(ready)
        self.search_button.setEnabled(not self._closing and not self.auto.active)
        self.start_button.setText("暂停识别" if self.running else "开始识别")
        self.floating.toggle_button.setText(self.start_button.text())
        self.floating.toggle_button.setEnabled(self.start_button.isEnabled())
        mode=self.auto_mode.currentData()
        self.browser_status.setText(self._browser_connection_message if mode == "dom" else
                                    "屏幕区域模式 · 手动进入考试并验证后，框选完整题目及底部按钮。")
        self.auto_button.setText("暂停自动答题" if self.auto.active else "继续自动答题" if self.auto.can_resume(self.index,mode) else "启动自动答题")
        target_ready=self.browser_bridge.connected if mode=="dom" else self.region is not None
        self.auto_button.setEnabled(self.auto.active or (ready and not self.auto.busy and bool(self.bank.questions) and target_ready))
        self.auto_mode.setEnabled(not self.auto.active and not self._closing and not personnel_busy)
        self.browser_connect_button.setEnabled(not self.auto.active and not self._closing and not personnel_busy)
        self.floating.auto_button.setText(self.auto_button.text())
        self.floating.auto_button.setEnabled(self.auto_button.isEnabled())
        person_ready = not personnel_busy and not self.auto.active and not self.auto.busy and not self._closing
        for widget in (self.browser_combo, self.browser_refresh, self.browser_browse, self.people_import_button):
            widget.setEnabled(person_ready)
        current = self.people.current
        can_load = current is not None and current.status in {"待考试", "加载失败"}
        self.person_button.setEnabled(person_ready and can_load)
        self.person_button.setText(f"进行{current.candidate.name}的考试" if current else "加载人员信息")
        self.person_cancel.setVisible(self.personnel_worker is not None)
        self.person_cancel.setEnabled(self.personnel_worker is not None and not self._closing)
        self.person_skip.setEnabled(person_ready and current is not None)
        for widget in (self.people_search, self.candidate_list, self.waiting_list,
                       self.add_people_button, self.remove_people_button):
            widget.setEnabled(person_ready)
        self.waiting_list.setDragEnabled(person_ready)
        self.waiting_list.setAcceptDrops(person_ready)

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
        if self.auto.mode=="screen":
            self.auto.stop("已展开主界面，自动答题已暂停，可从当前题继续")
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
            self.detail_tabs.setCurrentWidget(self.ocr_text)
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
        self.auto.stop(reason)
        self.running = False
        self.timer.stop()
        self.tracker.invalidate()
        self.clear_answer(reason)
        self.ocr_text.clear()
        self.status.setText(reason)
        self.refresh_controls()

    def toggle_auto(self):
        if self.auto.active:
            self.auto.stop("已停止自动答题")
            return
        # A physical stop-button click is also seen by the interrupt hook on
        # mouse-down. Its later clicked signal must not restart the session.
        if time.monotonic()-self.auto.stopped_at < 1:
            return
        mode=self.auto_mode.currentData()
        if (not self.bank.questions or self.auto.busy or self._closing or self.personnel_worker or self.personnel_importing
                or mode=="screen" and self.region is None or mode=="dom" and not self.browser_bridge.connected):
            return
        resume=self.auto.can_resume(self.index,mode)
        self.stop_monitor("正在启动自动答题")
        if self.search_window is not None:
            self.search_window.hide()
        if not resume:self.auto_report.clear()
        self.detail_tabs.setCurrentWidget(self.auto_report)
        current = self.people.current
        if current and current.status in {"已登录主页", "等待人工验证", "已进入答题页", "已暂停", "正在答题"}:
            self._auto_person_position = self.people.position
            current.status = "正在答题"
            self.refresh_people()
        self.auto.start(self.index,self.region,mode=mode,resume=resume)
        self.refresh_controls()
        if mode=="dom":
            self.log("网页直连自动答题：从当前题继续，不移动系统鼠标。")
            return
        screen = QGuiApplication.screenAt(self.region.center())
        self.floating.hide()
        if screen is not None:
            g = screen.availableGeometry()
            width,height = self.floating.width(),self.floating.height()
            candidates = [QRect(g.x()+10,g.y()+10,width,height),
                          QRect(g.right()-width-10,g.y()+10,width,height),
                          QRect(g.x()+10,g.bottom()-height-10,width,height),
                          QRect(g.right()-width-10,g.bottom()-height-10,width,height)]
            free = next((r for r in candidates if g.contains(r) and not r.intersects(self.region)),None)
            if free is not None:
                self.floating.move(free.topLeft())
                self.floating.show()
        self.showMinimized()
        self.log("已启动自动答题；从当前题逐题核验，有未完成题目不交卷。Esc 可暂停后继续。")

    def browser_connection_changed(self,message):
        self._browser_connection_message = message
        if self.auto.active and self.auto.mode=="dom" and (not self.browser_bridge.connected or self.browser_bridge.binding!=self.auto.binding):
            self.auto.stop("浏览器连接变化；重新连接后可从当前题继续")
        self.refresh_controls()

    def connect_browser(self):
        try:code=self.browser_bridge.connection_code
        except Exception as error:
            QMessageBox.warning(self,"无法启动浏览器连接",str(error))
            return
        dialog=QDialog(self)
        dialog.setWindowTitle("连接浏览器 · 不占鼠标答题")
        dialog.resize(620,380)
        layout=QVBoxLayout(dialog)
        layout.addWidget(label("1. 在 Chrome / Edge 扩展管理页开启开发者模式，\n   选择“加载已解压的扩展程序”，加载下面的扩展目录。\n2. 切换到答题标签页，点击工具栏 NewXKY 扩展。\n3. 将连接码粘贴到扩展中，点击“连接当前答题页”。",wrap=True))
        root=Path(sys.executable).parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parents[1]
        extension=root/"browser_extension"
        if not extension.is_dir():extension=ASSETS.parent/"browser_extension"
        path=QLineEdit(str(extension));path.setReadOnly(True);layout.addWidget(path)
        open_button=QPushButton("打开扩展目录")
        open_button.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(extension))))
        layout.addWidget(open_button)
        field=QLineEdit(code);field.setReadOnly(True);layout.addWidget(field)
        copy=QPushButton("复制连接码")
        copy.clicked.connect(lambda:QApplication.clipboard().setText(code))
        layout.addWidget(copy)
        status=label(self.browser_status.text(),wrap=True);layout.addWidget(status)
        self.browser_bridge.changed.connect(status.setText)
        close=QPushButton("完成")
        close.clicked.connect(dialog.accept);layout.addWidget(close)
        dialog.exec()
        self.refresh_controls()

    def auto_status(self,message):
        self.status.setText("自动答题中" if self.auto.active else "自动答题已停止")
        self.message.setText(emphasize_bank_order(message))
        self.sync_floating()

    def auto_observed(self,result):
        session = result["session"]
        self.ocr_text.setPlainText(result["layout"].text)
        self.timing.setText(f"第 {session.ordinal} 题 · 本次识别 {result['elapsed']:.2f} 秒 · 已核验 {sum(r.completed for r in session.records)} 题")
        q = session.question
        if q is not None:
            correct = {q.options[k] for k in q.answers}
            visible = result["view"].options
            from .bank import normalized
            mapped = [o for o in visible if normalized(o.text) in {normalized(v) for v in correct}]
            verified=session.verified_mapping
            pairs=[(k,session.options[k]["text"])for k,value in (verified or {}).items()if value]
            if not pairs:pairs=[(o.letter,o.text)for o in mapped if o.complete]
            screen_order = len(pairs)==len(q.answers)
            self.answer.setText(" / ".join(k for k,_ in pairs) if screen_order else " / ".join(q.answers))
            self.answer_title.setText(emphasize_bank_order("自动答题 / 网页答案" if screen_order else "自动答题 / 题库顺序"))
            self.answer_detail.setText("\n".join(f"{k}. {v}" for k,v in pairs) if screen_order else "\n".join(f"{k}. {q.options[k]}" for k in q.answers))
            self.question_text.setPlainText(q.stem+"\n\n"+"\n".join(f"{k}. {v}" for k,v in q.options.items()))
            self.provenance.setText(f"{session.method} · {q.source} · PDF 第 {', '.join(map(str,q.pages))} 页")
        else:
            self.answer.setText("—")
            self.answer_detail.clear()
            self.question_text.clear()
            self.provenance.clear()
        self.auto_report.setPlainText("\n".join(f"第 {r.number} 题：{'已完成' if r.completed else '未完成'} · {r.reason}\n{r.stem}" for r in session.records))
        self.sync_floating()

    def auto_finished(self,report):
        self.log(report["reason"])
        lines = [report["reason"],""]
        for record in report["records"]:
            lines.append(f"第 {record.number} 题：{'已完成' if record.completed else '未完成'} · {record.reason}\n{record.stem}\n")
        self.auto_report.setPlainText("\n".join(lines))
        if self._auto_person_position is not None and self._auto_person_position == self.people.position:
            self.people.finish(report["submitted"], report["reason"])
            self.save_people_results()
            self.refresh_people()
            if report["submitted"]:
                self._auto_person_position = None
                self.detail_tabs.setCurrentWidget(self.roster_widget)
                next_record = self.people.current
                self.person_hint.setText(
                    f"已确认交卷，浏览器已保留。请选择下次使用的浏览器，再点击“进行{next_record.candidate.name}的考试”。"
                    if next_record else "待考列表已处理完毕，可从备选人员继续添加；考试窗口均保留。")
                if not self._closing:
                    QTimer.singleShot(0, self.expand_main)
        self.refresh_controls()

    def _auto_idle(self):
        if self._closing and not self._jobs and not self.auto.busy:
            self.close()
        elif not self._closing:
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
            self.refresh_browsers(data.get("browser_path", ""))
            rect = QRect(*data["region"]) if data.get("region") else QRect()
            if rect.width() >= 120 and rect.height() >= 80 and any(s.geometry().contains(rect) for s in QGuiApplication.screens()):
                self.region = rect
                self.region_info.setText(f"已恢复上次区域\n{rect.x()}, {rect.y()} · {rect.width()} × {rect.height()}")
                self.update_border()
        except (OSError, ValueError, TypeError, KeyError):
            pass

    def _save_settings(self):
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            path = self.data_dir / "settings.json"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"region": self.region.getRect() if self.region is not None else None,
                                             "browser_path": self.browser_combo.currentData() or ""}), encoding="utf-8")
            temporary.replace(path)
        except OSError as error:
            self.log(f"区域设置未保存：{error}")

    def closeEvent(self, event):
        self._closing = True
        self.auto.stop("软件已关闭，自动答题已停止")
        if self.personnel_worker:
            self.personnel_worker.cancel()
        self.timer.stop()
        self.running = False
        self.tracker.invalidate()
        self.browser_bridge.close()
        self.border.close()
        self.floating.close()
        if self.search_window is not None:
            self.search_window.close()
        self._save_settings()
        if self._jobs or self.auto.busy or self.personnel_worker:
            self.setEnabled(False)
            self.status.setText("正在完成后台任务后退出…")
            event.ignore()
        else:
            event.accept()


def run(data_dir=None, *, hide_console=False):
    from .lifetime import startup_allowed
    if not startup_allowed():
        return 0
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
