from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTabWidget

from newxky.keyword_search import SearchWindow
from newxky.matching import KnowledgeIndex, Match
from newxky.models import Bank, Question
from newxky.ui import ActivationDialog, MainWindow


class FakeManager:
    server_url = ""
    last_error = ""

    def __init__(self):
        self.expired = False
        self.remaining = 2399

    def remaining_seconds(self):
        return 0 if self.expired else self.remaining

    @property
    def can_use(self):
        return not self.expired and self.remaining_seconds() > 0

    def reload_lease(self):
        return None

    def touch(self):
        return None

    def refresh(self):
        return self.remaining_seconds()

    def activate(self, code):
        raise AssertionError("not used")


def bank():
    return Bank(
        [Question(1, "单选", "下列哪一项属于依法行政的要求（）",
                  {"A": "任意扩大权限", "B": "依照法定权限和程序履行职责"},
                  ("B",), (1,), "题库.pdf")],
        sources=["题库.pdf"], page_count=2,
    )


def test_main_window_is_simplified_and_shows_license(tmp_path):
    manager = FakeManager()
    window = MainWindow(manager, bank(), data_dir=tmp_path, app_dir=tmp_path)
    try:
        window.show()
        window.license_tick()
        texts = [button.text() for button in window.findChildren(QPushButton)]
        assert "已验证 · 剩余 39:59" in window.license_label.text()
        assert "V1.0.8" in window.windowTitle()
        assert window.bank_count.text() == "1"
        assert not window.findChildren(QTabWidget)
        assert not any("导入" in text or "自动答题" in text or "人员" in text for text in texts)
        assert window.search_button.text() == "关键词搜题"
        assert window.search_button.isEnabled()
        assert window.license_hint.text() == "软件授权已生效。有效期内可随时开关，倒计时不暂停。"
        assert window.select_button.isEnabled()
        assert not window.start_button.isEnabled()
        assert window.renew_button.isHidden()
    finally:
        window.close()


def test_main_window_can_shrink_to_360_by_298_and_restore(tmp_path):
    manager = FakeManager()
    window = MainWindow(manager, bank(), data_dir=tmp_path, app_dir=tmp_path)
    try:
        window.show()
        window.resize(360, 298)
        QApplication.processEvents()
        assert window.size().width() == 360
        assert window.size().height() == 298
        assert not window.sidebar.isVisible()
        assert window.compact_bar.isVisible()
        assert window.compact_select_button.isVisible()
        assert window.compact_start_button.isVisible()
        assert not window.status.isVisible()
        assert not window.subtitle.isVisible()
        assert window.search_button.text() == "搜题"
        window.resize(1080, 760)
        QApplication.processEvents()
        assert window.sidebar.isVisible()
        assert not window.compact_bar.isVisible()
        assert window.status.isVisible()
        assert window.search_button.text() == "关键词搜题"
    finally:
        window.close()


def test_region_enables_start_and_expiry_locks_it(tmp_path):
    manager = FakeManager()
    window = MainWindow(manager, bank(), data_dir=tmp_path, app_dir=tmp_path)
    try:
        window.region = QRect(10, 10, 500, 300)
        window.refresh_controls()
        assert window.start_button.isEnabled()
        manager.expired = True
        window.license_tick()
        assert window.license_label.text() == "授权已到期"
        assert not window.start_button.isEnabled()
        assert not window.select_button.isEnabled()
        assert not window.renew_button.isHidden()
    finally:
        window.close()


def test_recognized_answer_is_rendered(tmp_path):
    manager = FakeManager()
    window = MainWindow(manager, bank(), data_dir=tmp_path, app_dir=tmp_path)
    try:
        question = window.bank.questions[0]
        text = (
            question.stem + "\n"
            "A. " + question.options["A"] + "\n"
            "B. " + question.options["B"]
        )
        match = window.index.lookup(text)
        assert match.status == "matched"
        window.running = True
        window.tracker.observe(b"question", 0)
        assert window.tracker.ready(.5)
        revision = window.tracker.begin()
        window.recognized(revision, (text, match, .1))
        assert window.answer.text() == "B"
        assert "依照法定权限" in window.answer_detail.toPlainText()
        assert question.stem in window.answer_detail.toPlainText()
        assert "2026知识库" in window.provenance.text()
    finally:
        window.close()


