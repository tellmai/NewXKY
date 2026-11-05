import pytest

from newxky.matching import KnowledgeIndex
from newxky.models import Question


def question():
    return Question(1, "多选", "关于对违法犯罪党员的纪律处分，以下说法正确的是（）。", {
        "A": "对违法犯罪的党员，不按照规定给予党纪处分，直接适用法律",
        "B": "党组织在纪律审查中发现党员有贪污贿赂、滥用职权、玩忽职守、权力寻租、利益输送、徇私舞弊、浪费国家资财等违反法律涉嫌犯罪行为的，应当给予撤销党内职务、留党察看或者开除党籍处分",
        "C": "党员有嫖娼或者吸食、注射毒品等丧失党员条件，严重败坏党的形象行为的，应当给予开除党籍处分",
        "D": "党员被依法留置、逮捕的，党组织应当按照管理权限中止其表决权、选举权和被选举权等党员权利",
    }, ("B", "C", "D"), (164, 165), "题库.pdf")


def screen(q):
    return q.stem + "\n" + "\n".join(f"{label} {q.options[old]}" for label, old in zip("ABCD", "DCBA"))


def test_reported_missing_characters_keep_a_warned_reference_in_screen_order():
    q = question()
    result = KnowledgeIndex([q]).lookup(screen(q).replace("嫖娼", "").replace("舞弊", "舞"))
    assert result.status == "unverified" and not result.answers
    assert result.reference.screen_order
    assert result.reference.answers == ("A", "B", "C")
    assert result.reference.options["B"] == q.options["C"]
    assert result.reference.options["C"] == q.options["B"]
    assert "仅供参考" in result.message


@pytest.mark.parametrize("old,new", [("中止", "不中止"), ("按照", "不按照"), ("管理权限", "管理权限5")])
def test_similar_options_with_changed_meaning_never_become_verified_answers(old, new):
    q = question()
    result = KnowledgeIndex([q]).lookup(screen(q).replace(old, new))
    assert result.status == "unverified" and not result.answers
    assert result.reference.screen_order and result.reference.answers == ("A", "B", "C")
    assert "仅供参考" in result.message


def test_near_identical_choices_do_not_infer_reference_letters():
    q = Question(2, "单选", "选出正确规定（）", {
        "A": "有关机关必须依法按照法定权限及时处理", "B": "有关机关不得依法按照法定权限及时处理",
        "C": "其他完全无关的选项内容", "D": "另一项完全不同的说明内容",
    }, ("B",), (1,))
    text = q.stem + "\nA 有关机关依法按照法定权限及时处理\nB " + q.options["B"] + "\nC " + q.options["C"] + "\nD " + q.options["D"]
    result = KnowledgeIndex([q]).lookup(text)
    assert result.status == "unverified" and not result.answers
    assert not result.reference.screen_order
    assert result.reference.answers == q.answers and result.reference.options == q.options


def test_different_or_duplicate_contents_keep_the_bank_reference():
    q = question()
    for replacement in (q.options["B"], "这是完全不同的选项内容"):
        result = KnowledgeIndex([q]).lookup(screen(q).replace(q.options["A"], replacement))
        assert result.status == "unverified" and not result.answers
        assert not result.reference.screen_order and result.reference.answers == q.answers


def test_conflicting_bank_answers_do_not_provide_a_reference():
    q = question()
    other = Question(2, q.kind, q.stem, q.options, ("A",), (1,))
    result = KnowledgeIndex([q, other]).lookup(screen(q).replace("嫖娼", ""))
    assert result.status == "ambiguous" and result.reference is None and not result.answers
