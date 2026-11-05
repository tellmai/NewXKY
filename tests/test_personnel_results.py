import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from openpyxl import load_workbook
from PySide6.QtWidgets import QApplication

from newxky.identities import Candidate, IdentityImport, load_identities
from newxky.personnel_results import HEADERS, PersonnelResults


PEOPLE = [Candidate(2, "黔江区", "演示甲", "11010119900101001X"),
          Candidate(3, "江北区", "演示乙", "110101199001010011"),
          Candidate(4, "渝中区", "演示丙", "110101199001010012")]


def test_saved_workbooks_partition_all_imported_people_and_can_be_reimported(tmp_path):
    store = PersonnelResults(tmp_path, PEOPLE)
    first = store.save(())
    assert first["completed"] == 0 and first["incomplete"] == 3
    assert load_identities(store.directory / "已完成人员.xlsx").candidates == []
    result = store.save({PEOPLE[0].id_number})
    assert result["completed"] == 1 and result["incomplete"] == 2
    for filename, expected in (("已完成人员.xlsx", PEOPLE[:1]), ("未完成人员.xlsx", PEOPLE[1:])):
        path = store.directory / filename
        workbook = load_workbook(path)
        try:
            assert tuple(c.value for c in workbook.active[1]) == HEADERS
            assert list(workbook.active.values)[1:] == [(c.district, c.name, c.id_number) for c in expected]
            assert all(cell.data_type == "s" and cell.number_format == "@"
                       for row in workbook.active.iter_rows(min_row=2) for cell in row)
        finally:
            workbook.close()
        imported = load_identities(path)
        assert not imported.issues
        assert [c.id_number for c in imported.candidates] == [c.id_number for c in expected]
    store.save({PEOPLE[0].id_number})
    assert len(load_identities(store.directory / "已完成人员.xlsx").candidates) == 1


def test_export_keeps_names_as_literal_text_and_preserves_id_precision(tmp_path):
    candidate = Candidate(2, "=区县", "=演示姓名", "11010119900101001X")
    store = PersonnelResults(tmp_path, [candidate])
    store.save(())
    book = load_workbook(store.directory / "未完成人员.xlsx", data_only=False)
    try:
        assert [cell.value for cell in book.active[2]] == [candidate.district, candidate.name, candidate.id_number]
        assert all(cell.data_type == "s" for cell in book.active[2])
    finally:
        book.close()


def test_new_import_batch_does_not_overwrite_previous_results(tmp_path):
    first = PersonnelResults(tmp_path, PEOPLE)
    first.save({PEOPLE[0].id_number})
    second = PersonnelResults(tmp_path, PEOPLE[1:])
    second.save(())
    assert first.directory != second.directory
    assert [c.id_number for c in load_identities(first.directory / "已完成人员.xlsx").candidates] == [PEOPLE[0].id_number]


def test_workbook_generation_failure_preserves_previous_pair(tmp_path, monkeypatch):
    store = PersonnelResults(tmp_path, PEOPLE)
    store.save(())
    original = {name: (store.directory / name).read_bytes() for name in ("已完成人员.xlsx", "未完成人员.xlsx")}
    real_write = store._write_workbook
    calls = []
    def fail_second(path, people):
        calls.append(path)
        if len(calls) == 2:
            raise OSError("simulated storage failure")
        real_write(path, people)
    monkeypatch.setattr(store, "_write_workbook", fail_second)
    with pytest.raises(OSError):
        store.save({PEOPLE[0].id_number})
    assert all((store.directory / name).read_bytes() == content for name, content in original.items())
    assert not list(store.directory.glob(".*.xlsx"))


