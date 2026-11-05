import pytest

from newxky.bank import merge_banks, parse_lines, read_bank, save_bank
from newxky.matching import KnowledgeIndex
from newxky.models import Bank, Question
from newxky.monitor import FrameTracker
from newxky.ocr import text_from_rows


def question(stem="下列哪一项属于依法行政的要求（）", answer=("B",)):
    return Question(1, "单选", stem, {"A": "任意扩大权限", "B": "依照法定权限和程序履行职责", "C": "以个人意见代替法律", "D": "不接受监督"}, answer, (1, 2), "题库.pdf")


def screen(q, order=("A", "B", "C", "D")):
    return "单选题\n1. " + q.stem + "\n" + "\n".join(f"{letter}. {q.options[old]}" for letter, old in zip("ABCD", order))


def test_pdf_cross_page_and_section_numbers():
    lines = [(1, "2026 年度法治理论知识考试复习资料"), (1, "一、单选题"), (1, "1、题干第一行"), (2, "题干第二行"),
             (2, "A. 甲"), (2, "B. 乙"), (2, "正确答案：B"), (2, "二、多选题"), (2, "1、另一道题"),
             (2, "A. 丙"), (2, "B. 丁"), (2, "正确答案：A、B")]
    bank = parse_lines(lines, 2, "中文.pdf")
    assert not bank.issues
    assert [q.kind for q in bank.questions] == ["单选", "多选"]
    assert bank.questions[0].stem == "题干第一行题干第二行"
    assert bank.questions[0].pages == (1, 2)
    assert bank.questions[1].answers == ("A", "B")


def test_invalid_answers_are_reported_and_not_added():
    bank = parse_lines([(1, x) for x in ["1、缺答案", "A. 甲", "B. 乙", "2、答案不存在", "A. 甲", "正确答案：D"]], 1)
    assert len(bank.issues) == 2
    assert bank.questions == []


def test_storage_and_conflicting_import_is_transactional(tmp_path):
    q = question()
    path = tmp_path / "bank.json"
    old = Bank([q], sources=["题库.pdf"], page_count=2)
    save_bank(old, path)
    assert read_bank(path) == old
    assert merge_banks([old, old]).duplicates == 1
    with pytest.raises(ValueError, match="答案冲突"):
        merge_banks([old, Bank([question(answer=("A",))])])
    assert read_bank(path) == old


def test_shuffled_options_use_screen_letters():
    q = question()
    result = KnowledgeIndex([q]).lookup(screen(q, ("B", "D", "A", "C")))
    assert result.status == "matched"
    assert result.answers == ("A",)


def test_multiple_answers_and_split_ocr_labels():
    q = question(answer=("A", "C"))
    text = screen(q, ("B", "D", "A", "C")).replace(". ", ".\n")
    result = KnowledgeIndex([q]).lookup(text)
    assert result.status == "matched" and result.answers == ("C", "D")


@pytest.mark.parametrize("alter", [lambda t: t.replace("属于", "不属于")])
def test_changed_negation_never_yields_answer(alter):
    q = question()
    result = KnowledgeIndex([q]).lookup(alter(screen(q)))
    assert result.status != "matched" and not result.answers


def test_incomplete_options_use_the_visible_correct_answer_letter():
    q = question()
    text = screen(q)
    result = KnowledgeIndex([q]).lookup(text[:text.rfind("\nD.")])
    assert result.status == "matched" and result.answers == ("B",)
    assert result.options["B"] == q.options["B"]


def test_incomplete_options_keep_bank_reference_when_correct_content_is_missing():
    q = question(answer=("D",))
    text = screen(q)
    result = KnowledgeIndex([q]).lookup(text[:text.rfind("\nD.")])
    assert result.status == "reference" and result.answers == ("D",)


def test_complete_changed_options_do_not_fall_back_to_bank_letters():
    q = question()
    result = KnowledgeIndex([q]).lookup(screen(q).replace("法定", "任意"))
    assert result.status == "unverified" and not result.answers


