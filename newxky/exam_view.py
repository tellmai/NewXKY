"""Screen geometry and visual state for the supported exam card layout.

No bank letters are used to manufacture screen locations. All click targets
come from current OCR boxes and visible option controls.
"""
import re
from dataclasses import dataclass, field

from .matching import clean_stem
from .bank import normalized
from .ocr import option_chips, text_from_rows


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def center(self):
        return (self.left + self.right) / 2, (self.top + self.bottom) / 2

    def contains(self, point):
        return self.left <= point[0] < self.right and self.top <= point[1] < self.bottom


@dataclass(frozen=True)
class Control:
    name: str
    box: Rect
    enabled: bool | None


@dataclass(frozen=True)
class VisibleOption:
    letter: str
    text: str
    box: Rect
    selected: bool | None
    complete: bool = True
    confidence: float = 1.0
    starts: bool = True
    ends: bool = True


@dataclass(frozen=True)
class ExamView:
    stem: str
    options: tuple[VisibleOption, ...]
    controls: dict[str, Control]
    width: int
    height: int
    footer_top: float
    text: str = ""
    number: int | None = None
    total: int | None = None
    answered: int | None = None
    source: str = "ocr"

    @property
    def last(self):
        return "finish" in self.controls


NAV = {"上一题": "previous", "上题": "previous", "下一题": "next",
       "下一题目": "next", "下题": "next", "完成检查": "finish",
       "提交答卷": "submit", "提交试卷": "submit", "交卷": "submit"}


def _rect(line):
    return Rect(*line.rect)


def _rows(lines):
    return [(line.box, line.text, line.confidence) for line in lines]


def _contours(pixels, threshold=245):
    import cv2
    gray = cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY)
    mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)[1]
    return cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]


def _button_state(pixels, rect):
    """Disabled grey labels are distinct from black/white enabled labels."""
    import cv2
    import numpy as np
    h, w = pixels.shape[:2]
    l, t, r, b = [int(v) for v in (rect.left, rect.top, rect.right, rect.bottom)]
    crop = pixels[max(0,t):min(h,b), max(0,l):min(w,r)]
    if not crop.size:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    # Coloured filled buttons have a light label on a dark/saturated fill.
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    if np.mean((hsv[:,:,1] > 70) & (hsv[:,:,2] < 240)) > .25:
        return True
    dark = float(np.mean(gray < 150))
    middle = float(np.mean((gray >= 150) & (gray < 220)))
    if dark > .025:
        return True
    if middle > .025:
        return False
    return None


def selected_state(pixels, chip, card=None):
    """Read the inner badge fill, excluding its outline and antialiased edges."""
    import cv2
    import numpy as np
    x, y, w, h = [round(v) for v in chip]
    inset_x, inset_y = max(2, round(w*.23)), max(2, round(h*.23))
    crop = pixels[max(0,y+inset_y):y+h-inset_y, max(0,x+inset_x):x+w-inset_x]
    if not crop.size or crop.shape[0] < 4 or crop.shape[1] < 4:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    if np.mean(gray < 155) > .48:
        return True
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    if np.mean((hsv[:,:,1] > 80) & (hsv[:,:,2] < 240)) > .45:
        return True
    # Some versions colour the card rather than filling the badge.
    if card is not None:
        cx = min(pixels.shape[1]-1, round(card.right - min(20, (card.right-card.left)*.05)))
        cy = min(pixels.shape[0]-1, max(0, round(card.center[1])))
        sample = pixels[max(0,cy-3):cy+4, max(0,cx-3):cx+4]
        hsv_card = cv2.cvtColor(sample, cv2.COLOR_BGR2HSV)
        if np.mean(hsv_card[:,:,1] > 65) > .6:
            return True
    if np.mean(gray > 220) > .5:
        return False
    return None


