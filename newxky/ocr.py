"""Offline Chinese OCR; same-baseline fragments are ordered left to right."""
import re
import unicodedata
import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class OCRLine:
    box: tuple
    text: str
    confidence: float

    @property
    def rect(self):
        xs, ys = zip(*self.box)
        return min(xs), min(ys), max(xs), max(ys)


@dataclass(frozen=True)
class OCRLayout:
    text: str
    lines: tuple[OCRLine, ...]
    width: int
    height: int


def _remember(cache, key, value, limit):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > limit:
        cache.popitem(last=False)
    return value


def option_chips(pixels):
    """Locate outlined letter chips near the left edge of an exam card."""
    import cv2
    gray = pixels if pixels.ndim == 2 else cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    height, width = gray.shape
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if not (12 <= w <= 90 and 12 <= h <= 90 and .75 <= w / h <= 1.3):
            continue
        if x > width * .25 or x < 3 or y < 20:
            continue
        if cv2.contourArea(contour) < w * h * .6:
            continue
        if any(abs(x - a) < 8 and abs(y - b) < 8 for a, b, _, _ in boxes):
            continue
        boxes.append((x, y, w, h))
    # Real badges share a left column. Small enclosed strokes in Chinese body
    # text can also be contours; do not run an OCR pass on each of those.
    columns = []
    for box in sorted(boxes):
        column = next((column for column in columns
                       if abs(box[0] - column[0][0]) <= max(4, min(box[2], column[0][2]) * .3)), None)
        if column is None:
            columns.append([box])
        else:
            column.append(box)
    aligned = [column for column in columns if len(column) >= 2]
    selected = min(aligned, key=lambda column: column[0][0]) if aligned else boxes
    return sorted(selected, key=lambda b: b[1])


def _text_lines(rows):
    lines = []
    for box, text, confidence in sorted(rows, key=lambda row: min(p[1] for p in row[0])):
        top, bottom = min(p[1] for p in box), max(p[1] for p in box)
        left, right = min(p[0] for p in box), max(p[0] for p in box)
        line = next((line for line in lines if
                     min(line["bottom"], bottom) - max(line["top"], top)
                     >= .6 * min(line["bottom"] - line["top"], bottom - top)), None)
        if line is None:
            line = {"top": top, "bottom": bottom, "parts": []}
            lines.append(line)
        line["parts"].append((left, right, str(text)))
    return lines


def _align_option_labels(rows):
    """Put a centred letter before its whole text block, not between its lines.

    Only letters actually recognised in a shared left column are used. Text
    blocks with more than one possible label are left unchanged so uncertain
    geometry cannot manufacture an option-to-letter mapping.
    """
    markers = []
    for index, (box, text, _) in enumerate(rows):
        text = unicodedata.normalize("NFKC", str(text)).strip()
        standalone = re.fullmatch(r"[○◯〇●◎□☐☑✓√\s]*([A-H])[.、:)]?", text)
        inline = re.match(r"^([A-H])(?:[.、:)]\s*|[ \t]+)\S", text)
        if not (standalone or inline):
            continue
        left, right = min(p[0] for p in box), max(p[0] for p in box)
        top, bottom = min(p[1] for p in box), max(p[1] for p in box)
        markers.append({"index": index, "label": (standalone or inline)[1],
                        "left": left, "right": right, "top": top, "bottom": bottom,
                        "standalone": bool(standalone)})
    if len(markers) < 2 or len({m["label"] for m in markers}) != len(markers):
        return rows
    height = max(m["bottom"] - m["top"] for m in markers)
    if max(m["left"] for m in markers) - min(m["left"] for m in markers) > max(12, height):
        return rows
    # An inline row's right edge includes its option text, not just the letter.
    column_right = max(m["right"] if m["standalone"] else m["left"] + height
                       for m in markers)
    marker_indices = {m["index"] for m in markers}
    body = [row for index, row in enumerate(rows)
            if index not in marker_indices and min(p[0] for p in row[0]) > column_right]
    blocks = []
    for line in _text_lines(body):
        left = min(part[0] for part in line["parts"])
        if blocks:
            previous = blocks[-1]["lines"][-1]
            line_height = min(line["bottom"] - line["top"], previous["bottom"] - previous["top"])
            gap = line["top"] - previous["bottom"]
            # A new card, indentation change or another labelled row ends a block.
            barrier = any(previous["bottom"] < (m["top"] + m["bottom"]) / 2 < line["top"]
                          and not m["standalone"] for m in markers)
            if (gap <= .9 * line_height and abs(left - blocks[-1]["left"]) <= 2 * line_height
                    and not barrier):
                blocks[-1]["lines"].append(line)
                continue
        blocks.append({"left": left, "lines": [line]})
    aligned = list(rows)
    for block in blocks:
        first, last = block["lines"][0], block["lines"][-1]
        labels = [m for m in markers if first["top"] <= (m["top"] + m["bottom"]) / 2 <= last["bottom"]]
        if len(labels) != 1 or not labels[0]["standalone"]:
            continue
        marker = labels[0]
        _, text, confidence = rows[marker["index"]]
        box = [[marker["left"], first["top"]], [marker["right"], first["top"]],
               [marker["right"], first["bottom"]], [marker["left"], first["bottom"]]]
        aligned[marker["index"]] = (box, text, confidence)
    return aligned