def test_activation_dialog_explains_single_use_and_timer(tmp_path):
    manager = FakeManager()
    dialog = ActivationDialog(manager)
    try:
        texts = " ".join(item.text() for item in dialog.findChildren(QLabel))
        assert dialog.windowTitle().startswith("NewXKY")
        assert dialog.code_input.placeholderText() == "XXXX-XXXX-XXXX-XXXX"
        assert "只能激活一台电脑" in texts
        assert "40 分钟" in texts
    finally:
        dialog.reject()


def test_keyword_search_window_shows_source_label():
    q = Question(1, "单选", "关于重要数据目录，下列说法正确的是（）",
                 {"A": "正确内容", "B": "其他内容"}, ("A",), (3,), "题库.pdf")
    dialog = SearchWindow(KnowledgeIndex([q]))
    try:
        dialog.set_query("重要数据")
        assert dialog.results.rowCount() == 1
        assert dialog.results.item(0, 0).text() == "1"
        assert dialog.results.item(0, 4).text() == "2026知识库"
        assert "来源：2026知识库" in dialog.detail.toPlainText()
    finally:
        dialog.close()


def test_reselect_region_replaces_previous_region(tmp_path):
    manager = FakeManager()
    window = MainWindow(manager, bank(), data_dir=tmp_path, app_dir=tmp_path)
    try:
        window.region = QRect(0, 0, 300, 200)
        window.region_selected(QRect(10, 20, 500, 300))
        assert window.region == QRect(10, 20, 500, 300)
        window.region_selected(QRect(30, 40, 640, 420))
        assert window.region == QRect(30, 40, 640, 420)
        assert "位置 30, 40" in window.region_info.text()
        assert not window._selecting
    finally:
        window.close()


def test_close_hides_region_border(tmp_path):
    manager = FakeManager()
    window = MainWindow(manager, bank(), data_dir=tmp_path, app_dir=tmp_path)
    window.region = QRect(0, 0, 500, 300)
    window.update_border()
    window.border.show()
    assert window.border.isVisible()
    window.close()
    assert not window.border.isVisible()


def test_incomplete_options_prompt_scroll_and_offer_red_bank_fallback(tmp_path):
    manager = FakeManager()
    window = MainWindow(manager, bank(), data_dir=tmp_path, app_dir=tmp_path)
    try:
        window.show()
        window.running = True
        question = window.bank.questions[0]
        match = Match(
            "incomplete",
            "当前画面只识别到 2/4 个选项，答案可能在未显示的选项里。请向下滚动考试页面。",
            question, options={"A": question.options["A"], "B": question.options["B"]}, score=1,
        )
        window.tracker.observe(b"frame", 0)
        revision = window.tracker.begin()
        window.recognized(revision, ("识别文字", match, .1))
        assert window.status.text() == "等待完整选项"
        assert window.answer.text() == "待核对"
        assert "滚动" in window.message.text()
        assert window.bank_fallback_button.isVisible()
        window.bank_fallback_button.click()
        assert window.status.text() == "题库顺序参考"
        assert "color:#c62828" in window.answer.styleSheet()
        assert window.answer.text() == " / ".join(question.answers)
        assert window.bank_fallback_button.isHidden()
    finally:
        window.close()


def test_scrolled_lower_options_merge_with_cached_upper_options(tmp_path):
    manager = FakeManager()
    question = Question(
        1, "单选", "跨屏题目（）",
        {"A": "选项甲", "B": "选项乙", "C": "选项丙", "D": "选项丁"},
        ("B",), (1,), "题库.pdf",
    )
    window = MainWindow(manager, Bank([question], sources=["题库.pdf"], page_count=1),
                        data_dir=tmp_path, app_dir=tmp_path)
    try:
        window._scroll_question = question
        window._scroll_options = {
            "A": question.options["A"],
            "B": question.options["B"],
        }
        lower = (
            "C. " + question.options["C"] + "\n"
            "D. " + question.options["D"]
        )
        merged = window._merge_scrolled(lower, window.index)
        assert merged is not None
        _text, match = merged
        assert match.status == "matched"
        assert match.answers == ("B",)
    finally:
        window.close()
