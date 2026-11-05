"""Qt bridge: capture on GUI thread, infer on one worker, input on GUI thread."""
import time

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QRect, QThreadPool, QTimer, Signal, Qt
from PySide6.QtGui import QGuiApplication

from .automation import AutoSession
from .desktop_input import DesktopInput,GlobalEscape
from .browser_bridge import decode_snapshot
from .exam_view import parse_exam, parse_dialog
from .workers import Worker


class AutoController(QObject):
    status = Signal(str)
    observation = Signal(object)
    finished = Signal(object)
    idle = Signal()
    interrupted = Signal(str)

    def __init__(self,ocr,parent=None,bridge=None):
        super().__init__(parent)
        self.ocr = ocr
        self.active = False
        self.busy = False
        self.session = None
        self.desktop = None
        self.bridge=bridge
        self.mode="screen"
        self.index=None
        self.binding=None
        self.escape=None
        self.previous_view=None
        self.force_ocr=False
        self.generation = 0
        self.stopped_at = -1e9
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._tick)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._jobs = set()
        self.interrupted.connect(self.stop,Qt.QueuedConnection)

    def can_resume(self,index,mode=None):
        return (self.session is not None and not self.session.submitted and self.index is index
                and (self.mode!="dom" or mode not in (None,"dom") or self.bridge is not None and self.binding==self.bridge.binding))

    def start(self,index,region=None,*,mode="screen",resume=False):
        if self.active or self.busy:
            return
        self.generation += 1
        if resume and self.can_resume(index,mode):
            self.session.resume(time.monotonic())
        else:
            self.session = AutoSession(index)
        self.index=index
        self.mode=mode
        self.binding=self.bridge.binding if mode=="dom" and self.bridge else None
        self.region = QRect(region) if region is not None else None
        self.previous_view=self.session.last_view
        self.force_ocr=False
        self.active = True
        self.status.emit("从当前题继续自动答题；Esc 暂停" if resume else "从当前题开始自动答题；Esc 暂停")
        if mode=="dom":
            try:
                self.bridge.activate()
                self.escape=GlobalEscape(self.interrupted.emit)
            except Exception as error:
                self.stop(str(error))
                return
        # Let minimization/foreground activation finish before binding a target.
        self.timer.start(400)

    def stop(self,reason="已停止自动答题"):
        if not self.active:
            return
        self.active = False
        self.generation += 1
        self.stopped_at = time.monotonic()
        self.timer.stop()
        if self.desktop is not None:
            self.desktop.close()
            self.desktop = None
        if self.escape is not None:
            self.escape.close()
            self.escape=None
        if self.mode=="dom" and self.bridge:
            self.bridge.deactivate()
        if self.session is not None and not self.session.done:
            self.session.stop(reason)
        self.status.emit(reason)
        self.finished.emit({"reason":reason,"submitted":self.session.submitted if self.session else False,
                            "session_id":self.session.session_id if self.session else None,
                            "records":list(self.session.records) if self.session else []})

    def _tick(self):
        if not self.active or self.busy:
            return
        if self.mode=="dom":
            self._tick_dom()
            return
        try:
            if self.desktop is None:
                screen = QGuiApplication.screenAt(self.region.center())
                if screen is None or not screen.geometry().contains(self.region):
                    raise RuntimeError("请重新框选单块显示器中的浏览器区域")
                self.desktop = DesktopInput(self.region,screen,self.interrupted.emit)
                self.desktop.bind()
            whole_window = self.session.needs_window
            rect = self.desktop.capture_rect(whole_window)
            screen = self.desktop.screen
            origin = screen.geometry().topLeft()
            pixmap = screen.grabWindow(0,rect.x()-origin.x(),rect.y()-origin.y(),rect.width(),rect.height())
            if pixmap.isNull():
                raise RuntimeError("截屏失败，自动答题已停止")
            ratio = pixmap.width()/rect.width()
            if abs(pixmap.height()/rect.height()-ratio) > .02:
                raise RuntimeError("截图缩放不一致，请重新框选")
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(QIODevice.WriteOnly)
            pixmap.save(buffer,"PNG")
            buffer.close()
            content = bytes(data)
        except Exception as error:
            self.stop(str(error))
            return
        token = self.generation
        self.busy = True
        started = time.monotonic()
        fresh,self.force_ocr = self.force_ocr,False
        def infer(_):
            import cv2
            import numpy as np
            layout = (self.ocr.recognize_layout(content,force=True) if fresh else
                      self.ocr.recognize_layout(content,reuse_text=True))
            pixels = cv2.imdecode(np.frombuffer(content,np.uint8),cv2.IMREAD_COLOR)
            return layout,parse_exam(layout,pixels,self.previous_view),parse_dialog(layout,pixels) if whole_window else None
        job = Worker(infer)
        self._jobs.add(job)
        job.signals.result.connect(lambda result:self._observed(token,result,rect,ratio,whole_window,started))
        job.signals.error.connect(lambda error:self.stop(error) if token==self.generation else None)
        job.signals.finished.connect(lambda:self._job_finished(job))
        self.pool.start(job)

    def _job_finished(self,job):
        self._jobs.discard(job)
        self.busy = bool(self._jobs)
        self.idle.emit()
        if self.active and not self.timer.isActive():
            self.timer.start(180)

    def _observed(self,token,result,rect,ratio,whole_window,started):
        if token != self.generation or not self.active:
            return
        try:
            self.desktop.validate(whole_window=whole_window)
            layout,view,dialog = result
            self.previous_view=view
            action = self.session.advance(view,time.monotonic(),dialog)
            self.session.message = action.message
            self.observation.emit({"layout":layout,"view":view,"session":self.session,
                                   "elapsed":time.monotonic()-started})
            self.status.emit(action.message)
            if action.kind == "stop":
                self.stop(action.message)
                return
            if action.kind == "reread":
                self.force_ocr=True
            if action.kind in {"click","scroll"}:
                self.desktop.perform(action,(rect.x(),rect.y()),ratio,whole_window=whole_window)
            self.timer.start(max(action.delay,280 if action.kind in {"click","scroll"} else 100))
        except Exception as error:
            self.stop(str(error))

    def _tick_dom(self):
        if self.bridge is None or not self.bridge.connected or self.bridge.binding!=self.binding:
            self.stop("答题标签页已断开或变化，重新连接后可点击继续")
            return
        token=self.generation
        started=time.monotonic()
        self.busy=True
        def infer(_):
            data=self.bridge.snapshot()
            return data,decode_snapshot(data)
        job=Worker(infer)
        self._jobs.add(job)
        job.signals.result.connect(lambda result:self._dom_observed(token,result,started))
        job.signals.error.connect(lambda error:self.stop(error) if token==self.generation else None)
        job.signals.finished.connect(lambda:self._job_finished(job))
        self.pool.start(job)

    def _dom_observed(self,token,result,started):
        if token!=self.generation or not self.active:
            return
        try:
            data,(layout,view,dialog)=result
            action=self.session.advance(view,time.monotonic(),dialog)
            self.session.message=action.message
            self.previous_view=view
            self.observation.emit({"layout":layout,"view":view,"session":self.session,"elapsed":time.monotonic()-started})
            self.status.emit(action.message)
            if action.kind=="stop":
                self.stop(action.message)
            elif action.kind in {"click","scroll"}:
                self.timer.stop()
                job=Worker(lambda _:self.bridge.perform(action,data))
                self._jobs.add(job)
                job.signals.error.connect(lambda error:self.stop(error) if token==self.generation else None)
                job.signals.finished.connect(lambda:self._job_finished(job))
                self.pool.start(job)
            else:
                self.timer.start(max(100,action.delay))
        except Exception as error:
            self.stop(str(error))
