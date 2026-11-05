"""Authenticated loopback connection to the user's explicitly connected tab.

The bridge never enumerates browser tabs or controls the system mouse. Only
the extension selected by the user can connect; every action has a short-lived
lease and a question revision checked again by the content script.
"""
import json
import re
import secrets
import threading
from concurrent.futures import Future
from http import HTTPStatus
from urllib.parse import urlsplit,parse_qs

from PySide6.QtCore import QObject,Signal

from .exam_view import Control,DialogView,ExamView,Rect,VisibleOption
from .ocr import OCRLayout


def dialog_from_message(message,kind="alert",buttons=()):
    text=re.sub(r"\s+","",str(message))
    control=Control("confirm",Rect(420,250,580,290),True)
    if kind=="prompt":
        return DialogView("blocked",message=text)
    if re.search(r"(?:还有|尚有|存在|您有)[1-9]\d*(?:道|题)?(?:题目)?(?:未答|未完成)|还有(?:题目)?未完成|(?:未答|漏答)[1-9]\d*题",text):
        return DialogView("incomplete",message=text)
    wait=re.search(r"(?:还需|请等待|剩余)(\d+)(秒|分钟)",text)
    if wait:
        return DialogView("wait",control,int(wait[1])*(60 if wait[2]=="分钟" else 1),text)
    if re.search(r"(?:全部|所有)(?:题目|试题)?(?:已|均已)?(?:完成|答完|作答)|检查完成|没有未答|无未答",text):
        return DialogView("checked",control,message=text)
    if re.search(r"(?:确认|确定|是否).{0,18}(?:交卷|提交答卷|提交试卷)|(?:交卷|提交答卷).{0,12}(?:确认|确定)",text):
        return DialogView("confirm",control,message=text)
    return DialogView("blocked",message=text)


def decode_snapshot(data):
    if not isinstance(data,dict) or not isinstance(data.get("stem",""),str):
        raise ValueError("浏览器返回的题目结构无效")
    options=data.get("options",[])
    if not isinstance(options,list) or len(options)>12:
        raise ValueError("页面包含多个题目或选项过多，请仅连接当前答题页")
    labels=set()
    parsed=[]
    for i,item in enumerate(options):
        letter=str(item.get("letter",""))
        text=str(item.get("text",""))
        if not letter or letter in labels or len(text)>20000:
            raise ValueError("网页选项标签或内容不完整")
        labels.add(letter)
        checked=item.get("selected")
        parsed.append(VisibleOption(letter,text,Rect(40,100+i*80,900,150+i*80),
                                    checked if isinstance(checked,bool) else None,True,1))
    footer=180+len(parsed)*80
    controls={}
    source=data.get("controls",{})
    for name,x in (("previous",100),("next",400),("finish",400),("submit",700)):
        item=source.get(name)
        if isinstance(item,dict):
            controls[name]=Control(name,Rect(x,footer,x+150,footer+40),bool(item.get("enabled")))
    def count(name):
        value=data.get(name)
        return value if isinstance(value,int) and not isinstance(value,bool) and 0<=value<=10000 else None
    stem=data.get("stem","")[:20000]
    text=stem+"\n"+"\n".join(f"{o.letter}. {o.text}"for o in parsed)
    view=ExamView(stem,tuple(parsed),controls,1000,footer+80,footer,text,
                  count("number"),count("total"),count("answered"),"dom")
    dialog=DialogView("success") if data.get("success") is True else DialogView("unknown")
    native=data.get("nativeDialog")
    html=data.get("dialog")
    if isinstance(native,dict):
        dialog=dialog_from_message(native.get("message",""),native.get("kind","alert"))
    elif isinstance(html,dict):
        dialog=dialog_from_message(html.get("message",""),"html",html.get("buttons",()))
        allowed={"确定","确认","知道了","确认提交","确认交卷","确定交卷","确定提交"}
        if not any(re.sub(r"\s+","",str(b))in allowed for b in html.get("buttons",())):
            dialog=DialogView(dialog.kind,message=dialog.message)
    return OCRLayout(text,(),view.width,view.height),view,dialog


