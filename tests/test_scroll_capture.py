from PySide6.QtCore import QRect
from PySide6.QtGui import QColor,QPixmap

from newxky.models import Bank,Question
from newxky.region_scroll import ScrollUnavailable
from newxky.ui import MainWindow


class Manager:
    server_url=''
    last_error=''
    expired=False

    @property
    def can_use(self):return not self.expired

    def remaining_seconds(self):return 2399 if not self.expired else 0

    def reload_lease(self):pass

    def touch(self):pass


def setup(tmp_path,monkeypatch):
    q=Question(1,'单选','这是用于完整截图流程验证的一道题目（）',
               {'A':'第一项完整内容','B':'第二项完整内容','C':'第三项完整内容','D':'第四项完整内容'},
               ('B',),(1,))
    frames=[q.stem+'\n请选择一个答案\nA 第三项完整内容\nB 第一项完整内容',
            'B 第一项完整内容\nC 第四项完整内容\nD 第二项完整内容']
    state={'frame':0,'time':100.0,'actions':[]}
    monkeypatch.setattr('newxky.ui.time.monotonic',lambda:state['time'])
    monkeypatch.setattr(MainWindow,'warm_ocr',lambda self:None)
    monkeypatch.setattr(MainWindow,'start_license_refresh',lambda self:None)
    window=MainWindow(Manager(),Bank([q]),data_dir=tmp_path,app_dir=tmp_path)
    window.region=QRect(0,0,400,300)
    window.running=True
    window.ocr.recognize=lambda content,**kwargs:frames[state['frame']]
    window.launch=lambda work,result,error:result(work(None))

    class Screen:
        def geometry(self):return QRect(0,0,800,800)

        def grabWindow(self,*args):
            pixmap=QPixmap(400,300)
            pixmap.fill(QColor('white' if state['frame']==0 else 'gray'))
            return pixmap

    monkeypatch.setattr('newxky.ui.QGuiApplication.screenAt',lambda point:Screen())

    class Scroller:
        def reset(self):pass

        def interrupted(self):return False

        def wheel(self,region,direction):
            state['actions'].append(direction)
            state['frame']=1 if direction<0 else 0

    window.scroller=Scroller()
    return window,state


def poll(window,state,count=1):
    for _ in range(count):
        state['time']+=.6
        window.capture()


def test_real_capture_change_preserves_scan_and_verifies_actual_letters(tmp_path,monkeypatch):
    window,state=setup(tmp_path,monkeypatch)
    try:
        poll(window,state,2)
        assert window._scroll_reader is not None
        assert state['actions']==[-1]
        assert window.answer.text()=='—'
        poll(window,state,2)
        assert window._scroll_reader is None
        assert window.status.text()=='已核对网页选项'
        assert window.answer.text()=='D'
    finally:window.close()


def test_pause_discards_scroll_state_and_sends_no_further_input(tmp_path,monkeypatch):
    window,state=setup(tmp_path,monkeypatch)
    try:
        poll(window,state,2)
        window.stop_monitor()
        assert window._scroll_reader is None
        poll(window,state,5)
        assert state['actions']==[-1] and window.answer.text()=='—'
    finally:window.close()


def test_scroll_failure_returns_an_explicit_red_bank_reference(tmp_path,monkeypatch):
    window,state=setup(tmp_path,monkeypatch)
    def unavailable(*args):raise ScrollUnavailable('本地测试无法滚动')
    window.scroller.wheel=unavailable
    try:
        poll(window,state,2)
        assert '题库顺序' in window.answer_title.text()
        assert 'c62828' in window.answer.styleSheet()
        assert window.answer.text()=='B'
        assert '本地测试无法滚动' in window.message.text()
    finally:window.close()


def test_expiry_stops_inflight_scroll_before_another_wheel(tmp_path,monkeypatch):
    window,state=setup(tmp_path,monkeypatch)
    try:
        poll(window,state,2)
        window.manager.expired=True
        poll(window,state,2)
        assert not window.running and window._scroll_reader is None
        assert state['actions']==[-1]
    finally:window.close()


def test_escape_stops_auto_scroll(tmp_path,monkeypatch):
    window,state=setup(tmp_path,monkeypatch)
    try:
        poll(window,state,2)
        window.scroller.interrupted=lambda:True
        poll(window,state)
        assert not window.running and 'Esc' in window.status.text()
        assert state['actions']==[-1]
    finally:window.close()