def text_from_rows(rows):
    lines = _text_lines(_align_option_labels(list(rows)))
    result = []
    for line in lines:
        fragments, last_right = [], None
        for left, right, fragment in sorted(line["parts"]):
            # Spaces retain option-label boundaries when OCR splits A. and its text.
            overlap = max(0, (last_right or left) - left)
            shared = 0
            width = (right - left) / max(len(fragment), 1)
            previous = "".join(fragments)
            if overlap > width * .35:
                for size in range(1, min(len(previous), len(fragment)) + 1):
                    if previous.endswith(fragment[:size]) and size * width <= overlap + width * .65:
                        shared = size
            fragments.append(fragment[shared:])
            last_right = max(last_right or right, right)
        result.append(" ".join(fragments))
    return "\n".join(result)


def _recognize_option_chip(engine, crop):
    """Read both outlined badges and white letters on a selected dark badge."""
    import cv2
    import numpy as np

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    edge = np.concatenate((binary[0], binary[-1], binary[:, 0], binary[:, -1]))
    dark_background = np.median(edge) < 128
    if dark_background:
        binary = cv2.bitwise_not(binary)
    cleaned = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    contrast = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    if dark_background:
        contrast = cv2.bitwise_not(contrast)
    contrast = cv2.cvtColor(contrast, cv2.COLOR_GRAY2BGR)
    variants = [cleaned, contrast, crop] if dark_background else [crop, contrast, cleaned]
    ink_y, ink_x = np.where(cv2.cvtColor(contrast, cv2.COLOR_BGR2GRAY) < 235)
    if ink_x.size:
        variants.append(contrast[ink_y.min():ink_y.max() + 1, ink_x.min():ink_x.max() + 1])
    ink_y, ink_x = np.where(binary < 128)
    if ink_x.size:
        tight = cleaned[ink_y.min():ink_y.max() + 1, ink_x.min():ink_x.max() + 1]
        tight = cv2.resize(tight, (max(1, round(tight.shape[1] * 32 / tight.shape[0])), 32),
                           interpolation=cv2.INTER_CUBIC)
        variants.append(tight)
    votes = []
    for pixels in variants:
        scale = 40 / pixels.shape[0]
        pixels = cv2.resize(pixels, (max(1, round(pixels.shape[1] * scale)), 40), interpolation=cv2.INTER_CUBIC)
        pixels = cv2.copyMakeBorder(pixels, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        recognized = engine(pixels, use_det=False)
        if recognized:
            text, score = recognized[0][:2]
            letter = text.strip().upper()
            if re.fullmatch(r"[A-H]", letter) and score >= .85:
                return letter, score
            if re.fullmatch(r"[A-H]", letter) and score >= .65:
                votes.append((letter, score))
    # Very small antialiased glyphs can be consistent but individually below
    # the single-pass threshold. Require agreement across enhanced readings.
    if len(votes) >= 2 and len({letter for letter, _ in votes}) == 1 and max(score for _, score in votes) >= .7:
        return votes[0][0], sum(score for _, score in votes) / len(votes)
    return None


def _inside_chip(box, chip):
    x, y, w, h = chip
    left, right = min(p[0] for p in box), max(p[0] for p in box)
    top, bottom = min(p[1] for p in box), max(p[1] for p in box)
    return (x - 2 <= left <= right <= x + w + 2
            and y - 2 <= top <= bottom <= y + h + 2)


def _refine_uncertain_rows(engine, pixels, rows):
    """Native-resolution rereads for a few uncertain body lines, never a
    whole-frame upscale. Require agreement and retain semantic uncertainty.
    """
    import cv2
    result = list(rows)
    uncertain = sorted((i for i,(_,text,score) in enumerate(rows)
                        if .35 <= score < .90 and len(str(text)) >= 4),key=lambda i:rows[i][2])[:4]
    for i in uncertain:
        box,text,score = rows[i]
        x0 = max(0,round(min(p[0] for p in box))-2)
        y0 = max(0,round(min(p[1] for p in box))-2)
        x1 = min(pixels.shape[1],round(max(p[0] for p in box))+2)
        y1 = min(pixels.shape[0],round(max(p[1] for p in box))+2)
        crop = pixels[y0:y1,x0:x1]
        if not crop.size:
            continue
        reads = []
        for scale in (1,1.5):
            variant = cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC) if scale!=1 else crop
            reading = engine(variant,use_det=False)
            if reading:
                reads.append((str(reading[0][0]).strip(),float(reading[0][1])))
        if len(reads)!=2 or reads[0][0]!=reads[1][0] or min(r[1] for r in reads)<.9:
            continue
        replacement = reads[0][0]
        average = sum(r[1] for r in reads)/2
        if average < score+.04:
            continue
        critical = lambda value:re.findall(r"不|未|无|非|禁止|严禁|不得|\d+(?:\.\d+)?|[%％]",value)
        if critical(text) != critical(replacement):
            # Preserve the unresolved text but forbid automatic selection on it.
            result[i] = (box,text,min(score,.69))
        else:
            result[i] = (box,replacement,average)
    return result


