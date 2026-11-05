"""Login one selected person, detach, then let screen automation take over."""
import asyncio
import threading

from PySide6.QtCore import QThread, Signal

from .browsers import launch_retained_browser
from .login_session import CaptchaFailure, SiteSession
from .privacy import redact


class PersonnelWorker(QThread):
    progress = Signal(str)
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, data_dir, candidate, config, parent=None):
        super().__init__(parent)
        self.data_dir, self.candidate, self.config = data_dir, candidate, config
        self.cancelled = threading.Event()
        self.loop = self.task = None
        self.handle = None

    def cancel(self):
        self.cancelled.set()
        loop, task = self.loop, self.task
        if loop is not None and task is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass

    def run(self):
        try:
            asyncio.run(self._run())
        except asyncio.CancelledError:
            self.failed.emit("已停止加载人员，已打开的浏览器保留")
        except Exception as error:
            self.failed.emit(redact(str(error), (self.candidate.id_number,)))
        finally:
            self.loop = self.task = None

    async def _run(self):
        from playwright.async_api import async_playwright
        from .login_ocr import LocalOCR

        self.loop, self.task = asyncio.get_running_loop(), asyncio.current_task()
        if self.cancelled.is_set():
            raise asyncio.CancelledError
        self.config.validate()
        ocr = LocalOCR()
        try:
            self.handle = await launch_retained_browser(self.data_dir, self.config.chrome_path,
                                                       progress=self.progress.emit)
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(self.handle.endpoint, timeout=self.config.timeout_ms)
                session = SiteSession(playwright, self.config, self.progress.emit, browser=browser)
                try:
                    await session.login(self.candidate, ocr)
                except CaptchaFailure:
                    await session.wait_manual_login(self.candidate)
                stage = await session.prepare_exam()
                await session.page.bring_to_front()
                self.ready.emit({"handle": self.handle, "stage": stage})
                # The context belongs to the separately launched browser. Stop
                # only the driver; no browser/context/page close is sent here.
        finally:
            ocr.close()
