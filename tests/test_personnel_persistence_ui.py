import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtCore import QPointF,Qt
from PySide6.QtWidgets import QApplication

from newxky.identities import IdentityImport
from test_identity_folder import workbook
from test_progress import PEOPLE


def window(tmp_path,monkeypatch):
    from newxky import ui
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui.MainWindow,"restore_bank",lambda self:None)
    def immediate(self,function,result,error,progress=None):
        try:
            value = function(lambda *a:None)
        except Exception as failure:
            error(str(failure))
        else:
            result(value)
    monkeypatch.setattr(ui.MainWindow,"launch",immediate)
    return app,ui.MainWindow(tmp_path)


def test_counter_only_increases_on_confirmed_success_and_survives_restart(tmp_path,monkeypatch):
    app,first = window(tmp_path,monkeypatch)
    first.auto_finished({"submitted":False,"reason":"未交卷","records":[],"session_id":"one"})
    assert first.completed_total == 0
    report = {"submitted":True,"reason":"确认交卷","records":[],"session_id":"one"}
    first.auto_finished(report)
    first.auto_finished(dict(report))
    assert first.completed_total == 1 and "1 人" in first.completion_label.text()
    first.close()
    _,second = window(tmp_path,monkeypatch)
    assert second.completed_total == 1
    second.auto_finished(dict(report,session_id="two"))
    assert second.completed_total == 2
    second.close()


def test_saved_folder_loads_all_workbooks_on_next_start(tmp_path,monkeypatch):
    folder = tmp_path/"input"
    workbook(folder/"one.xlsx",[PEOPLE[0].key])
    workbook(folder/"two.xlsx",[c.key for c in PEOPLE])
    app,first = window(tmp_path,monkeypatch)
    first.people_folder = str(folder)
    first._save_settings()
    first.close()
    _,second = window(tmp_path,monkeypatch)
    app.processEvents()
    assert second.people_folder == str(folder)
    assert len(second.candidates) == 2
    assert (tmp_path/"人员记录/未完成/未完成总表.xlsx").is_file()
    second.close()


class Drop:
    def __init__(self,source,position):
        self.origin,self.point,self.accepted = source,position,False
    def source(self):return self.origin
    def position(self):return QPointF(self.point)
    def setDropAction(self,action):self.action=action
    def accept(self):self.accepted=True
    def ignore(self):self.accepted=False


def test_cross_list_drop_moves_people_both_ways_and_keeps_queue_order(tmp_path,monkeypatch):
    app,ui = window(tmp_path,monkeypatch)
    ui.people_imported(IdentityImport(PEOPLE,[],"人员"))
    ui.show()
    app.processEvents()
    ui.candidate_list.item(1).setSelected(True)
    drop = Drop(ui.candidate_list,ui.waiting_list.viewport().rect().bottomRight())
    ui.waiting_list.dropEvent(drop)
    assert drop.accepted and drop.action == Qt.CopyAction
    assert [r.candidate.key for r in ui.people.pending] == [PEOPLE[1].key]
    assert ui.candidate_list.count() == ui.waiting_list.count() == 1
    ui.candidate_list.item(0).setSelected(True)
    drop = Drop(ui.candidate_list,ui.waiting_list.visualItemRect(ui.waiting_list.item(0)).center())
    ui.waiting_list.dropEvent(drop)
    assert [r.candidate.key for r in ui.people.pending] == [c.key for c in PEOPLE]
    ui.waiting_list.setCurrentRow(0)
    ui.waiting_list.item(0).setSelected(True)
    drop = Drop(ui.waiting_list,ui.candidate_list.viewport().rect().center())
    ui.candidate_list.dropEvent(drop)
    assert drop.accepted
    assert [r.candidate.key for r in ui.people.pending] == [PEOPLE[1].key]
    assert ui.candidate_list.count() == ui.waiting_list.count() == 1
    ui.close()


def test_drops_are_rejected_while_automation_is_active(tmp_path,monkeypatch):
    app,ui = window(tmp_path,monkeypatch)
    ui.people_imported(IdentityImport(PEOPLE,[],"人员"))
    ui.candidate_list.item(0).setSelected(True)
    ui.auto.active=True
    ui.refresh_controls()
    drop = Drop(ui.candidate_list,ui.waiting_list.viewport().rect().center())
    ui.waiting_list.dropEvent(drop)
    assert not drop.accepted and not ui.people.records
    ui.auto.active=False
    ui.close()


def test_locked_history_keeps_a_retry_control_and_refreshes_standard_name(tmp_path,monkeypatch):
    from newxky.identities import load_identities
    app,ui = window(tmp_path,monkeypatch)
    replace = Path.replace
    destination = tmp_path/"人员记录/已完成/已完成总表.xlsx"
    with monkeypatch.context() as patch:
        def locked(source,target):
            if target == destination:
                raise PermissionError("simulated Excel lock")
            return replace(source,target)
        patch.setattr(Path,"replace",locked)
        ui.people_imported(IdentityImport(PEOPLE,[],"人员"))
        ui.people.add(PEOPLE[:1])
        ui._auto_person_position=0
        ui.auto_finished({"submitted":True,"reason":"确认交卷","records":[],"session_id":"locked-success"})
        assert ui.completed_total == 1 and not ui.results_retry.isHidden()
    ui.save_people_results()
    assert ui.results_retry.isHidden()
    assert load_identities(destination).candidates[0].key == PEOPLE[0].key
    ui.close()
