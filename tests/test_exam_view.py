import cv2
import numpy as np

from newxky.exam_view import parse_exam,parse_dialog
from newxky.ocr import OCRLayout,OCRLine,LocalOCR
from newxky.ocr_engine import CachedRecognizer


def line(x,y,text,w=150,h=22,confidence=.99):
    return OCRLine(((x,y),(x+w,y),(x+w,y+h),(x,y+h)),text,confidence)


def fixture(selected=False):
    pixels=np.full((700,1000,3),255,np.uint8)
    rows=[line(160,30,"这里是一道完整的测试题目（）",600)]
    for i,(letter,text) in enumerate((("A","正确"),("B","错误"))):
        top=140+i*170
        cv2.rectangle(pixels,(15,top),(980,top+140),(215,215,215),1)
        cv2.circle(pixels,(55,top+70),20,(40,40,160) if selected and i==0 else (195,195,195),-1 if selected and i==0 else 1)
        cv2.putText(pixels,letter,(47,top+77),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255) if selected and i==0 else (70,70,70),1)
        rows.extend([line(47,top+60,letter,16,20),line(110,top+55,text,200,30)])
    for x,text in ((500,"上一题"),(670,"下一题"),(830,"提交答卷")):
        cv2.rectangle(pixels,(x,640),(x+110,680),(80,80,80),-1)
        rows.append(line(x+10,650,text,90,20))
    return pixels,OCRLayout("\n".join(r.text for r in rows),tuple(rows),1000,700)


def test_geometry_reads_selection_from_fresh_pixels_with_cached_text():
    pixels,layout=fixture()
    assert not parse_exam(layout,pixels).options[0].selected
    changed,_=fixture(selected=True)
    actual=parse_exam(layout,changed)
    assert actual.options[0].selected and not actual.options[1].selected
    assert actual.options[0].text=="正确"
    assert actual.controls["next"].enabled


def test_footer_words_inside_an_option_are_not_buttons():
    pixels,layout=fixture()
    rows=list(layout.lines)
    rows[2]=line(110,195,"提交答卷",200,30)
    actual=parse_exam(OCRLayout(layout.text,tuple(rows),1000,700),pixels)
    assert len(actual.controls)==3
    assert actual.controls["submit"].box.top==650


def test_only_one_navigation_word_does_not_produce_a_click_target():
    pixels,layout=fixture()
    layout=OCRLayout("",tuple(layout.lines[:-2]),1000,700)
    assert not parse_exam(layout,pixels).controls


def test_dialog_requires_explicit_exam_confirmation_text():
    pixels=np.full((600,900,3),255,np.uint8)
    rows=(line(300,100,"确定删除资料吗？",300),line(450,350,"确定",80))
    cv2.rectangle(pixels,(450,350),(530,372),(70,70,70),-1)
    layout=OCRLayout("\n".join(r.text for r in rows),rows,900,600)
    assert parse_dialog(layout,pixels).kind=="blocked"
    rows=(line(300,100,"确定提交答卷吗？",300),rows[1])
    layout=OCRLayout("\n".join(r.text for r in rows),rows,900,600)
    dialog=parse_dialog(layout,pixels)
    assert dialog.kind=="confirm" and dialog.control.enabled


def test_success_option_prose_is_not_a_submission_receipt():
    pixels,layout=fixture()
    rows=list(layout.lines)
    rows[2]=line(110,195,"交卷成功",200,30)
    layout=OCRLayout("\n".join(r.text for r in rows),tuple(rows),1000,700)
    assert parse_dialog(layout,pixels).kind!="success"


def test_ocr_identical_frame_skips_model_inference():
    pixels,layout=fixture()
    content=cv2.imencode(".png",pixels)[1].tobytes()
    engine_calls=[]
    def engine(image,use_det=True):
        engine_calls.append(use_det)
        return [(r.box,r.text,r.confidence) for r in layout.lines] if use_det else [["A",.99]]
    ocr=LocalOCR()
    ocr._engine=engine
    first=ocr.recognize_layout(content,reuse_text=True)
    count=len(engine_calls)
    second=ocr.recognize_layout(content,reuse_text=True)
    assert first is second and len(engine_calls)==count and ocr.stats["exact_cache"]==1


def test_line_cache_reuses_only_identical_original_pixels_and_preserves_order():
    calls=[]
    def recognizer(images,word_boxes):
        calls.append(len(images))
        return [(str(int(image.sum())),.99) for image in images],.1
    first=np.zeros((15,40,3),np.uint8)
    changed=first.copy()
    changed[7,15,0]=1
    cache=CachedRecognizer(recognizer,limit=2)
    a,_=cache([first,changed])
    b,elapsed=cache([changed,first])
    assert b==list(reversed(a)) and calls==[2] and elapsed==0
    assert cache.hits==2


def test_body_layout_cache_rechecks_changed_badge_letters(monkeypatch):
    pixels,layout=fixture()
    content=cv2.imencode(".png",pixels)[1].tobytes()
    ocr=LocalOCR()
    ocr._engine=lambda image,use_det=True:[(r.box,r.text,r.confidence)for r in layout.lines] if use_det else [["A",.99]]
    first=ocr.recognize_layout(content,reuse_text=True)
    # Force the text-only mask to agree, as it intentionally ignores controls.
    monkeypatch.setattr("newxky.monitor.same_text_signature",lambda a,b:True)
    changed=pixels.copy()
    changed[200:220,45:65]=(30,30,150)
    monkeypatch.setattr("newxky.ocr._recognize_option_chip",lambda engine,crop:("C",.99))
    new_content=cv2.imencode(".png",changed)[1].tobytes()
    actual=ocr.recognize_layout(new_content,reuse_text=True)
    assert ocr.stats["text_cache"]==1
    assert any(r.text=="C" for r in actual.lines)
    assert actual.text!=first.text


def test_check_acknowledgement_does_not_inherit_submit_intent_from_background_footer():
    pixels,layout=fixture()
    rows=(*layout.lines,line(250,250,"全部题目已完成，检查完成。",450),line(450,450,"确定",80))
    cv2.rectangle(pixels,(450,450),(530,472),(80,80,80),-1)
    layout=OCRLayout("\n".join(r.text for r in rows),rows,1000,700)
    dialog=parse_dialog(layout,pixels)
    assert dialog.kind=="checked" and dialog.control.enabled