def test_open_excel_file_saves_complete_latest_pair_elsewhere(tmp_path, monkeypatch):
    store = PersonnelResults(tmp_path, PEOPLE)
    store.save(())
    old_directory = store.directory
    replace = Path.replace
    def locked(source, destination):
        if destination == old_directory / "未完成人员.xlsx":
            raise PermissionError("simulated open Excel file")
        return replace(source, destination)
    monkeypatch.setattr(Path, "replace", locked)
    result = store.save({PEOPLE[0].id_number})
    assert result["saved_copy"] and result["directory"] != old_directory
    assert load_identities(store.directory / "已完成人员.xlsx").candidates[0].id_number == PEOPLE[0].id_number
    assert len(load_identities(store.directory / "未完成人员.xlsx").candidates) == 2


def test_ui_saves_only_confirmed_success_and_keeps_backup_skipped_and_paused_people_incomplete(tmp_path, monkeypatch):
    from newxky import ui
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui.MainWindow, "restore_bank", lambda self: None)
    def immediate(self, function, result, error, progress=None):
        try:
            value = function(lambda *a: None)
        except Exception as failure:
            error(str(failure))
        else:
            result(value)
    monkeypatch.setattr(ui.MainWindow, "launch", immediate)
    window = ui.MainWindow(tmp_path)
    window.people_imported(IdentityImport(PEOPLE, [], "人员"))
    directory = window.results_directory
    assert directory is not None and window.results_open.isEnabled()
    window.people.add(PEOPLE[:2])
    window._auto_person_position = 0
    window.auto_finished({"submitted": False, "reason": "未完成", "records": []})
    assert len(load_identities(directory / "未完成人员.xlsx").candidates) == 3
    assert not load_identities(directory / "已完成人员.xlsx").candidates
    window.auto_finished({"submitted": True, "reason": "确认交卷", "records": []})
    window.skip_person()
    assert [c.id_number for c in load_identities(directory / "已完成人员.xlsx").candidates] == [PEOPLE[0].id_number]
    assert [c.id_number for c in load_identities(directory / "未完成人员.xlsx").candidates] == [p.id_number for p in PEOPLE[1:]]
    assert window.people.current is None
    assert window.candidate_list.count() == 1
    window.close()


def test_queued_exports_keep_latest_state_for_each_import_batch(tmp_path, monkeypatch):
    from newxky import ui
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui.MainWindow, "restore_bank", lambda self: None)
    jobs = []
    monkeypatch.setattr(ui.MainWindow, "launch", lambda self, function, result, error, progress=None:
                        jobs.append((function, result)))
    window = ui.MainWindow(tmp_path)
    window.people_imported(IdentityImport(PEOPLE, [], "人员"))
    first = window.results_store
    window.people.add(PEOPLE[:1])
    window._auto_person_position = 0
    window.auto_finished({"submitted": True, "reason": "确认交卷", "records": []})
    window.people_imported(IdentityImport(PEOPLE[1:], [], "第二批"))
    second = window.results_store
    assert len(jobs) == 1
    while jobs:
        function, result = jobs.pop(0)
        result(function(lambda *a: None))
    assert [c.id_number for c in load_identities(first.directory / "已完成人员.xlsx").candidates] == [PEOPLE[0].id_number]
    assert len(load_identities(second.directory / "未完成人员.xlsx").candidates) == 2
    assert window.results_directory == second.directory
    assert window.results_summary.text() == "已完成 0 · 未完成 2"
    window.close()


