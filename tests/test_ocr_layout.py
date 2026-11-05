import pytest

from newxky.bank import normalized
from newxky.matching import KnowledgeIndex, screen_parts
from newxky.models import Question
from newxky.ocr import LocalOCR, _recognize_option_chip, option_chips, text_from_rows


def row(left, top, text, width=500, height=24):
    return ([[left, top], [left + width, top],
             [left + width, top + height], [left, top + height]], text, .99)


def card_rows(stem, options, *, inline=False):
    rows = [row(180, 20, stem)]
    top = 110
    for label, fragments in options.items():
        height = 24 + (len(fragments) - 1) * 38
        if inline:
            rows.append(row(20, top, label + ". " + fragments[0]))
        else:
            rows.append(row(20, top + height / 2 - 7, label, width=12, height=14))
            rows.append(row(65, top, fragments[0]))
        rows.extend(row(65, top + i * 38, text) for i, text in enumerate(fragments[1:], 1))
        top += height + 60
    rows.append(row(400, top, "上一题 下一题 提交答卷"))
    # OCR engines do not necessarily return boxes in reading order.
    return list(reversed(rows))


@pytest.mark.parametrize("wrapped", "ABCD")
@pytest.mark.parametrize("line_count", [2, 4, 6])
def test_centred_labels_keep_all_lines_in_their_own_option(wrapped, line_count):
    stem = "下列哪一项符合题目要求？（）"
    options = {label: [f"{name}选项内容"] for label, name in zip("ABCD", "甲乙丙丁")}
    options[wrapped].extend(f"换行内容{index}" for index in range(1, line_count))
    # The visible letters differ from the bank's letters.
    q = Question(1, "单选", stem,
                 dict(zip("ABCD", ("".join(options[k]) for k in "BCDA"))), ("A",), (1,))
    text = text_from_rows(card_rows(stem, options))
    actual_stem, actual_options = screen_parts(text)
    assert normalized(actual_stem) == normalized(stem)
    assert {k: normalized(v) for k, v in actual_options.items()} == {
        k: normalized("".join(v)) for k, v in options.items()
    }
    result = KnowledgeIndex([q]).lookup(text)
    assert result.status == "matched" and result.answers == ("B",)


def test_reported_first_option_stays_out_of_stem():
    stem = "全面依法治国的核心是下列哪一选项？（）"
    values = ["坚持依法治国、依法执政、依法行政共同推进，法治国家、法治政府、法治社会一体建设",
              "坚持依宪治国、依宪执政", "坚持建设中国特色社会主义法治体系",
              "坚持党的领导、人民当家作主、依法治国有机统一"]
    q = Question(18, "单选", stem, dict(zip("ABCD", values[1:] + values[:1])), ("C",), (6,))
    rows = [row(336, 26, stem, height=26),
            row(224, 117, "坚持依法治国、依法执政、依法行政共同推进，法治国家、", height=25),
            row(178, 141, "A", width=11, height=13),
            row(223, 155, "法治政府、法治社会一体建设", height=25)]
    for label, value, top in zip("BCD", values[1:], [241, 328, 415]):
        rows.extend([row(224, top, value), row(178, top + 5, label, width=11, height=14)])
    result = KnowledgeIndex([q]).lookup(text_from_rows(rows))
    assert result.status == "matched" and result.answers == ("D",)


def test_reported_wrapped_c_does_not_contaminate_b():
    stem = "关于重要数据目录，下列说法正确的是（ ）"
    options = {
        "A": ["目录由数据处理者自行编制确定，报行业主管部门备案"],
        "B": ["目录应当完整载明数据内容本身"],
        "C": ["目录主要包括数据基本情况、责任主体情况、数据处理情况、", "数据安全情况等，不包括数据内容本身"],
        "D": ["目录一经确定即不得调整"],
    }
    q = Question(329, "单选", stem,
                 dict(zip("ABCD", ("".join(options[k]) for k in "BCAD"))), ("B",), (95,))
    result = KnowledgeIndex([q]).lookup(text_from_rows(card_rows(stem, options)))
    assert result.status == "matched" and result.answers == ("C",)


