from pathlib import Path

from newxky import default_bank
from newxky.bank import save_bank
from newxky.models import Bank, Question


def sample_bank(stem="随包的完整题目", answer=("A",)):
    return Bank(
        [Question(1, "单选", stem, {"A": "选项甲", "B": "选项乙"}, answer, (1,), "builtin.pdf")],
        sources=["builtin.pdf"], page_count=2,
    )


def test_loads_bundled_json_without_pdf(tmp_path):
    app = tmp_path / "app"
    folder = app / default_bank.BUNDLE_DIRECTORY
    folder.mkdir(parents=True)
    save_bank(sample_bank(), folder / default_bank.CACHE_NAME)
    bank, notes = default_bank.load_startup_bank(app)
    assert len(bank.questions) == 1
    assert bank.questions[0].stem == "随包的完整题目"
    assert "已加载" in notes[0]


def test_missing_bank_returns_actionable_note(tmp_path):
    bank, notes = default_bank.load_startup_bank(tmp_path / "app")
    assert bank.questions == []
    assert "未找到内置题库" in notes[0]


def test_corrupt_bank_returns_empty_and_note(tmp_path):
    app = tmp_path / "app"
    folder = app / default_bank.BUNDLE_DIRECTORY
    folder.mkdir(parents=True)
    (folder / default_bank.CACHE_NAME).write_text("not json", encoding="utf-8")
    bank, notes = default_bank.load_startup_bank(app)
    assert bank.questions == []
    assert "读取失败" in notes[0]
