from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTabWidget

from newxky.keyword_search import SearchWindow
from newxky.matching import KnowledgeIndex, Match
from newxky.models import Bank, Question
from newxky.ui import ActivationDialog, MainWindow
from newxky import __version__


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
        assert f"V{__version__}" in window.windowTitle()
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


def test_recognized_answer_is_rendered_in_bank_order(tmp_path):
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
        body = window.answer_detail.toPlainText()
        assert window.answer_title.text() == "当前题目 / 题库答案"
        assert "题库答案请注意实际考题顺序" in window.message.text()
        assert "B" not in window.status.text()
        assert window.status.text() == "题库答案"
        assert question.stem in body
        assert "A. " in body and "B. " in body
        assert question.options["B"] in body
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


def test_incomplete_page_options_still_show_the_full_bank_answer(tmp_path):
    manager = FakeManager()
    window = MainWindow(manager, bank(), data_dir=tmp_path, app_dir=tmp_path)
    try:
        window.show()
        window.running = True
        question = window.bank.questions[0]
        match = Match(
            "incomplete",
            "题干已匹配；当前画面只识别到 2/4 个选项。",
            question, options={"A": question.options["A"], "B": question.options["B"]}, score=1,
        )
        window.tracker.observe(b"frame", 0)
        revision = window.tracker.begin()
        window.recognized(revision, ("识别文字", match, .1))
        body = window.answer_detail.toPlainText()
        assert window.status.text() == "题库答案"
        assert "题库答案请注意实际考题顺序" in window.message.text()
        # Every bank option is listed even though the page showed only two.
        assert question.options["A"] in body and question.options["B"] in body
        assert question.stem in body
    finally:
        window.close()


def test_missing_question_clears_the_answer(tmp_path):
    manager = FakeManager()
    window = MainWindow(manager, bank(), data_dir=tmp_path, app_dir=tmp_path)
    try:
        window.running = True
        match = Match("missing", "2026知识库 中未找到匹配题目；可点击“关键词搜题”手动检索")
        window.tracker.observe(b"blank", 0)
        revision = window.tracker.begin()
        window.recognized(revision, ("随便一段文字", match, .1))
        assert window.status.text() == "未找到题目"
        assert window.answer_detail.toPlainText() == ""
        assert "未找到匹配题目" in window.message.text()
    finally:
        window.close()