class LocalOCR:
    def __init__(self):
        self._engine = None
        self._engine_lock = Lock()
        self._recognition_lock = Lock()
        self._layouts = OrderedDict()
        self._badges = OrderedDict()
        self._last_signature = None
        self._last_layout = None
        self._last_chips = ()
        self.stats = {"full": 0, "exact_cache": 0, "text_cache": 0, "badge_cache": 0}

    def warmup(self):
        if self._engine is None:
            with self._engine_lock:
                if self._engine is None:
                    from .ocr_engine import OCREngine
                    self._engine = OCREngine()

    def recognize(self, image: bytes) -> str:
        return self.recognize_layout(image).text

    def recognize_layout(self, image: bytes, *, reuse_text=False, force=False) -> OCRLayout:
        """Retain original hit-test geometry; serialize inference across workers.

        Automation may reuse geometry after a colour-only selection change. Its
        selection and enabled states are ALWAYS read from the fresh pixels.
        """
        self.warmup()
        with self._recognition_lock:
            if force:
                self._layouts.clear()
                self._last_signature = self._last_layout = None
            return self._recognize_layout(image, reuse_text and not force)

    def _recognize_layout(self, image, reuse_text):
        key = hashlib.blake2b(image, digest_size=16).digest()
        if key in self._layouts:
            self.stats["exact_cache"] += 1
            self._layouts.move_to_end(key)
            return self._layouts[key]
        import cv2
        import numpy as np
        pixels = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if pixels is None:
            raise ValueError("无法读取截图")
        chips = option_chips(pixels)
        signature = None
        if reuse_text:
            from .monitor import text_signature, same_text_signature
            signature = text_signature(cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY))
            if (self._last_layout is not None and self._last_signature is not None
                    and same_text_signature(self._last_signature, signature)):
                reused = self._reuse_badges(pixels,chips)
                if reused is not None:
                    self.stats["text_cache"] += 1
                    self._last_signature,self._last_layout,self._last_chips = signature,reused,chips
                    return _remember(self._layouts,key,reused,6)
        # Keep low-confidence lines too: dropping one could manufacture a
        # shorter, incorrect match. Desktop text is upright, so skip rotation.
        # Keep the byte input compatible with both supported RapidOCR versions.
        rows = self._engine(image)
        self.stats["full"] += 1
        rows = _refine_uncertain_rows(self._engine,pixels,rows)
        # Small A/B/C/D badges are often below the detector's text size even
        # when option text is large. Recognize each visible badge independently;
        # never invent letters from its position or from the bank's order.
        for x, y, w, h in chips:
            inside = [row for row in rows if _inside_chip(row[0], (x, y, w, h))]
            known = [row for row in inside if re.fullmatch(r"[A-H][.]?", row[1].strip()) and row[2] >= .85]
            inset_x, inset_y = round(w * .25), round(h * .2)
            crop = pixels[y + inset_y:y + h - inset_y, x + inset_x:x + w - inset_x]
            crop_key = (crop.shape, hashlib.blake2b(crop.tobytes(), digest_size=16).digest())
            if len(inside) == len(known) == 1:
                _remember(self._badges,crop_key,(known[0][1].strip()[0],known[0][2]),64)
                continue
            if crop_key in self._badges:
                self.stats["badge_cache"] += 1
                recognized = self._badges[crop_key]
                self._badges.move_to_end(crop_key)
            else:
                recognized = _remember(self._badges, crop_key,
                                       _recognize_option_chip(self._engine, crop), 64)
            if recognized:
                letter, score = recognized
                # A Chinese-looking glyph (e.g. B -> 巴) inside this same badge
                # is the old reading of the letter, not part of the option text.
                rows = [row for row in rows if not _inside_chip(row[0], (x, y, w, h))]
                rows.append(([[x + inset_x, y + inset_y], [x + w - inset_x, y + inset_y],
                              [x + w - inset_x, y + h - inset_y], [x + inset_x, y + h - inset_y]], letter, score))
        lines = tuple(OCRLine(tuple(tuple(float(v) for v in p) for p in box), str(text), float(score))
                      for box, text, score in rows)
        layout = OCRLayout(text_from_rows(rows), lines, pixels.shape[1], pixels.shape[0])
        # The signature and its layout must be updated together, including when
        # a caller alternates detailed automation OCR and ordinary manual OCR.
        self._last_signature, self._last_layout = signature, layout
        self._last_chips = chips
        return _remember(self._layouts, key, layout, 6)

    def _reuse_badges(self,pixels,chips):
        """Text masks ignore controls; re-read actual letters before reusing
        body geometry, so a badge-letter change cannot inherit an old label.
        """
        if len(chips)!=len(self._last_chips):
            return None
        if any(max(abs(a-b) for a,b in zip(now,old))>3 for now,old in zip(chips,self._last_chips)):
            return None
        rows = [(line.box,line.text,line.confidence) for line in self._last_layout.lines]
        for (x,y,w,h),old_chip in zip(chips,self._last_chips):
            ix,iy = round(w*.25),round(h*.2)
            crop = pixels[y+iy:y+h-iy,x+ix:x+w-ix]
            key = (crop.shape,hashlib.blake2b(crop.tobytes(),digest_size=16).digest())
            if key in self._badges:
                self.stats["badge_cache"] += 1
                recognized = self._badges[key]
                self._badges.move_to_end(key)
            else:
                recognized = _remember(self._badges,key,_recognize_option_chip(self._engine,crop),64)
            if not recognized:
                return None
            letter,score = recognized
            rows = [row for row in rows if not _inside_chip(row[0],old_chip)]
            rows.append(([[x+ix,y+iy],[x+w-ix,y+iy],[x+w-ix,y+h-iy],[x+ix,y+h-iy]],letter,score))
        lines = tuple(OCRLine(tuple(tuple(p) for p in box),text,float(score)) for box,text,score in rows)
        return OCRLayout(text_from_rows(rows),lines,pixels.shape[1],pixels.shape[0])
