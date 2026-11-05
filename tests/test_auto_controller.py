import os

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from PySide6.QtWidgets import QApplication

from newxky.auto_controller import AutoController
from newxky.automation import AutoSession
from newxky.matching import KnowledgeIndex
from newxky.ocr import LocalOCR


def application():
    return QApplication.instance() or QApplication([])


def test_stale_worker_cannot_validate_or_click_after_cancellation():
    app=application()
    controller=AutoController(LocalOCR())
    controller.active=True
    controller.generation=2
    class Desktop:
        def validate(self,**kwargs):
            raise AssertionError("stale OCR reached native input")
    controller.desktop=Desktop()
    controller._observed(1,None,None,None,False,0)
    assert controller.active


def test_stop_invalidates_pending_work_and_releases_native_hooks():
    app=application()
    controller=AutoController(LocalOCR())
    controller.session=AutoSession(KnowledgeIndex([]))
    controller.active=True
    closed=[]
    class Desktop:
        def close(self):
            closed.append(True)
    controller.desktop=Desktop()
    reports=[]
    controller.finished.connect(reports.append)
    old=controller.generation
    controller.stop("Esc 停止")
    assert not controller.active and controller.generation>old
    assert closed==[True] and reports[0]["reason"]=="Esc 停止"


def test_main_ui_has_automatic_button_and_locks_conflicting_controls(tmp_path):
    from newxky.ui import MainWindow
    from PySide6.QtCore import QRect
    from newxky.models import Bank,Question
    app=application()
    window=MainWindow(tmp_path)
    window.region=QRect(20,20,500,500)
    window.bank=Bank([Question(1,"判断","测试题目",{"A":"正确","B":"错误"},("A",),(1,))])
    window.auto_mode.setCurrentIndex(1)
    window.refresh_controls()
    assert window.auto_button.text()=="启动自动答题" and window.auto_button.isEnabled()
    window.auto.active=True
    window.refresh_controls()
    assert window.auto_button.text()=="暂停自动答题"
    assert not window.import_button.isEnabled() and not window.select_button.isEnabled()
    assert not window.start_button.isEnabled() and not window.search_button.isEnabled()
    window.auto.active=False
    window.close()


def test_no_mouse_controller_executes_only_the_browser_adapter(monkeypatch):
    import time
    from newxky import auto_controller
    from newxky.browser_bridge import decode_snapshot
    from newxky.models import Question
    app=application()
    calls=[]
    class Bridge:
        binding="test-tab"
        connected=True
        def perform(self,action,data):calls.append(action.target)
        def deactivate(self):pass
    class Pool:
        def start(self,job):job.run()
    monkeypatch.setattr(auto_controller,"DesktopInput",lambda *a:(_ for _ in()).throw(AssertionError("mouse adapter used")))
    q=Question(1,"单选","本地浏览器测试题目",{"A":"选项甲","B":"选项乙"},("B",),(1,))
    index=KnowledgeIndex([q])
    c=AutoController(LocalOCR(),bridge=Bridge())
    c.pool=Pool();c.active=True;c.mode="dom";c.index=index;c.binding="test-tab"
    c.session=AutoSession(index)
    data={"stem":q.stem,"options":[{"letter":k,"text":v,"selected":False}for k,v in q.options.items()],
          "controls":{"previous":{"enabled":True},"next":{"enabled":True}},"revision":"snapshot"}
    c._dom_observed(c.generation,(data,decode_snapshot(data)),time.monotonic())
    assert calls==["option:B"]
    c.stop("test completed")


def test_paused_main_ui_offers_continue_instead_of_starting_over(tmp_path):
    from newxky.ui import MainWindow
    from PySide6.QtCore import QRect
    app=application()
    window=MainWindow(tmp_path)
    window.auto_mode.setCurrentIndex(1)
    window.region=QRect(20,20,500,500)
    window.auto.start(window.index,window.region)
    window.auto.stop("暂停")
    window.refresh_controls()
    assert window.auto_button.text()=="继续自动答题"
    assert window.floating.auto_button.text()=="继续自动答题"
    window.close()
