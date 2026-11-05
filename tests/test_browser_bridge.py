import pytest

from newxky.browser_bridge import decode_snapshot,dialog_from_message


def test_dom_snapshot_contains_full_options_even_outside_the_visible_viewport():
    data={"stem":"测试题目（）","number":47,"total":100,"answered":46,
          "options":[{"letter":"A","text":"选项甲","selected":False},{"letter":"C","text":"正确内容","selected":True}],
          "controls":{"next":{"enabled":True},"submit":{"enabled":True}},"revision":"example"}
    layout,view,dialog=decode_snapshot(data)
    assert view.source=="dom" and view.number==47 and view.options[1].selected
    assert view.controls["next"].enabled and dialog.kind=="unknown"


@pytest.mark.parametrize("message,expected",[("全部题目已完成，检查完成。","checked"),("确定提交答卷吗？","confirm"),
    ("还有2题未完成，请检查","incomplete"),("确定删除资料吗？","blocked"),("请等待15秒再交卷","wait")])
def test_native_browser_dialogs_are_classified_by_their_own_message(message,expected):
    assert dialog_from_message(message).kind==expected


def test_dom_snapshot_rejects_duplicate_labels_and_multiple_questions():
    with pytest.raises(ValueError):
        decode_snapshot({"stem":"题目","options":[{"letter":"A","text":"甲"},{"letter":"A","text":"乙"}]})


def test_html_modal_without_an_actual_confirm_control_is_not_clickable():
    _,_,dialog=decode_snapshot({"stem":"题目","options":[],"dialog":{"message":"确定提交答卷吗？","buttons":["取消"]}})
    assert dialog.kind=="confirm" and dialog.control is None
