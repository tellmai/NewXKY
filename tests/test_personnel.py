import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from openpyxl import Workbook
from PySide6.QtWidgets import QApplication

from newxky.browsers import BrowserChoice, discover_browsers
from newxky.identities import Candidate, ExamQueue, IdentityImport, SiteConfig, load_identities


PEOPLE = [Candidate(2, "黔江区", "演示甲", "110101199001010010"),
          Candidate(3, "黔江区", "演示乙", "110101199001010011")]


def test_import_preserves_text_ids_rejects_precision_loss_and_duplicates(tmp_path):
    wb = Workbook()
    wb.active.append(["忽略的表"])
    sheet = wb.create_sheet("人员")
    sheet.append(["姓名", "所在的区县", "身份证号"])
    sheet.append(["演示甲", "黔江区", "11010119900101001x"])
    sheet.append(["重复", "黔江区", "11010119900101001X"])
    sheet.append(["数值", "黔江区", 110101199001010010])
    sheet.append(["缺少区县", "", "110101199001010010"])
    sheet.append([None, None, None])
    path = tmp_path / "people.xlsx"
    wb.save(path)
    result = load_identities(path)
    assert result.sheet == "人员" and len(result.candidates) == 1
    assert len(result.issues) == 3
    assert result.candidates[0].id_number.endswith("X")
    assert "19900101" not in result.candidates[0].masked_id
    assert "11010119900101001" not in repr(result.candidates[0])


def test_queue_requires_confirmed_submission_and_explicit_next_launch():
    queue = ExamQueue(PEOPLE)
    assert queue.begin() == PEOPLE[0]
    queue.finish(False, "未找到可靠答案")
    assert queue.position == 0 and queue.current.status == "已暂停"
    with pytest.raises(ValueError):
        queue.begin()
    queue.finish(True, "已确认交卷")
    assert queue.position == 1 and queue.current.status == "待考试"
    assert queue.begin() == PEOPLE[1]
    queue.finish(True, "已确认交卷")
    assert queue.current is None


def test_queue_explicit_skip_and_load_retry():
    queue = ExamQueue(PEOPLE)
    queue.begin()
    queue.current.status = "加载失败"
    assert queue.begin() == PEOPLE[0]
    queue.skip()
    assert queue.current.candidate == PEOPLE[1] and queue.records[0].status == "已跳过"


@pytest.mark.parametrize("url", ["http://ks.cqsdx.cn/exam/", "https://example.com/exam/",
                                 "https://ks.cqsdx.cn.evil.example/exam/", "https://ks.cqsdx.cn/exam/?id=1"])
def test_personal_data_only_goes_to_expected_exam_origin(url):
    with pytest.raises(ValueError):
        SiteConfig(url).validate()


def test_browser_inventory_includes_unsupported_without_selecting_it(tmp_path, monkeypatch):
    from newxky import browsers
    chrome = tmp_path / "chrome.exe"
    firefox = tmp_path / "firefox.exe"
    chrome.touch()
    firefox.touch()
    monkeypatch.setattr(browsers, "_registry_paths", lambda: [str(firefox), str(chrome), str(chrome).upper()])
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        monkeypatch.delenv(key, raising=False)
    choices = discover_browsers(include_unsupported=True)
    assert [(c.name, c.compatible) for c in choices] == [("Google Chrome", True), ("Mozilla Firefox", False)]