def test_mixed_inline_and_centred_labels():
    stem = "选择正确内容（）"
    options = {"A": ["第一段", "第二段"], "B": ["乙"], "C": ["丙"], "D": ["丁"]}
    rows = card_rows(stem, options, inline=True)
    rows = [item for item in rows if not item[1].startswith("A.")]
    rows.extend([row(65, 110, "第一段"), row(20, 134, "A", width=12, height=14)])
    actual_stem, actual_options = screen_parts(text_from_rows(rows))
    assert normalized(actual_stem) == normalized(stem)
    assert normalized(actual_options["A"]) == "第一段第二段"
    assert normalized(actual_options["B"]) == "乙"


@pytest.mark.parametrize("old,new", [("允许", "不允许"), ("1.5", "15")])
def test_layout_recovery_does_not_accept_changed_option_meaning(old, new):
    stem = "下列说法正确的是（）"
    options = {"A": [f"标准{old}", "符合要求"], "B": ["内容乙"], "C": ["内容丙"], "D": ["内容丁"]}
    q = Question(1, "单选", stem, {k: "".join(v) for k, v in options.items()}, ("A",), (1,))
    options["A"][0] = options["A"][0].replace(old, new)
    result = KnowledgeIndex([q]).lookup(text_from_rows(card_rows(stem, options)))
    assert result.status == "unverified" and not result.answers


def test_layout_recovery_does_not_invent_missing_letters():
    stem = "下列说法正确的是（）"
    options = {"A": ["第一行", "第二行"], "B": ["内容乙"], "C": ["内容丙"], "D": ["内容丁"]}
    rows = [item for item in card_rows(stem, options) if item[1] != "A"]
    _, actual_options = screen_parts(text_from_rows(rows))
    assert "A" not in actual_options


def test_duplicate_labels_are_not_reassigned_between_questions():
    stem, other_stem = "这是第一道完整题目（）", "这是第二道完整题目（）"
    options = {"A": ["第一行", "第二行"], "B": ["内容乙"], "C": ["内容丙"], "D": ["内容丁"]}
    first = Question(1, "单选", stem, {k: "".join(v) for k, v in options.items()}, ("A",), (1,))
    second = Question(2, "单选", other_stem, first.options, ("B",), (1,))
    rows = card_rows(stem, options)
    for box, text, confidence in card_rows(other_stem, options):
        rows.append(([[x, y + 800] for x, y in box], text, confidence))
    result = KnowledgeIndex([first, second]).lookup(text_from_rows(rows))
    assert result.status == "ambiguous" and not result.answers


@pytest.mark.parametrize("badge_score", [.99, .72, .2])
def test_badge_reread_replaces_only_the_glyph_inside_its_bounds(monkeypatch, badge_score):
    import cv2
    import numpy as np

    pixels = np.full((90, 500, 3), 255, np.uint8)
    content = cv2.imencode(".png", pixels)[1].tobytes()
    rows = [row(15, 35, "巴", width=10, height=12), row(65, 30, "巴西的选项内容", width=200)]
    monkeypatch.setattr("newxky.ocr.option_chips", lambda _: [(10, 30, 20, 24)])
    ocr = LocalOCR()
    ocr._engine = lambda image, use_det=True: list(rows) if use_det else [["B", badge_score]]
    text = ocr.recognize(content)
    assert "巴西的选项内容" in text
    if badge_score >= .7:
        assert text == "B 巴西的选项内容"
    else:
        assert text == "巴 巴西的选项内容"


def test_missing_first_badge_uses_corroborated_screen_order():
    stem = "中央部门工作会议原则上只开到（）一级。"
    q = Question(1, "单选", stem, {"A": "省部", "B": "地市", "C": "县区", "D": "乡镇"}, ("A",), (1,))
    text = stem + "\n省部\nB 乡镇\nC 县区\nD 地市"
    result = KnowledgeIndex([q]).lookup(text)
    assert result.status == "matched" and result.answers == ("A",)
    assert "当前画面" in result.message and result.options["B"] == "乡镇"


