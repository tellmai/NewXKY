"""Keyword search over the bundled 2026 knowledge bank."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from .default_bank import SOURCE_LABEL
from .matching import KnowledgeIndex


class SearchWindow(QDialog):
    def __init__(self, index: KnowledgeIndex, parent=None):
        super().__init__(parent)
        self.index = index
        self.matches = []
        self.setWindowTitle("NewXKY · 关键词搜题")
        self.resize(980, 700)
        self.setMinimumSize(760, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        heading = QLabel("关键词搜题")
        heading.setObjectName("brand")
        layout.addWidget(heading)
        hint = QLabel(
            f"搜索 {SOURCE_LABEL} 中的题干和选项；多个关键词用空格分隔。"
            "答案按题库顺序显示，请按选项内容核对网页。"
        )
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        layout.addWidget(hint)

        controls = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("输入关键词，例如：重要数据 目录")
        self.query.setClearButtonEnabled(True)
        self.query.setMinimumHeight(38)
        controls.addWidget(self.query, 1)
        self.search_button = QPushButton("搜索")
        self.search_button.setObjectName("primary")
        self.search_button.clicked.connect(self.run_search)
        controls.addWidget(self.search_button)
        layout.addLayout(controls)

        self.summary = QLabel()
        self.summary.setObjectName("muted")
        layout.addWidget(self.summary)

        self.results = QTableWidget(0, 4)
        self.results.setHorizontalHeaderLabels(["题型", "题干", "答案", "来源"])
        self.results.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results.setSelectionBehavior(QTableWidget.SelectRows)
        self.results.setSelectionMode(QTableWidget.SingleSelection)
        self.results.setAlternatingRowColors(True)
        self.results.verticalHeader().setVisible(False)
        self.results.verticalHeader().setDefaultSectionSize(62)
        self.results.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.results.setColumnWidth(0, 65)
        self.results.setColumnWidth(2, 80)
        self.results.setColumnWidth(3, 110)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("选择搜索结果，在这里查看完整题目、正确答案和来源。")
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.results)
        splitter.addWidget(self.detail)
        splitter.setSizes([270, 300])
        layout.addWidget(splitter, 1)

        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(180)
        self.debounce.timeout.connect(self.run_search)
        self.query.textChanged.connect(lambda: self.debounce.start())
        self.query.returnPressed.connect(self.run_search)
        self.results.itemSelectionChanged.connect(self.show_selected)
        self.run_search()

    def set_index(self, index: KnowledgeIndex):
        self.index = index
        self.run_search()

    def set_query(self, text: str):
        self.query.setText(text)
        self.run_search()
        self.query.setFocus()

    def run_search(self):
        self.debounce.stop()
        query = self.query.text().strip()
        self.matches = self.index.search(query)
        fuzzy = False
        if not self.matches and query:
            self.matches = [question for question, _score in self.index.find_candidates(query, 10)]
            fuzzy = bool(self.matches)
        self.results.blockSignals(True)
        self.results.setRowCount(len(self.matches))
        for row, question in enumerate(self.matches):
            values = (
                question.kind,
                question.stem,
                " / ".join(question.answers),
                SOURCE_LABEL,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.results.setItem(row, column, item)
        self.results.clearSelection()
        self.results.blockSignals(False)
        self.detail.clear()
        if not self.index.questions:
            self.summary.setText(f"{SOURCE_LABEL} 未加载。")
        elif not query:
            self.summary.setText(f"{SOURCE_LABEL} 共 {len(self.index.questions):,} 道题，请输入关键词。")
        elif not self.matches:
            self.summary.setText("未找到包含这些关键词的题目，可缩短关键词后重试。")
        elif fuzzy:
            self.summary.setText(
                f"未找到完全包含关键词的题目，以下 {len(self.matches):,} 道为相似题参考，请核对题干。"
            )
            self.results.selectRow(0)
        else:
            self.summary.setText(f"找到 {len(self.matches):,} 道题，选择一项查看完整答案。")
            self.results.selectRow(0)

    def show_selected(self):
        row = self.results.currentRow()
        if not 0 <= row < len(self.matches):
            return
        question = self.matches[row]
        correct = "\n".join(
            f"{letter}. {question.options[letter]}" for letter in question.answers
        )
        options = "\n".join(f"{letter}. {value}" for letter, value in question.options.items())
        pages = ", ".join(map(str, question.pages))
        self.detail.setPlainText(
            f"正确答案（题库顺序）：{' / '.join(question.answers)}\n{correct}\n\n"
            f"{question.kind} · 第 {question.number} 题\n{question.stem}\n\n"
            f"全部选项：\n{options}\n\n"
            f"来源：{SOURCE_LABEL} · 第 {pages} 页\n"
            "网页可能调整选项顺序，请以正确选项内容为准。"
        )
