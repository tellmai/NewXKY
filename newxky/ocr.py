"""Offline Chinese OCR; same-baseline fragments are ordered left to right."""
import re


def option_chips(pixels):
    """Locate outlined letter chips near the left edge of an exam card."""
    import cv2
    gray = cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    height, width = gray.shape
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if not (18 <= w <= 90 and 18 <= h <= 90 and .75 <= w / h <= 1.3):
            continue
        if x > width * .16 or x < 3 or y < 20:
            continue
        if cv2.contourArea(contour) < w * h * .6:
            continue
        if any(abs(x - a) < 8 and abs(y - b) < 8 for a, b, _, _ in boxes):
            continue
        boxes.append((x, y, w, h))
    return sorted(boxes, key=lambda b: b[1])


def text_from_rows(rows):
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


class LocalOCR:
    def __init__(self):
        self._engine = None

    def recognize(self, image: bytes) -> str:
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
        # Keep low-confidence lines too: dropping one could manufacture a
        # shorter, incorrect match. Desktop text is upright, so skip rotation.
        rows, _ = self._engine(image, use_cls=False, text_score=0.0)
        rows = rows or []
        # Small A/B/C/D badges are often below the detector's text size even
        # when option text is large. Recognize each visible badge independently;
        # never invent letters from its position or from the bank's order.
        import cv2
        import numpy as np
        pixels = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        for x, y, w, h in option_chips(pixels):
            already = any(min(p[0] for p in box) < x + w and max(p[0] for p in box) > x
                          and min(p[1] for p in box) < y + h and max(p[1] for p in box) > y
                          and re.match(r"^[A-H](?:[.\s]|$)", text.strip()) for box, text, _ in rows)
            if already:
                continue
            inset_x, inset_y = round(w * .25), round(h * .2)
            crop = pixels[y + inset_y:y + h - inset_y, x + inset_x:x + w - inset_x]
            crop = cv2.copyMakeBorder(crop, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=(255, 255, 255))
            crop = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            recognized, _ = self._engine(crop, use_det=False, use_cls=False, text_score=0.0)
            if recognized:
                text, score = recognized[0][:2]
                letter = text.strip().upper()
                if re.fullmatch(r"[A-H]", letter) and score >= .85:
                    rows.append(([[x + inset_x, y + inset_y], [x + w - inset_x, y + inset_y],
                                  [x + w - inset_x, y + h - inset_y], [x + inset_x, y + h - inset_y]], letter, score))
        return text_from_rows(rows)