@pytest.mark.parametrize("change", [
    lambda text: text.replace("原则上", "原则上不"),
    lambda text: text.replace("省部", "省级"),
    lambda text: text.replace("地市", "地县"),
    lambda text: text.replace("\n省部", "省部"),
])
def test_missing_badge_reference_requires_exact_stem_options_and_line_boundary(change):
    stem = "中央部门工作会议原则上只开到（）一级。"
    q = Question(1, "单选", stem, {"A": "省部", "B": "地市", "C": "县区", "D": "乡镇"}, ("A",), (1,))
    text = change(stem + "\n省部\nB 乡镇\nC 县区\nD 地市")
    assert not KnowledgeIndex([q]).lookup(text).answers


def test_missing_badge_reference_remains_ambiguous_for_conflicting_answers():
    stem = "中央部门工作会议原则上只开到（）一级。"
    options = {"A": "省部", "B": "地市", "C": "县区", "D": "乡镇"}
    questions = [Question(1, "单选", stem, options, answer, (1,)) for answer in [("A",), ("B",)]]
    result = KnowledgeIndex(questions).lookup(stem + "\n省部\nB 乡镇\nC 县区\nD 地市")
    assert result.status == "ambiguous" and not result.answers


def test_small_badges_are_kept_without_treating_body_strokes_as_badges():
    import cv2
    import numpy as np

    pixels = np.full((240, 600, 3), 255, np.uint8)
    for y in [45, 105, 165]:
        cv2.rectangle(pixels, (12, y), (24, y + 12), (160, 160, 160), 1)
        cv2.rectangle(pixels, (70, y), (84, y + 14), (20, 20, 20), 1)
    chips = option_chips(pixels)
    assert len(chips) == 3
    assert all(x < 30 for x, _, _, _ in chips)


def test_background_warmup_and_first_recognition_share_one_engine(monkeypatch):
    import time
    from concurrent.futures import ThreadPoolExecutor

    created = []
    def create_engine():
        time.sleep(.02)
        engine = object()
        created.append(engine)
        return engine
    monkeypatch.setattr("newxky.ocr_engine.OCREngine", create_engine)
    ocr = LocalOCR()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: ocr.warmup(), range(4)))
    assert created == [ocr._engine]


def test_small_badge_consensus_rejects_disagreeing_letters():
    import numpy as np

    crop = np.full((10, 8, 3), 255, np.uint8)
    crop[2:8, 2:6] = 80
    outputs = iter([["B", .75], ["D", .76], ["B", .74], ["D", .73], ["B", .74]])
    assert _recognize_option_chip(lambda image, use_det: [next(outputs)], crop) is None


@pytest.mark.parametrize("visible_letters", [set(), {"B"}, {"A", "D"}])
def test_complete_unlabelled_contents_disambiguate_shared_stem(visible_letters):
    stem = "根据本条例，以下说法正确的是（）"
    values = {"A": "甲的完整内容", "B": "乙的完整内容", "C": "丙的完整内容", "D": "丁的完整内容"}
    q = Question(1, "多选", stem, values, ("A", "C"), (1,))
    other = Question(2, "多选", stem, dict(values, C="另一份题目的选项"), ("B",), (2,))
    text = stem + "\n" + "\n".join((label + " " if label in visible_letters else "") + value
                                       for label, value in values.items())
    result = KnowledgeIndex([q, other]).lookup(text)
    assert result.status == ("matched" if visible_letters == {"A", "D"} else "reference")
    assert result.question == q and result.answers == ("A", "C")
    assert "全部选项内容已核对" in result.message


@pytest.mark.parametrize("extra", ["附加内容", "甲的完整内容"])
def test_unlabelled_content_recovery_does_not_discard_extra_or_duplicate_text(extra):
    stem = "选择正确内容（）"
    values = {"A": "甲的完整内容", "B": "乙的完整内容"}
    q = Question(1, "单选", stem, values, ("A",), (1,))
    text = stem + "\n" + "\n".join(values.values()) + "\n" + extra
    assert not KnowledgeIndex([q]).lookup(text).answers