def parse_exam(layout, pixels, previous=None) -> ExamView:
    """Re-read colour state even if OCR text/geometry came from a cache."""
    import cv2
    lines = list(layout.lines)
    h, w = pixels.shape[:2]
    candidates = []
    for line in lines:
        name = NAV.get(re.sub(r"\s+", "", line.text))
        box = _rect(line)
        if name and box.center[1] >= h * .72:
            candidates.append((name, box))
    # Require at least two aligned footer labels. A stem or answer mentioning
    # “提交答卷” is not a navigation control.
    controls = {}
    if len(candidates) >= 2:
        bottom = max(box.center[1] for _, box in candidates)
        for name, box in candidates:
            if abs(box.center[1] - bottom) <= max(16, (box.bottom-box.top)*.7):
                if name in controls:
                    controls = {}
                    break
                controls[name] = Control(name, box, _button_state(pixels, box))
    footer = min((c.box.top for c in controls.values()), default=h) - (12 if controls else 0)
    if controls:
        import numpy as np
        # Fixed footers can cover the lower half of an option even though its
        # badge is still visible. Locate the broad background boundary above
        # the buttons instead of treating the label baseline as the viewport.
        delta = np.max(np.abs(pixels[1:].astype(np.int16)-pixels[:-1].astype(np.int16)),axis=2)
        broad = np.mean(delta>4,axis=1)
        edges = np.flatnonzero(broad>.6)+1
        edges = edges[(edges>h*.7)&(edges<footer)]
        if edges.size:
            footer = min(footer,float(edges[-1]))
    chips = [b for b in option_chips(pixels) if b[1]+b[3]*.5 < footer]
    contours = _contours(pixels)
    rectangles = []
    for contour in contours:
        x,y,cw,ch = cv2.boundingRect(contour)
        if cw > w*.48 and ch > 40 and cv2.contourArea(contour) > cw*ch*.65:
            rectangles.append(Rect(x,y,x+cw,y+ch))
    labels = []
    for chip in chips:
        x,y,cw,ch = chip
        found = [line for line in lines if re.fullmatch(r"[A-H][.]?",line.text.strip())
                 and Rect(x-3,y-3,x+cw+3,y+ch+3).contains(_rect(line).center)]
        labels.append(found[0] if len(found)==1 else None)
    anchors = [ord(line.text.strip()[0])-i for i,line in enumerate(labels) if line is not None]
    base = anchors[0] if len(anchors)>=2 and len(set(anchors))==1 and 65<=anchors[0] and anchors[0]+len(chips)<=73 else None
    chip_cards = []
    for x,y,cw,ch in chips:
        center = (x+cw/2,y+ch/2)
        cards = [r for r in rectangles if r.contains(center)
                 and sum(r.contains((a+c/2,b+d/2)) for a,b,c,d in chips) == 1]
        chip_cards.append(min(cards,key=lambda r:(r.right-r.left)*(r.bottom-r.top)) if cards else None)
    entries = []
    for index,chip in enumerate(chips):
        x,y,cw,ch = chip
        center = (x+cw/2,y+ch/2)
        label_line = labels[index]
        card = chip_cards[index]
        letter = label_line.text.strip()[0] if label_line else None
        if letter is None and previous is not None and card is not None:
            body = [line for line in lines if _rect(line).left>=x+cw-2 and card.contains(_rect(line).center)]
            value = normalized(text_from_rows(_rows(body)))
            old = [o for o in previous.options if abs(o.box.center[0]-center[0])<=3
                   and abs(o.box.center[1]-center[1])<=3 and value and normalized(o.text)==value]
            if len(old)==1:
                letter = old[0].letter
        if letter is None and base is not None:
            # Corroborated PAGE label positions, never the bank's letter order.
            letter = chr(base+index)
        if letter is not None:
            entries.append((chip,letter,card,label_line))
    options = []
    for i,(chip,letter,card,label_line) in enumerate(entries):
        x,y,cw,ch = chip
        bounded = card is not None
        if card is None:
            top = (entries[i-1][0][1]+entries[i-1][0][3]/2+y+ch/2)/2 if i else y-ch*1.1
            next_y = entries[i+1][0][1] if i+1 < len(entries) else footer
            bottom = (y+ch/2+next_y)/2 if i+1 < len(entries) else footer
            card = Rect(max(0,x-12), max(0,top), w-4, min(footer,bottom))
        body = [line for line in lines if line is not label_line
                and _rect(line).left >= x+cw-2 and card.contains(_rect(line).center)
                and _rect(line).bottom < footer]
        text = text_from_rows(_rows(body))
        starts = card.top >= 1 if bounded else i > 0
        ends = card.bottom < footer-2 if bounded else i+1 < len(entries)
        clipped = not starts or not ends
        # Text touching the fixed footer can itself have been cut in half.
        if any(_rect(line).bottom >= footer-3 for line in body):
            ends = False
            clipped = True
        confidence = min((line.confidence for line in body), default=0)
        options.append(VisibleOption(letter,text,Rect(x,y,x+cw,y+ch),
                                     selected_state(pixels,chip,card),not clipped,confidence,starts,ends))
    if len({o.letter for o in options}) != len(options):
        options = []
    # An unreadable selected A badge must not move the stem boundary down to B.
    first_top = min((card.top if card else chip[1]-chip[3]
                     for chip,card in zip(chips,chip_cards)),default=footer)
    stem_lines = [line for line in lines if _rect(line).bottom <= first_top and _rect(line).bottom < footer]
    stem_cards = [r for r in rectangles if r.bottom <= first_top+1
                  and any(r.contains(_rect(line).center) for line in stem_lines)]
    stem_card = min(stem_cards,key=lambda r:(r.right-r.left)*(r.bottom-r.top)) if stem_cards else None
    if stem_card:
        headers = [line for line in stem_lines if _rect(line).bottom <= stem_card.top+2]
        stem_lines = [line for line in stem_lines if stem_card.contains(_rect(line).center)]
    else:
        prose_top = min((_rect(line).top for line in stem_lines
                         if _rect(line).right-_rect(line).left > w*.2),default=first_top)
        headers = [line for line in stem_lines if _rect(line).bottom <= prose_top]
    numbers = []
    for line in headers:
        text = line.text.strip()
        tag = re.fullmatch(r"(?:单选|多选|判断)题(?:[·•.]可多选)?\s*(\d{1,4})",text)
        bare = re.fullmatch(r"\d{1,4}",text)
        if tag or bare and _rect(line).right >= w*.8:
            number = int(tag[1] if tag else text)
            if 0 < number <= 1000:
                numbers.append(number)
                if line in stem_lines:
                    stem_lines.remove(line)
    card_number = numbers[0] if numbers and len(set(numbers)) == 1 else None
    stem = clean_stem(text_from_rows(_rows(stem_lines)))
    progress = re.search(r"第\s*(\d+)\s*题\s*/\s*共\s*(\d+)\s*题", layout.text)
    answered = re.search(r"已答\s*(\d+)\s*/\s*(\d+)",layout.text)
    return ExamView(stem,tuple(options),controls,w,h,footer,layout.text,
                    int(progress[1]) if progress else card_number, int(progress[2]) if progress else None,
                    int(answered[1]) if answered else None)


