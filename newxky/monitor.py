"""Frame revision tracking keeps completed OCR from reviving a stale answer."""
import hashlib
import struct


def text_signature(gray) -> bytes:
    """Compare character strokes, ignoring flat fills, card borders and badges."""
    import cv2
    import numpy as np
    from .ocr import option_chips

    kernel = np.ones((15, 15), np.uint8)
    low, high = cv2.erode(gray, kernel), cv2.dilate(gray, kernel)
    mean = cv2.boxFilter(gray, cv2.CV_32F, (15, 15))
    background = np.where(mean * 2 >= high.astype(np.int16) + low, high, low).astype(np.uint8)
    contrast = high.astype(np.int16) - low
    distance = cv2.absdiff(gray, background).astype(np.int16)
    ink = ((distance * 2 > contrast) & (contrast > 28)).astype(np.uint8) * 255
    height, width = ink.shape
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    keep = np.ones(count, np.uint8)
    keep[0] = 0
    for index in range(1, count):
        _, _, w, h, area = stats[index]
        caret = w <= 2 and h >= 12 and area >= w * h * .8
        border = area < w * h * .04 or w > max(64, h * 8) or h > max(80, w * 10)
        control_outline = w >= 40 and h >= 12 and w >= h * 1.8 and area < w * h * .18
        if caret or border or control_outline:
            keep[index] = 0
    ink = keep[labels] * 255
    # Exclude isolated option controls, whose fill/letter weight changes on hover
    # or selection. Neighbouring body strokes prevent treating prose as a badge.
    for x, y, w, h in option_chips(gray):
        left = ink[y:y + h, max(0, x - w):max(0, x - 2)]
        right = ink[y:y + h, x + w + 2:min(width, x + 2 * w)]
        if np.count_nonzero(left) <= 2 and np.count_nonzero(right) <= 2:
            ink[y:y + h, x:x + w] = 0
    # A filled hover button may leave four high-contrast rounded corners even
    # after its outline is removed. Preserve its text and discard those corners.
    _, dark = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(dark, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= 40 and 12 <= h <= 128 and w >= h * 1.8 and cv2.contourArea(contour) >= w * h * .6:
            corner = min(12, max(4, h // 3))
            for top in (y, y + h - corner):
                for left in (x, x + w - corner):
                    ink[top:top + corner, left:left + corner] = 0
    # Remove long decorative rules after whole card borders, including their
    # rounded corners, have been excluded above.
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, max(24, width // 8)), np.uint8))
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((max(24, height // 6), 1), np.uint8))
    mask = (ink & ~(horizontal | vertical)) > 0
    # Preserve relative stroke intensity too: this distinguishes tiny genuine
    # glyph changes from antialias rounding after a foreground/background tint.
    strength = np.clip(distance.astype(np.int32) * 255 // np.maximum(contrast, 1), 0, 255).astype(np.uint8)
    return struct.pack("<II", width, height) + np.packbits(mask).tobytes() + strength.tobytes()


def same_text_signature(first: bytes, second: bytes) -> bool:
    if first == second:
        return True
    if first[:8] != second[:8]:
        return False
    import cv2
    import numpy as np

    width, height = struct.unpack("<II", first[:8])
    size = (width * height + 7) // 8
    previous = np.unpackbits(np.frombuffer(first[8:8 + size], np.uint8))[:width * height].reshape(height, width)
    current = np.unpackbits(np.frombuffer(second[8:8 + size], np.uint8))[:width * height].reshape(height, width)
    strength0 = np.frombuffer(first[8 + size:], np.uint8).reshape(height, width)
    strength1 = np.frombuffer(second[8 + size:], np.uint8).reshape(height, width)
    text_area = cv2.dilate(previous | current, np.ones((3, 3), np.uint8)) > 0
    delta = cv2.absdiff(strength0, strength1)
    return not np.any((delta > 8) & text_area)


class FrameTracker:
    def __init__(self):
        self.revision = 0
        self.digest = None
        self.observed_at = 0.0
        self.processed = None
        self.busy = False
        self._text_signature = None
        self._raw_digest = None

    def observe_image(self, gray, now: float) -> bool:
        raw_digest = hashlib.blake2b(gray.tobytes(), digest_size=16).digest()
        if raw_digest == self._raw_digest:
            return False
        self._raw_digest = raw_digest
        return self.observe_text(text_signature(gray), now)

    def observe_text(self, signature: bytes, now: float) -> bool:
        if self._text_signature is not None and same_text_signature(self._text_signature, signature):
            return False
        self._text_signature = signature
        return self.observe(signature, now)

    def observe(self, pixels: bytes, now: float) -> bool:
        digest = hashlib.blake2b(pixels, digest_size=16).digest()
        if digest == self.digest:
            return False
        self.revision += 1
        self.digest = digest
        self.observed_at = now
        return True

    def ready(self, now: float, settle: float = .18) -> bool:
        return not self.busy and self.digest is not None and self.processed != self.revision and now - self.observed_at >= settle

    def begin(self) -> int:
        self.busy = True
        return self.revision

    def finish(self, revision: int) -> bool:
        self.busy = False
        if revision != self.revision:
            return False
        self.processed = revision
        return True

    def invalidate(self):
        self.revision += 1
        self.digest = None
        self.processed = None
        self._text_signature = None
        self._raw_digest = None
