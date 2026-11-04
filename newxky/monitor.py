"""Frame revision tracking keeps completed OCR from reviving a stale answer."""
import hashlib


class FrameTracker:
    def __init__(self):
        self.revision = 0
        self.digest = None
        self.observed_at = 0.0
        self.processed = None
        self.busy = False

    def observe(self, pixels: bytes, now: float) -> bool:
        digest = hashlib.blake2b(pixels, digest_size=16).digest()
        if digest == self.digest:
            return False
        self.revision += 1
        self.digest = digest
        self.observed_at = now
        return True

    def ready(self, now: float, settle: float = .3) -> bool:
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