@dataclass(frozen=True)
class DialogView:
    kind: str
    control: Control | None = None
    wait_seconds: int | None = None
    message: str = ""


def parse_dialog(layout, pixels):
    """Only explicit exam check/submit dialogs are eligible for confirmation."""
    text = re.sub(r"\s+", "", layout.text)
    # A success phrase must be a standalone line: quoted option prose cannot
    # be mistaken for a receipt. Dialogs are inspected only in submit states.
    success = {"交卷成功", "答卷提交成功", "提交成功", "考试已完成", "考试已结束"}
    footer_visible = sum(re.sub(r"\s+", "", line.text) in NAV
                         and _rect(line).center[1] > layout.height*.72 for line in layout.lines) >= 2
    if not footer_visible and any(re.sub(r"[\s！!。.]", "", line.text) in success for line in layout.lines):
        return DialogView("success",message=text)
    missing = re.search(r"(?:还有|存在|您有)\d*(?:道|题)?(?:题目)?(?:未答|未完成)|(?:未答|漏答)\d+题|尚有.*未(?:答|完成)",text)
    if missing:
        return DialogView("incomplete",message=text)
    wait = re.search(r"(?:还需|请等待|剩余)\s*(\d+)\s*(秒|分钟)",layout.text)
    minimum = re.search(r"开考(?:满)?\s*(\d+)\s*分钟后(?:可|允许)?交卷",layout.text)
    if wait:
        acks = [line for line in layout.lines if re.sub(r"\s+","",line.text) in {"确定","知道了"}]
        ack = Control("ack",_rect(acks[0]),_button_state(pixels,_rect(acks[0]))) if len(acks)==1 else None
        return DialogView("wait",ack,int(wait[1])*(60 if wait[2]=="分钟" else 1),text)
    # The minimum-time banner alone isn't a rejection or a dialog.
    if minimum and any(s in text for s in ("不能交卷", "暂不能", "未达到", "未满")):
        acks = [line for line in layout.lines if re.sub(r"\s+","",line.text) in {"确定","知道了"}]
        ack = Control("ack",_rect(acks[0]),_button_state(pixels,_rect(acks[0]))) if len(acks)==1 else None
        return DialogView("wait",ack,5,text)
    # Do not join a generic dialog “确定” with the background footer's
    # “提交答卷”. Confirmation intent must occur in the message itself.
    message_lines = [re.sub(r"\s+","",line.text) for line in layout.lines
                     if re.sub(r"\s+","",line.text) not in {*NAV,"确定","确认","取消","知道了","确认提交","确认交卷","确定交卷"}]
    confirming = any(re.search(r"(?:确认|确定|是否).{0,18}(?:交卷|提交答卷|提交试卷)|(?:交卷|提交答卷).{0,12}(?:确认|确定)",line)
                     for line in message_lines)
    checked = any(s in text for s in ("全部完成", "全部已答", "全部答完", "检查完成", "没有未答", "无未答"))
    checked |= bool(re.search(r"(?:全部|所有)(?:题目|试题)?(?:已|均已)?(?:完成|答完|作答)",text))
    if not confirming and not checked:
        buttons = [line for line in layout.lines if re.sub(r"\s+","",line.text) in {"确定","取消","确认","知道了"}]
        return DialogView("blocked" if buttons else "unknown",message=text)
    allowed = ("确认交卷","确定交卷","确认提交","确定提交","确定","确认","是") if confirming else ("确定","确认","知道了")
    found = [line for line in layout.lines if re.sub(r"\s+","",line.text) in allowed]
    if len(found) == 1:
        box = _rect(found[0])
        return DialogView("confirm" if confirming else "checked",Control("confirm",box,_button_state(pixels,box)),message=text)
    return DialogView("confirm" if confirming else "checked",message=text)
