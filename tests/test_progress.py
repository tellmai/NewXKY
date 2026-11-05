from datetime import datetime
from pathlib import Path

from newxky.identities import Candidate,load_identities
from newxky.progress import ProgressJournal


PEOPLE = [Candidate(2,"演示区","演示甲","11010119900101001X"),
          Candidate(3,"演示区","演示乙","110101199001010011")]


def test_success_receipts_persist_and_duplicate_callbacks_do_not_increase_count(tmp_path):
    first = ProgressJournal(tmp_path)
    first.register(PEOPLE)
    assert first.record_success("session-one",PEOPLE[0]) == 1
    assert first.record_success("session-one",PEOPLE[0]) == 1
    reopened = ProgressJournal(tmp_path)
    assert reopened.total == 1
    assert reopened.record_success("session-one",PEOPLE[1]) == 1
    assert reopened.record_success("session-two",PEOPLE[1]) == 2


def test_daily_and_total_workbooks_keep_prior_dates_and_pending_people(tmp_path):
    moment = [datetime(2026,11,5,9)]
    journal = ProgressJournal(tmp_path,clock=lambda:moment[0])
    journal.register(PEOPLE)
    journal.record_success("first",PEOPLE[0])
    journal.export()
    assert [c.key for c in load_identities(tmp_path/"已完成/已完成2026-11-05.xlsx").candidates] == [PEOPLE[0].key]
    assert [c.key for c in load_identities(tmp_path/"未完成/未完成总表.xlsx").candidates] == [PEOPLE[1].key]
    moment[0] = datetime(2026,11,6,9)
    journal.record_success("second",PEOPLE[1])
    journal.export()
    assert len(load_identities(tmp_path/"已完成/已完成总表.xlsx").candidates) == 2
    assert len(load_identities(tmp_path/"已完成/已完成2026-11-05.xlsx").candidates) == 1
    assert [c.key for c in load_identities(tmp_path/"已完成/已完成2026-11-06.xlsx").candidates] == [PEOPLE[1].key]
    assert not load_identities(tmp_path/"未完成/未完成总表.xlsx").candidates


def test_locked_excel_keeps_durable_success_and_saves_an_updated_copy(tmp_path,monkeypatch):
    journal = ProgressJournal(tmp_path)
    journal.register(PEOPLE)
    journal.export()
    replace = Path.replace
    def locked(source,target):
        if target == tmp_path/"已完成/已完成总表.xlsx":
            raise PermissionError("simulated Excel lock")
        return replace(source,target)
    monkeypatch.setattr(Path,"replace",locked)
    journal.record_success("first",PEOPLE[0])
    result = journal.export()
    assert result["copies"] and journal.total == 1
    assert load_identities(result["copies"][0]).candidates[0].key == PEOPLE[0].key


def test_cumulative_records_distinguish_people_with_same_id_but_different_names(tmp_path):
    other = Candidate(4,PEOPLE[0].district,"另一个姓名",PEOPLE[0].id_number)
    journal = ProgressJournal(tmp_path)
    journal.register([PEOPLE[0],other])
    journal.record_success("first",PEOPLE[0])
    result = journal.export()
    assert result["completed"] == result["incomplete"] == 1
    assert load_identities(tmp_path/"未完成/未完成总表.xlsx").candidates[0].key == other.key
