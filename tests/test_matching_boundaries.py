from pathlib import Path

import pytest

from newxky.bank import read_bank
from newxky.matching import KnowledgeIndex
from newxky.models import Question


@pytest.fixture(scope="module")
def bank_index():
    bank = read_bank(Path(__file__).resolve().parents[1] / "题库/default-bank.json")
    return KnowledgeIndex(bank.questions)


def screen(question, order=None):
    order = order or tuple(question.options)
    return question.stem + "\n" + "\n".join(
        f"{label}. {question.options[old]}"
        for label, old in zip(question.options, order)
    )


@pytest.mark.parametrize("number", [564, 689, 844, 845])
@pytest.mark.parametrize("order", ["ABCD", "DCBA", "CADB"])
def test_reported_bank_questions_match_with_reordered_options(bank_index, number, order):
    question = next(q for q in bank_index.questions if q.number == number)
    result = bank_index.lookup(screen(question, order))
    assert result.status == "matched"
    assert result.question is question
    assert result.answers == tuple(label for label, old in zip("ABCD", order)
                                   if old in question.answers)


def test_every_complete_bundled_question_matches_its_own_bank_entry(bank_index):
    failures = []
    for question in bank_index.questions:
        result = bank_index.lookup(screen(question))
        if result.status != "matched" or result.question is not question:
            failures.append((question.number, result.status, result.message))
    assert failures == []


@pytest.mark.parametrize("separator", ["\n", "\n下一题\n"])
def test_a_stem_quoted_in_an_option_does_not_hide_a_later_question(separator):
    other = Question(2, "判断", "这是第二道题的完整陈述", {"A": "对", "B": "错"}, ("A",), (2,))
    first = Question(1, "单选", "请选择正确描述", {
        "A": other.stem + "，后面还有补充内容", "B": "其他描述",
    }, ("B",), (1,))
    index = KnowledgeIndex([first, other])
    assert index.lookup(screen(first)).status == "matched"
    result = index.lookup(screen(first) + separator + other.stem)
    assert result.status == "ambiguous" and result.question is None


def test_duplicate_options_with_conflicting_correctness_stay_ambiguous():
    question = Question(1, "单选", "选择正确内容", {
        "A": "相同内容", "B": "相同内容", "C": "不同内容",
    }, ("A",), (1,))
    result = KnowledgeIndex([question]).lookup(screen(question))
    assert result.status == "ambiguous" and not result.answers


def test_duplicate_option_counts_must_match():
    question = Question(1, "多选", "选择正确内容", {
        "A": "甲的内容", "B": "甲的内容", "C": "乙的内容",
    }, ("A", "B"), (1,))
    result = KnowledgeIndex([question]).lookup(
        screen(question).replace("B. 甲的内容", "B. 乙的内容"))
    assert result.status != "matched" and not result.answers


def test_partial_card_requires_every_copy_of_a_duplicate_correct_option(bank_index):
    question = next(q for q in bank_index.questions if q.number == 845)
    text = question.stem + "\nA. " + question.options["A"] + "\nB. " + question.options["B"]
    result = bank_index.lookup(text)
    assert result.status != "matched" and not result.answers
    assert result.question is question


@pytest.mark.parametrize("number", [564, 689, 844, 845])
def test_partial_shared_stems_can_be_identified_by_complete_visible_options(bank_index, number):
    question = next(q for q in bank_index.questions if q.number == number)
    text = question.stem + "\n" + "\n".join(
        f"{label}. {question.options[label]}" for label in "AB")
    result = bank_index.lookup(text)
    assert result.question is question
    assert result.status != "ambiguous"


def test_every_bundled_question_can_be_collected_from_two_overlapping_frames(bank_index):
    from newxky.scroll_scan import ScrollReader, complete_match

    failures = []
    for question in bank_index.questions:
        labels = list(question.options)
        split = max(1, len(labels) // 2)
        upper = question.stem + "\n" + "\n".join(
            f"{label}. {question.options[label]}" for label in labels[:split])
        lower = "\n".join(f"{label}. {question.options[label]}" for label in labels[split - 1:])
        reader = ScrollReader(bank_index)
        first = reader.feed(upper, bank_index.lookup(upper))
        last = reader.feed(lower, bank_index.lookup(lower))
        if (first.direction != -1 or not complete_match(last.match)
                or last.match.question is not question or last.match.answers != question.answers):
            failures.append((question.number, first.match.status, last.match.status))
    assert failures == []