def test_ui_advances_one_person_changes_browser_and_clears_previous_session(tmp_path, monkeypatch):
    from PySide6.QtCore import QObject, Signal
    from newxky import ui
    app = QApplication.instance() or QApplication([])
    paths = [tmp_path / "chrome.exe", tmp_path / "msedge.exe", tmp_path / "firefox.exe"]
    for path in paths:
        path.touch()
    choices = [BrowserChoice("Chrome", str(paths[0]), 0), BrowserChoice("Edge", str(paths[1]), 1),
               BrowserChoice("Firefox", str(paths[2]), 4, False)]
    monkeypatch.setattr(ui, "discover_browsers", lambda **k: choices)
    calls = []
    class Worker(QObject):
        progress, ready, failed, finished = Signal(str), Signal(object), Signal(str), Signal()
        def __init__(self, data_dir, candidate, config, parent):
            super().__init__(parent)
            calls.append((candidate, config.chrome_path))
        def start(self):
            pass
        def cancel(self):
            pass
    monkeypatch.setattr(ui, "PersonnelWorker", Worker)
    window = ui.MainWindow(tmp_path)
    assert window.auto_mode.currentData() == "screen"
    assert "屏幕区域模式" in window.browser_status.text()
    assert [window.detail_tabs.tabText(i) for i in range(window.detail_tabs.count())] == [
        "备选 / 待考人员", "人员考试进度", "识别文字", "题库原文", "自动答题记录", "已导入题库", "导入 / 运行记录"]
    window.people_imported(IdentityImport(PEOPLE, [], "人员"))
    assert window.person_button.text() == "加载人员信息"
    assert window.people.current is None and not window.person_button.isEnabled()
    assert window.candidate_list.count() == 2 and window.waiting_list.count() == 0
    window.candidate_list.selectAll()
    window.add_waiting_people()
    assert window.person_button.text() == "进行演示甲的考试"
    assert not window.browser_combo.model().item(3).isEnabled()
    window.browser_combo.setCurrentIndex(1)
    window.load_person()
    assert calls == [(PEOPLE[0], str(paths[0]))]
    assert not window.browser_combo.isEnabled() and not window.auto_button.isEnabled()
    handle = object()
    window.person_ready({"handle": handle, "stage": "已登录主页"})
    assert "手动点击“进入考试”" in window.person_hint.text()
    window.person_worker_finished()
    window._auto_person_position = 0
    window.auto_finished({"submitted": False, "reason": "暂停", "records": []})
    assert window.people.position == 0 and not window.person_button.isEnabled()
    window.auto_finished({"submitted": True, "reason": "交卷成功", "records": []})
    assert window.people.position == 1
    assert window.person_button.text() == "进行演示乙的考试"
    assert window.browser_combo.isEnabled() and window._browser_handles == [handle]
    from newxky.automation import AutoSession
    window.auto.session = AutoSession(window.index)
    window.browser_combo.setCurrentIndex(2)
    window.load_person()
    assert calls[-1] == (PEOPLE[1], str(paths[1]))
    assert window.auto.session is None and window.region is None
    window.person_worker_finished()
    window.close()


def test_browser_choice_persists_without_a_capture_region(tmp_path, monkeypatch):
    from newxky import ui
    app = QApplication.instance() or QApplication([])
    custom = tmp_path / "custom.exe"
    custom.touch()
    monkeypatch.setattr(ui, "discover_browsers", lambda **k: [])
    first = ui.MainWindow(tmp_path)
    first.refresh_browsers(str(custom))
    first.close()
    second = ui.MainWindow(tmp_path)
    assert second.browser_combo.currentData() == str(custom)
    custom.unlink()
    second.refresh_browsers()
    assert "文件不存在" in second.browser_combo.currentText()
    assert second.browser_combo.currentData() == str(custom)
    second.close()


def test_roster_search_add_drag_order_remove_and_always_start_at_top(tmp_path, monkeypatch):
    from PySide6.QtCore import QModelIndex
    from newxky import ui
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui.MainWindow, "restore_bank", lambda self: None)
    window = ui.MainWindow(tmp_path)
    people = PEOPLE + [Candidate(4, "渝中区", "其他考生", "110101199001010012")]
    window.people_imported(IdentityImport(people, [], "人员"))
    assert not window.people.records and window.waiting_list.count() == 0
    window.people_search.setText("演示乙")
    assert window.candidate_list.count() == 1
    window.candidate_list.item(0).setSelected(True)
    window.add_waiting_people()
    assert window.people.current.candidate == PEOPLE[1]
    window.people_search.setText("演示甲")
    window.candidate_list.item(0).setSelected(True)
    window.add_waiting_people()
    assert [r.candidate for r in window.people.pending] == [PEOPLE[1], PEOPLE[0]]
    assert window.person_button.text() == "进行演示乙的考试"
    assert window.waiting_list.model().moveRows(QModelIndex(), 1, 1, QModelIndex(), 0)
    assert [r.candidate for r in window.people.pending] == PEOPLE
    assert window.person_button.text() == "进行演示甲的考试"
    app.processEvents()
    window.waiting_list.setCurrentRow(1)
    # Merely selecting a lower row never changes the next person to load.
    assert window.person_button.text() == "进行演示甲的考试"
    window.remove_waiting_people()
    window.people_search.clear()
    assert window.people.current.candidate == PEOPLE[0]
    assert window.waiting_list.count() == 1 and window.candidate_list.count() == 2
    window.close()


def test_reorder_cannot_replace_person_while_exam_is_in_progress():
    queue = ExamQueue(PEOPLE)
    queue.begin()
    queue.current.status = "等待人工验证"
    with pytest.raises(ValueError):
        queue.reorder([PEOPLE[1].row, PEOPLE[0].row])
    queue.remove([PEOPLE[0].row])
    assert queue.current.candidate == PEOPLE[0]