def test_stem_only_shows_bank_answers_and_contents():
    q = question(answer=("A", "C"))
    result = KnowledgeIndex([q]).lookup(q.stem)
    assert result.status == "reference" and result.answers == ("A", "C")
    assert result.options["C"] == q.options["C"]


def test_partial_question_with_conflicting_answers_stays_ambiguous():
    q = question()
    assert KnowledgeIndex([q, question(answer=("A",))]).lookup(q.stem).status == "ambiguous"


def test_exam_card_type_and_question_number_are_not_part_of_stem():
    q = question()
    result = KnowledgeIndex([q]).lookup("多选题·可多选 64\n" + screen(q).split("\n", 1)[1])
    assert result.status == "matched"


def test_unknown_and_empty_region_never_yield_answer():
    index = KnowledgeIndex([question()])
    assert index.lookup("").status == "unreadable"
    assert index.lookup("一道没有收录的题目").status == "missing"


def test_extra_leading_negation_is_not_discarded_as_a_header():
    q = question("允许使用该方法")
    assert not KnowledgeIndex([q]).lookup(screen(q).replace(q.stem, "不" + q.stem)).answers


@pytest.mark.parametrize("old,new", [("1.5", "15"), ("-15", "15"), ("5%", "5")])
def test_numeric_meaning_survives_normalization(old, new):
    q = question(f"标准为{old}时符合要求")
    assert not KnowledgeIndex([q]).lookup(screen(q).replace(old, new)).answers


def test_conflict_in_cache_cannot_yield_answer():
    q = question()
    assert KnowledgeIndex([q, question(answer=("A",))]).lookup(screen(q)).status == "ambiguous"


def test_two_visible_questions_are_ambiguous():
    q, other = question(), question("这是第二道完整题目")
    result = KnowledgeIndex([q, other]).lookup(screen(q) + "\n" + screen(other))
    assert result.status == "ambiguous" and not result.answers


def test_generic_stem_nested_inside_full_stem_is_one_question():
    q = question("根据本条例，以下说法正确的是（）")
    generic = question("以下说法正确的是（）", answer=("A",))
    index = KnowledgeIndex([q, generic])
    result = index.lookup(screen(q))
    assert result.status == "matched" and result.answers == ("B",)
    second_question = index.lookup(screen(q) + "\n" + screen(generic))
    assert second_question.status == "ambiguous" and not second_question.answers


@pytest.mark.parametrize("tag", ["多造明·可多造 95", "多造圆·可多造 95", "多选题·可多选 95"])
def test_small_decorative_type_badge_is_not_added_to_stem(tag):
    q = question()
    result = KnowledgeIndex([q]).lookup(tag + "\n" + screen(q).split("\n", 1)[1])
    assert result.status == "matched" and result.answers == ("B",)


def test_inflight_old_frame_cannot_replace_new_frame():
    tracker = FrameTracker()
    assert tracker.observe(b"first question", 0)
    assert not tracker.ready(.1)
    assert tracker.ready(.5)
    first = tracker.begin()
    tracker.observe(b"second question", .7)
    assert not tracker.finish(first)
    assert tracker.ready(1.1)
    second = tracker.begin()
    assert tracker.finish(second)
    assert not tracker.ready(2)


def test_pause_or_reselect_discards_pending_ocr():
    tracker = FrameTracker()
    tracker.observe(b"question", 0)
    revision = tracker.begin()
    tracker.invalidate()
    assert not tracker.finish(revision)
    assert not tracker.busy


def test_fast_polling_still_waits_for_a_stable_current_frame():
    tracker = FrameTracker()
    tracker.observe(b"first", 0)
    assert not tracker.ready(.1)
    assert tracker.ready(.2)
    revision = tracker.begin()
    tracker.observe(b"changed", .21)
    assert not tracker.finish(revision)
    assert not tracker.ready(.3)
    assert tracker.ready(.41)


def test_ocr_line_order_keeps_repeated_words():
    def row(x, y, text):
        return ([[x, y], [x + 50, y], [x + 50, y + 20], [x, y + 20]], text, .99)
    text = text_from_rows([row(70, 30, "人人"), row(5, 0, "题干"), row(5, 30, "A.")])
    assert text == "题干\nA. 人人"
