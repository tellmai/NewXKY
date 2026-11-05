from openpyxl import Workbook

from newxky.identities import Candidate,ExamQueue,load_identity_folder


def workbook(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    book = Workbook()
    book.active.append(["所在的区县","姓名","身份证号"])
    for row in rows:
        book.active.append(row)
    book.save(path)
    book.close()


def test_folder_import_loads_all_files_and_deduplicates_only_complete_triples(tmp_path):
    first = ("演示区","演示甲","11010119900101001X")
    workbook(tmp_path/"a.xlsx",[first,first])
    workbook(tmp_path/"sub/b.xlsx",[first,("另一区",first[1],first[2]),(first[0],"演示乙",first[2])])
    workbook(tmp_path/"~$temporary.xlsx",[("临时区","忽略",first[2])])
    result = load_identity_folder(tmp_path)
    assert len(result.candidates) == 3 and result.files == 2 and result.duplicates == 2
    assert len({c.row for c in result.candidates}) == 3
    assert len({c.key for c in result.candidates}) == 3
    queue = ExamQueue()
    queue.add(result.candidates)
    queue.add(result.candidates)
    assert len(queue.records) == 3


def test_folder_import_skips_bad_workbook_and_generated_history(tmp_path):
    row = ("演示区","演示甲","11010119900101001X")
    workbook(tmp_path/"people.xlsx",[row])
    workbook(tmp_path/"人员记录/已完成/ignored.xlsx",[("别的区","历史",row[2])])
    (tmp_path/"bad.xlsx").write_text("not a workbook",encoding="utf-8")
    result = load_identity_folder(tmp_path,excluded=(tmp_path/"人员记录",))
    assert len(result.candidates) == 1 and result.files == 2 and len(result.issues) == 1