def test_progress_context_menu_returns_success_and_failure_to_pool_and_synchronizes_excel(tmp_path, monkeypatch):
    from newxky import ui
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui.MainWindow, "restore_bank", lambda self: None)
    def immediate(self, function, result, error, progress=None):
        result(function(lambda *a: None))
    monkeypatch.setattr(ui.MainWindow, "launch", immediate)
    window = ui.MainWindow(tmp_path)
    window.people_imported(IdentityImport(PEOPLE, [], "人员"))
    window.people.add(PEOPLE)
    window.people.records[0].status = "已完成"
    window.people.position = 1
    window.people.current.status = "加载失败"
    window.refresh_people()
    window.save_people_results()
    directory = window.results_directory
    assert len(load_identities(directory / "已完成人员.xlsx").candidates) == 1
    window.detail_tabs.setCurrentWidget(window.people_table)
    window.people_table.selectRow(0)
    position = window.people_table.visualItemRect(window.people_table.item(0, 0)).center()
    menu = window.create_people_progress_menu(position)
    assert menu.actions()[0].text() == "添加到备选人员"
    assert menu.actions()[0].isEnabled()
    menu.actions()[0].trigger()
    assert window.people.position == 0 and window.people.current.candidate == PEOPLE[1]
    assert window.candidate_list.count() == 1 and window.waiting_list.count() == 2
    assert not load_identities(directory / "已完成人员.xlsx").candidates
    assert len(load_identities(directory / "未完成人员.xlsx").candidates) == 3
    window.return_progress_people([PEOPLE[1].row])
    assert window.candidate_list.count() == 2 and window.waiting_list.count() == 1
    window.people.add(PEOPLE[:1])
    window.people.reorder([PEOPLE[0].row, PEOPLE[2].row])
    window._auto_person_position = 0
    window.auto_finished({"submitted": True, "reason": "重新考试已交卷", "records": []})
    assert [c.id_number for c in load_identities(directory / "已完成人员.xlsx").candidates] == [PEOPLE[0].id_number]
    assert [c.id_number for c in load_identities(directory / "未完成人员.xlsx").candidates] == [c.id_number for c in PEOPLE[1:]]
    window.close()


def test_returning_paused_person_clears_resume_and_is_disabled_during_automation(tmp_path, monkeypatch):
    from newxky import ui
    from newxky.automation import AutoSession
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui.MainWindow, "restore_bank", lambda self: None)
    monkeypatch.setattr(ui.MainWindow, "launch", lambda self, function, result, error, progress=None:
                        result(function(lambda *a: None)))
    window = ui.MainWindow(tmp_path)
    window.people_imported(IdentityImport(PEOPLE, [], "人员"))
    window.people.add(PEOPLE)
    window.people.current.status = "已暂停"
    window.auto.session = AutoSession(window.index)
    window._auto_person_position = 0
    window.refresh_people()
    window.auto.active = True
    position = window.people_table.visualItemRect(window.people_table.item(0, 0)).center()
    menu = window.create_people_progress_menu(position)
    assert not menu.actions()[0].isEnabled()
    window.return_progress_people([PEOPLE[0].row])
    assert window.people.current.candidate == PEOPLE[0]
    window.auto.active = False
    window.return_progress_people([PEOPLE[0].row])
    assert window.auto.session is None and window._auto_person_position is None
    assert window.people.current.candidate == PEOPLE[1]
    assert window.candidate_list.count() == 1
    window.close()


def test_returning_completed_person_while_export_is_pending_keeps_latest_classification(tmp_path, monkeypatch):
    from newxky import ui
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui.MainWindow, "restore_bank", lambda self: None)
    jobs = []
    monkeypatch.setattr(ui.MainWindow, "launch", lambda self, function, result, error, progress=None:
                        jobs.append((function, result)))
    window = ui.MainWindow(tmp_path)
    window.people_imported(IdentityImport(PEOPLE, [], "人员"))
    window.people.add(PEOPLE[:1])
    window._auto_person_position = 0
    window.auto_finished({"submitted": True, "reason": "确认交卷", "records": []})
    window.return_progress_people([PEOPLE[0].row])
    while jobs:
        function, result = jobs.pop(0)
        result(function(lambda *a: None))
    assert not load_identities(window.results_directory / "已完成人员.xlsx").candidates
    assert len(load_identities(window.results_directory / "未完成人员.xlsx").candidates) == 3
    assert window.candidate_list.count() == 3
    assert window.results_summary.text() == "已完成 0 · 未完成 3"
    window.close()
