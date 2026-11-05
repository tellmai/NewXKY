import pytest

from newxky.matching import KnowledgeIndex
from newxky.models import Question


def question(answers=("A", "C")):
    return Question(1, "多选", "下列哪些内容正确（）",
                    {"A": "甲的完整内容", "B": "乙的完整内容", "C": "丙的完整内容", "D": "丁的完整内容"},
                    answers, (1,), "题库.pdf")


def screen(q, visible):
    return q.stem + "\n" + "\n".join(
        (label + " " if label in visible else "") + q.options[old]
        for label, old in zip("ABCD", "CADB")
    )


@pytest.mark.parametrize("visible", [{"A", "D"}, {"B", "D"}, {"A", "C"}])
def test_two_consistent_anchors_restore_shuffled_multiple_answers(visible):
    q = question()
    result = KnowledgeIndex([q]).lookup(screen(q, visible))
    assert result.status == "matched" and result.answers == ("A", "B")
    assert result.options["A"] == q.options["C"]
    assert result.options["B"] == q.options["A"]


def test_correct_option_with_a_visible_letter_needs_no_other_badges():
    q = question(answers=("D",))
    result = KnowledgeIndex([q]).lookup(screen(q, {"C"}))
    assert result.status == "matched" and result.answers == ("C",)
    assert result.options["C"] == q.options["D"]


def test_one_unrelated_badge_is_not_enough_to_infer_the_missing_answer():
    q = question(answers=("A",))
    result = KnowledgeIndex([q]).lookup(screen(q, {"A"}))
    assert result.status == "reference" and result.answers == ("A",)
    assert "题库顺序" in result.message


def test_conflicting_letter_positions_do_not_restore_missing_labels():
    q = question(answers=("B",))
    text = screen(q, {"A", "C"}).replace("C 丁", "D 丁")
    result = KnowledgeIndex([q]).lookup(text)
    assert result.status == "reference" and result.answers == ("B",)


def test_similar_question_keeps_a_separate_reference_status():
    q = question()
    text = screen(q, set("ABCD")).replace("哪些", "哪种")
    result = KnowledgeIndex([q]).lookup(text)
    assert result.status == "candidate" and result.question == q
    assert not result.answers and "仅供参考" in result.message


def test_content_with_two_possible_orders_does_not_infer_missing_labels():
    q = Question(1, "单选", "选择正确内容（）",
                 {"A": "甲", "B": "甲甲", "C": "乙", "D": "丙"}, ("B",), (1,))
    result = KnowledgeIndex([q]).lookup(q.stem + "\nA 甲甲甲\n乙\nD 丙")
    assert result.status == "reference" and result.answers == ("B",)
