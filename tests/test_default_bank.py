import pytest

from newxky import default_bank
from newxky.bank import read_bank,save_bank
from newxky.models import Bank,Question


def bank(stem="随包的完整题目",answer=("A",)):
    return Bank([Question(1,"单选",stem,{"A":"选项甲","B":"选项乙"},answer,(1,),"default.pdf")],
                sources=["default.pdf"],page_count=2)


def bundle(tmp_path,monkeypatch):
    pdf=tmp_path/"source/default.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"test PDF bytes")
    monkeypatch.setattr(default_bank,"load_pdf",lambda source:bank())
    app=tmp_path/"app"
    default_bank.prepare_bundle(pdf,app/default_bank.BUNDLE_DIRECTORY)
    return app


def test_first_start_uses_verified_bundled_cache_and_preserves_pdf_bytes(tmp_path,monkeypatch):
    app=bundle(tmp_path,monkeypatch)
    monkeypatch.setattr(default_bank,"load_pdf",lambda source:pytest.fail("valid cache should avoid PDF parsing"))
    data=tmp_path/"data"
    result,notes=default_bank.restore_startup_bank(data,app)
    assert len(result.questions)==1 and notes
    assert read_bank(data/"bank.json")==result
    assert (app/"题库/default.pdf").read_bytes()==b"test PDF bytes"


def test_custom_imports_remain_and_restarts_do_not_grow_counts_or_metadata(tmp_path,monkeypatch):
    app=bundle(tmp_path,monkeypatch)
    data=tmp_path/"data"
    save_bank(bank("用户的另一道题目"),data/"bank.json")
    first,_=default_bank.restore_startup_bank(data,app)
    before=(data/"bank.json").read_bytes()
    second,_=default_bank.restore_startup_bank(data,app)
    assert len(first.questions)==len(second.questions)==2
    assert first==second and (data/"bank.json").read_bytes()==before


def test_conflicting_local_answers_are_preserved_and_reported(tmp_path,monkeypatch):
    app=bundle(tmp_path,monkeypatch)
    data=tmp_path/"data"
    old=bank(answer=("B",))
    save_bank(old,data/"bank.json")
    before=(data/"bank.json").read_bytes()
    result,notes=default_bank.restore_startup_bank(data,app)
    assert result==old and (data/"bank.json").read_bytes()==before
    assert "冲突" in notes[0]


def test_corrupt_local_cache_does_not_block_default_or_destroy_original_file(tmp_path,monkeypatch):
    app=bundle(tmp_path,monkeypatch)
    data=tmp_path/"data"
    data.mkdir()
    (data/"bank.json").write_bytes(b"broken local cache")
    result,notes=default_bank.restore_startup_bank(data,app)
    assert len(result.questions)==1
    assert (data/"bank.json").read_bytes()==b"broken local cache"
    assert any("原缓存文件保留" in note for note in notes)


@pytest.mark.parametrize("damage",["cache","manifest","pdf"])
def test_changed_or_invalid_bundle_is_reparsed_from_the_pdf(tmp_path,monkeypatch,damage):
    app=bundle(tmp_path,monkeypatch)
    folder=app/default_bank.BUNDLE_DIRECTORY
    if damage=="cache":
        (folder/default_bank.CACHE_NAME).write_text("invalid cache",encoding="utf-8")
    elif damage=="manifest":
        # The conventional filename is still available without a valid manifest.
        pdf=folder/"default.pdf"
        pdf.rename(folder/default_bank.DEFAULT_PDF_NAME)
        (folder/default_bank.MANIFEST_NAME).write_text("[]",encoding="utf-8")
    else:
        (folder/"default.pdf").write_bytes(b"changed PDF bytes")
    calls=[]
    monkeypatch.setattr(default_bank,"load_pdf",lambda source:calls.append(source) or bank())
    result,_=default_bank.restore_startup_bank(tmp_path/"data",app)
    assert calls and len(result.questions)==1


def test_no_bundled_pdf_keeps_existing_local_behavior(tmp_path):
    data=tmp_path/"data"
    old=bank()
    save_bank(old,data/"bank.json")
    result,notes=default_bank.restore_startup_bank(data,tmp_path/"app")
    assert result==old and not notes
