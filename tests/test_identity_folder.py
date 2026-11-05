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
    workbook(tmp_path/"b.xlsx",[first,("另一区",first[1],first[2]),(first[0],"演示乙",first[2])])
    workbook(tmp_path/"sub/ignored.xlsx",[("嵌套区","不属于当前目录",first[2])])
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
    result = load_identity_folder(tmp_path)
    assert len(result.candidates) == 1 and result.files == 2 and len(result.issues) == 1


def test_two_root_files_produce_six_people_with_both_same_name_different_ids(tmp_path):
    district="演示区"
    shared=(district,"共同人员","110101199001010010")
    first=(district,"同名人员","110101199001010011")
    second=(district,"同名人员","110101199001010012")
    workbook(tmp_path/"a.xlsx",[shared,first,(district,"演示甲","110101199001010013")])
    workbook(tmp_path/"b.xlsx",[shared,second,(district,"演示乙","110101199001010014"),
                                 (district,"演示丙","110101199001010015")])
    workbook(tmp_path/"other/people.xlsx",[(district,"其他目录","110101199001010016")])
    result=load_identity_folder(tmp_path)
    assert result.files==2 and result.duplicates==1 and len(result.candidates)==6
    twins=[person for person in result.candidates if person.name==first[1]]
    assert len(twins)==2 and {person.key for person in twins}=={first,second}