class BrowserBridge(QObject):
    changed=Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.token=secrets.token_hex(24)
        self.port=None
        self.server=None
        self.client=None
        self.binding=None
        self.title=""
        self.pending={}
        self._lock=threading.RLock()
        self._send_lock=threading.Lock()
        self._lease=None
        self._last_snapshot=None
        self._native_dialog=None

    @property
    def connected(self):
        with self._lock:
            return self.client is not None

    @property
    def connection_code(self):
        if self.port is None:
            self.start()
        return f"{self.port}:{self.token}"

    def start(self):
        if self.server is not None:
            return
        from websockets.sync.server import serve
        def authenticate(connection,request):
            provided=parse_qs(urlsplit(request.path).query).get("token",[""])[0]
            if not secrets.compare_digest(provided,self.token):
                return connection.respond(HTTPStatus.FORBIDDEN,"Invalid connection code")
        self.server=serve(self._handle,"127.0.0.1",0,
                          origins=[re.compile(r"chrome-extension://[a-p]{32}")],
                          process_request=authenticate,max_size=1024*1024,close_timeout=1,
                          ping_interval=15,ping_timeout=20)
        self.port=self.server.socket.getsockname()[1]
        self._thread=threading.Thread(target=self.server.serve_forever,daemon=True,name="NewXKY-tab-bridge")
        self._thread.start()

    def _handle(self,connection):
        try:
            hello=json.loads(connection.recv(timeout=5))
            if (hello.get("type")!="hello" or hello.get("version")!=1
                    or not re.fullmatch(r"[a-f0-9]{32}",str(hello.get("clientId","")))
                    or urlsplit(str(hello.get("url",""))).scheme not in {"http","https"}):
                connection.close(1008,"Invalid tab binding")
                return
            with self._lock:
                if self.client is not None:
                    connection.close(1008,"Another tab is connected")
                    return
                self.client=connection
                self.binding=hello["clientId"]
                self.title=str(hello.get("title","答题页"))[:200]
                self._last_snapshot=None
                self._native_dialog=None
            self._send({"type":"ready","version":1})
            self.changed.emit("已连接："+self.title)
            for raw in connection:
                message=json.loads(raw)
                if message.get("type")=="ping":
                    continue
                if message.get("type")=="native_dialog":
                    with self._lock:self._native_dialog=message.get("dialog")
                    continue
                if message.get("type")=="native_dialog_closed":
                    with self._lock:self._native_dialog=None
                    continue
                with self._lock:future=self.pending.pop(str(message.get("id","")),None)
                if future and not future.done():
                    if message.get("ok") is True:
                        future.set_result(message.get("data"))
                    else:
                        future.set_exception(RuntimeError(str(message.get("error","网页操作失败"))[:500]))
        except Exception:
            pass
        finally:
            with self._lock:
                if self.client is connection:
                    self.client=None
                    self._lease=None
                    pending=list(self.pending.values())
                    self.pending.clear()
                else:
                    pending=[]
            for future in pending:
                if not future.done():future.set_exception(RuntimeError("浏览器连接已断开；重新连接后可点击继续"))
            if pending or self.client is None:
                self.changed.emit("浏览器未连接；请在答题标签页中连接扩展")

    def _send(self,message):
        with self._lock:client=self.client
        if client is None:
            raise RuntimeError("浏览器未连接；请先在答题标签页连接扩展")
        with self._send_lock:client.send(json.dumps(message,ensure_ascii=False))

    def activate(self):
        self._lease=secrets.token_hex(16)
        self._send({"type":"lease","value":self._lease})

    def deactivate(self):
        self._lease=None
        if self.connected:
            try:self._send({"type":"lease","value":None})
            except Exception:pass

    def rpc(self,method,params=None,timeout=8):
        request_id=secrets.token_hex(12)
        future=Future()
        with self._lock:self.pending[request_id]=future
        try:
            self._send({"id":request_id,"method":method,"params":params or {}})
            return future.result(timeout)
        except TimeoutError as error:
            raise RuntimeError("网页响应超时；处理页面后可点击继续") from error
        finally:
            with self._lock:self.pending.pop(request_id,None)

    def snapshot(self):
        with self._lock:
            native=self._native_dialog
            previous=self._last_snapshot
        if native and previous:
            return {**previous,"nativeDialog":native}
        data=self.rpc("snapshot")
        decode_snapshot(data)
        with self._lock:self._last_snapshot=data
        return data

    def perform(self,action,snapshot):
        lease=self._lease
        if not lease:
            raise RuntimeError("自动答题已暂停，取消待执行的网页操作")
        target=action.target
        if not target:
            _,view,_=decode_snapshot(snapshot)
            target=next((name for name,c in view.controls.items()if c.box.contains(action.point)),"")
        if snapshot.get("nativeDialog"):
            if target not in {"confirm","ack"}:
                raise RuntimeError("请先处理浏览器弹窗，再点击继续")
            return self.rpc("dialog",{"lease":lease,"accept":True})
        return self.rpc("action",{"lease":lease,"target":target,"kind":action.kind,
                                  "selected":action.selected,"amount":action.amount,
                                  "revision":snapshot.get("revision")})

    def close(self):
        self.deactivate()
        with self._lock:client=self.client
        if client:
            try:client.close()
            except Exception:pass
        if self.server:
            self.server.shutdown()
            self.server=None
