"""Keyword search over the bundled 2026 knowledge bank."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from .default_bank import SOURCE_LABEL
from .matching import KnowledgeIndex


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.PlainText)
    return widget


class SearchWindow(QDialog):
    def __init__(self, index: KnowledgeIndex, parent=None):
        super().__init__(parent)
        self.index = index
        self.matches = []
        self.setObjectName("searchDialog")
        self.setWindowTitle("NewXKY · 关键词搜题")
        self.resize(1000, 760)
        self.setMinimumSize(820, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(14)

        hero = QFrame()
        hero.setObjectName("searchHero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(14)
        icon = QLabel("搜")
        icon.setObjectName("searchHeroIcon")
        icon.setFixedSize(54, 54)
        icon.setAlignment(Qt.AlignCenter)
        hero_layout.addWidget(icon)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(3)
        hero_text.addWidget(label("关键词搜题", "searchTitle"))
        hero_text.addWidget(label(
            f"搜索 {SOURCE_LABEL} 中的题干和选项，多个关键词用空格分隔。",
            "searchSubtitle", True,
        ))
        hero_layout.addLayout(hero_text, 1)
        chip = QLabel(SOURCE_LABEL)
        chip.setObjectName("searchSourceChip")
        hero_layout.addWidget(chip, 0, Qt.AlignVCenter)
        layout.addWidget(hero)

        search_card = QFrame()
        search_card.setObjectName("searchBarCard")
        search_layout = QHBoxLayout(search_card)
        search_layout.setContentsMargins(14, 8, 8, 8)
        search_layout.setSpacing(8)
        self.query = QLineEdit()
        self.query.setObjectName("searchInput")
        self.query.setPlaceholderText("输入题干或选项关键词，例如：重要数据 目录")
        self.query.setClearButtonEnabled(True)
        self.query.setMinimumHeight(38)
        search_layout.addWidget(self.query, 1)
        self.search_button = QPushButton("搜索")
        self.search_button.setObjectName("searchButton")
        self.search_button.setMinimumWidth(88)
        self.search_button.clicked.connect(self.run_search)
        search_layout.addWidget(self.search_button)
        layout.addWidget(search_card)

        summary_row = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setObjectName("searchCount")
        summary_row.addWidget(self.summary)
        summary_row.addStretch()
        summary_row.addWidget(label("答案按题库顺序显示，请按选项内容核对网页", "searchHint"))
        layout.addLayout(summary_row)

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        result_panel = QFrame()
        result_panel.setObjectName("searchPanel")
        result_layout = QVBoxLayout(result_panel)
        result_layout.setContentsMargins(12, 10, 12, 10)
        result_layout.setSpacing(8)
        result_layout.addWidget(label("搜索结果", "searchPanelTitle"))
        self.results = QTableWidget(0, 5)
        self.results.setObjectName("searchResults")
        self.results.setHorizontalHeaderLabels(["序号", "题型", "题干", "答案", "来源"])
        self.results.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results.setSelectionBehavior(QTableWidget.SelectRows)
        self.results.setSelectionMode(QTableWidget.SingleSelection)
        self.results.setAlternatingRowColors(True)
        self.results.setShowGrid(False)
        self.results.verticalHeader().setVisible(False)
        self.results.verticalHeader().setDefaultSectionSize(58)
        self.results.horizontalHeader().setHighlightSections(False)
        self.results.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.results.setColumnWidth(0, 58)
        self.results.setColumnWidth(1, 70)
        self.results.setColumnWidth(3, 80)
        self.results.setColumnWidth(4, 112)
        result_layout.addWidget(self.results, 1)
        splitter.addWidget(result_panel)

        detail_panel = QFrame()
        detail_panel.setObjectName("searchPanel")
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(12, 10, 12, 10)
        detail_layout.setSpacing(8)
        detail_layout.addWidget(label("题目详情", "searchPanelTitle"))
        self.detail = QTextEdit()
        self.detail.setObjectName("searchDetail")
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("选择上方搜索结果，在这里查看完整题目、正确答案和来源。")
        detail_layout.addWidget(self.detail, 1)
        splitter.addWidget(detail_panel)
        splitter.setSizes([330, 300])
        layout.addWidget(splitter, 1)

        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(180)
        self.debounce.timeout.connect(self.run_search)
        self.query.textChanged.connect(lambda: self.debounce.start())
        self.query.returnPressed.connect(self.run_search)
        self.results.itemSelectionChanged.connect(self.show_selected)
        self.run_search()
        QTimer.singleShot(0, self.query.setFocus)

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
                str(row + 1),
                question.kind,
                question.stem,
                " / ".join(question.answers),
                SOURCE_LABEL,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column != 2:
                    item.setTextAlignment(Qt.AlignCenter)
                self.results.setItem(row, column, item)
        self.results.clearSelection()
        self.results.blockSignals(False)
        self.detail.clear()
        self.summary.setStyleSheet("")
        if not self.index.questions:
            self.summary.setText(f"{SOURCE_LABEL} 未加载。")
        elif not query:
            self.summary.setText(f"{SOURCE_LABEL} 共 {len(self.index.questions):,} 道题，请输入关键词。")
        elif not self.matches:
            self.summary.setText("未找到包含这些关键词的题目，可缩短关键词后重试。")
            self.summary.setStyleSheet("background:#fff4f2;color:#b42318;")
        elif fuzzy:
            self.summary.setText(
                f"未找到完全包含关键词的题目，以下 {len(self.matches):,} 道为相似题参考，请核对题干。"
            )
            self.summary.setStyleSheet("background:#fff7e8;color:#9a5b00;")
            self.results.selectRow(0)
        else:
            self.summary.setText(f"找到 {len(self.matches):,} 道题，选择一项查看完整答案。")
            self.results.selectRow(0)

    def show_selected(self):
        row = self.results.currentRow()
        if not 0 <= row < len(self.matches):
            return
        self.detail.setHtml(self._detail_html(self.matches[row]))

    def _detail_html(self, question) -> str:
        answers = " / ".join(question.answers)
        option_rows = []
        for letter, value in question.options.items():
            if letter in question.answers:
                style = "background:#eaf7f1;color:#075e50;border-left:4px solid #0b8c78;"
            else:
                style = "border-left:4px solid transparent;"
            option_rows.append(
                f"<div style='{style} padding:6px 9px;margin:4px 0;border-radius:6px;'>"
                f"<b>{letter}.</b> {escape(value)}</div>"
            )
        pages = ", ".join(map(str, question.pages))
        return (
            "<div style=\"color:#182c43;line-height:1.65;\">"
            "<div style=\"color:#0b8c78;font-weight:700;font-size:12px;\">正确答案（题库顺序）</div>"
            f"<div style=\"font-size:28px;font-weight:700;color:#087c68;margin:2px 0 10px;\">{escape(answers)}</div>"
            f"<div style=\"background:#f4f9f7;border-radius:8px;padding:8px 10px;\">{''.join(option_rows)}</div>"
            "<div style=\"margin-top:14px;color:#0b8c78;font-weight:700;font-size:12px;\">题干</div>"
            f"<div style=\"font-size:14px;margin:4px 0 10px;\">{escape(question.stem)}</div>"
            f"<div style=\"color:#63778c;font-size:12px;\">{escape(question.kind)} · "
            f"第 {question.number} 题 · 来源：{SOURCE_LABEL} · 第 {escape(pages)} 页</div>"
            "<div style=\"color:#7b8d9c;font-size:12px;margin-top:6px;\">"
            "网页可能调整选项顺序，请以正确选项内容为准。</div>"
            "</div>"
        )
