from newxky.matching import KnowledgeIndex
from newxky.models import Question


def question(number, stem, options=None, answers=("A",)):
    return Question(number, "单选", stem, options or {"A": "正确内容", "B": "其他内容"}, answers, (3,), "题库.pdf")


def test_keyword_search_covers_stems_options_and_all_words():
    first = question(1, "关于重要数据目录，下列说法正确的是（）", {"A": "不包括数据内容本身", "B": "其他内容"})
    second = question(2, "其他题目", {"A": "重要数据", "B": "目录情况"})
    excluded = question(3, "重要数据的管理方式")
    index = KnowledgeIndex([first, second, excluded])
    assert index.search("重要数据 目录") == [first, second]
    assert index.search("不包括 数据内容") == [first]
    assert index.search("没有收录的内容") == []


def test_keyword_search_ranks_stem_matches_before_option_matches():
    option_match = question(1, "其他题目", {"A": "关键词", "B": "其他"})
    stem_match = question(2, "题干包含关键词")
    assert KnowledgeIndex([option_match, stem_match]).search("关键词") == [stem_match, option_match]


def test_keyword_search_normalizes_punctuation_and_ignores_empty_input():
    q = question(1, "Alpha法第１条（）")
    index = KnowledgeIndex([q])
    assert index.search("ALPHA 第1条") == [q]
    for query in ["", "  ", "（）", "， 。"]:
        assert index.search(query) == []
    assert KnowledgeIndex([]).search("题目") == []


def test_search_preserves_each_questions_own_answer_and_source():
    first = question(1, "相同题干", answers=("A",))
    second = question(2, "相同题干", answers=("B",))
    results = KnowledgeIndex([first, second]).search("相同题干")
    assert [q.answers for q in results] == [("A",), ("B",)]
    assert all(q.source == "题库.pdf" and q.pages == (3,) for q in results)
