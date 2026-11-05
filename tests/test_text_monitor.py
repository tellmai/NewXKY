from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from newxky.monitor import FrameTracker, text_signature


def frame(text="Allowed limit 1.5", *, background="white", foreground="#222222", border="#dddddd", selected=False, caret=False, button_hover=False):
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 22) if font_path.exists() else ImageFont.load_default(size=22)
    image = Image.new("RGB", (640, 320), "#f4f7fa")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 630, 310), radius=12, fill=background, outline=border, width=1)
    draw.text((80, 45), text, font=font, fill=foreground)
    for y, label, value in [(135, "A", "Option one"), (225, "B", "Option two")]:
        draw.ellipse((22, y, 44, y + 22), fill="#9b2029" if selected else "white", outline="#bbbbbb")
        draw.text((27, y - 2), label, font=font, fill="white" if selected else "#333333")
        draw.text((80, y), value, font=font, fill=foreground)
    if caret:
        draw.rectangle((430, 45, 431, 70), fill=foreground)
    draw.rounded_rectangle((470, 265, 615, 301), radius=6,
                           fill="#0b7f70" if button_hover else "white", outline="#cccccc")
    draw.text((505, 270), "NEXT", font=font, fill="white" if button_hover else "#222222")
    return np.asarray(image.convert("L"))


@pytest.mark.parametrize("style", [
    {"background": "#f0f7f3"},
    {"background": "#fff6f6", "border": "#b12028"},
    {"border": "#087f70"},
    {"foreground": "#126658"},
    {"caret": True},
    {"selected": True},
    {"button_hover": True},
])
def test_hover_and_control_changes_do_not_invalidate_text(style):
    tracker = FrameTracker()
    tracker.observe_text(text_signature(frame()), 0)
    assert not tracker.observe_text(text_signature(frame(**style)), .1)


@pytest.mark.parametrize("changed", ["Forbidden limit 1.5", "Allowed limit 15", "Allowed limit -1.5", "Allowed limit 1.6"])
def test_word_negation_and_numeric_changes_invalidate_text(changed):
    tracker = FrameTracker()
    tracker.observe_text(text_signature(frame()), 0)
    assert tracker.observe_text(text_signature(frame(changed)), .1)


@pytest.mark.skipif(not Path("C:/Windows/Fonts/msyh.ttc").exists(), reason="Windows Chinese font fixture")
@pytest.mark.parametrize("old,new", [("允许", "不允许"), ("王", "玉"), ("未", "末"), ("己", "已")])
@pytest.mark.parametrize("size", [14, 22])
def test_chinese_character_changes_are_not_treated_as_colour_fringe(old, new, size):
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", size)
    images = []
    for text in [old, new]:
        image = Image.new("L", (640, 320), 255)
        ImageDraw.Draw(image).text((80, 45), text, font=font, fill=34)
        images.append(np.asarray(image))
    tracker = FrameTracker()
    tracker.observe_text(text_signature(images[0]), 0)
    assert tracker.observe_text(text_signature(images[1]), .1)


def test_hover_keeps_processed_answer_but_new_text_discards_old_work():
    tracker = FrameTracker()
    assert tracker.observe_text(text_signature(frame()), 0)
    first = tracker.begin()
    assert not tracker.observe_text(text_signature(frame(background="#f0f7f3")), .1)
    assert tracker.finish(first)
    assert not tracker.ready(.5)
    assert tracker.observe_text(text_signature(frame("A different question")), .6)
    second = tracker.begin()
    assert tracker.observe_text(text_signature(frame("The next question")), .7)
    assert not tracker.finish(second)


def test_unchanged_raw_frames_skip_text_analysis_and_retry_resets_cache(monkeypatch):
    calls = []
    monkeypatch.setattr("newxky.monitor.text_signature", lambda image: calls.append(1) or b"same text")
    tracker = FrameTracker()
    image = frame()
    assert tracker.observe_image(image, 0)
    assert not tracker.observe_image(image, .1)
    assert not tracker.observe_image(image.copy(), .2)
    assert calls == [1]
    tracker.invalidate()
    assert tracker.observe_image(image, .3)
    assert calls == [1, 1]
