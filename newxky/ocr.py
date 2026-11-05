"""Offline Chinese OCR; same-baseline fragments are ordered left to right."""
import re
import unicodedata
from threading import Lock


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


class LocalOCR:
    def __init__(self):
        self._engine = None
        self._engine_lock = Lock()

    def warmup(self):
        if self._engine is None:
            with self._engine_lock:
                if self._engine is None:
                    from .ocr_engine import OCREngine
                    self._engine = OCREngine()

    def recognize(self, image: bytes) -> str:
        self.warmup()
        # Keep low-confidence lines too: dropping one could manufacture a
        # shorter, incorrect match. Desktop text is upright, so skip rotation.
        rows = self._engine(image)
        # Small A/B/C/D badges are often below the detector's text size even
        # when option text is large. Recognize each visible badge independently;
        # never invent letters from its position or from the bank's order.
        import cv2
        import numpy as np
        pixels = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        for x, y, w, h in option_chips(pixels):
            inside = [row for row in rows if _inside_chip(row[0], (x, y, w, h))]
            known = [row for row in inside if re.fullmatch(r"[A-H][.]?", row[1].strip()) and row[2] >= .85]
            if len(inside) == len(known) == 1:
                continue
            inset_x, inset_y = round(w * .25), round(h * .2)
            crop = pixels[y + inset_y:y + h - inset_y, x + inset_x:x + w - inset_x]
            recognized = _recognize_option_chip(self._engine, crop)
            if recognized:
                letter, score = recognized
                # A Chinese-looking glyph (e.g. B -> 巴) inside this same badge
                # is the old reading of the letter, not part of the option text.
                rows = [row for row in rows if not _inside_chip(row[0], (x, y, w, h))]
                rows.append(([[x + inset_x, y + inset_y], [x + w - inset_x, y + inset_y],
                              [x + w - inset_x, y + h - inset_y], [x + inset_x, y + h - inset_y]], letter, score))
        return text_from_rows(rows)
