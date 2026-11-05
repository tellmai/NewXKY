"""Test no-mouse page operations in a fresh headless local browser profile."""
import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tmp/dev-tools'))

from playwright.sync_api import sync_playwright
from newxky.automation import AutoSession
from newxky.browser_bridge import BrowserBridge,decode_snapshot
from newxky.matching import KnowledgeIndex
from verify_automatic_flow import RenderedExam


def verify_bridge():
    from websockets.sync.client import connect
    bridge=BrowserBridge()
    bridge.start()
    endpoint=f"ws://127.0.0.1:{bridge.port}/?token={bridge.token}"
    origin="chrome-extension://"+"a"*32
    ready=threading.Event()
    def client():
        with connect(endpoint,origin=origin) as ws:
            ws.send(json.dumps({"type":"hello","version":1,"clientId":"a"*32,"url":"http://127.0.0.1/exam","title":"本地测试"}))
            for raw in ws:
                message=json.loads(raw)
                if message.get("type")=="ready":ready.set()
                elif message.get("id"):
                    ws.send(json.dumps({"id":message["id"],"ok":True,"data":{"stem":"本地测试题目","options":[],"controls":{},"revision":"test"}}))
    thread=threading.Thread(target=client,daemon=True)
    thread.start()
    assert ready.wait(5)
    bridge.activate()
    assert bridge.snapshot()["stem"]=="本地测试题目"
    from newxky.automation import Action
    bridge.deactivate()
    try:bridge.perform(Action("click",target="next"),{"revision":"test"})
    except RuntimeError:pass
    else:raise AssertionError("paused bridge accepted an action")
    try:
        with connect(endpoint.replace(bridge.token,"0"*48),origin=origin,open_timeout=2):
            raise AssertionError("invalid token accepted")
    except Exception as error:
        assert "403"in str(error),str(error)
    bridge.close()
    thread.join(2)
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome",type=Path,required=True)
    args=parser.parse_args()
    fixture=(ROOT/'tests/fixtures/automatic_exam.html').read_bytes()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.end_headers();self.wfile.write(fixture)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    reports=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=str(args.chrome),headless=True,args=['--no-proxy-server'])
            for scenario in ["normal","missing","native_dialog_resume"]:
                page=browser.new_page(viewport={"width":1200,"height":850})
                page.add_init_script("globalThis.chrome={runtime:{id:'newxky-test',onMessage:{addListener(fn){globalThis.__newxkyReceive=fn;}}}}")
                page.goto(f"http://127.0.0.1:{server.server_port}/?start=1"+("&missing=1"if scenario=="missing"else""))
                page.evaluate((ROOT/'browser_extension/content.js').read_text(encoding='utf-8'))
                if scenario=="native_dialog_resume":
                    page.evaluate("window.showDialog=(text,callback,label)=>{if(label==='确认提交'){if(confirm(text))callback?.()}else{alert(text);callback?.()}}")
                native=[]
                page.on("dialog",lambda dialog:native.append(dialog))
                def request(method,params=None):
                    return page.evaluate("payload=>new Promise(resolve=>globalThis.__newxkyReceive({newxky:true,...payload},{id:'newxky-test'},resolve))",{"method":method,"params":params or {}})
                session=AutoSession(KnowledgeIndex(RenderedExam().questions))
                last=None;paused=False;trace=[]
                for i in range(100):
                    if native:
                        data={**last,"nativeDialog":{"kind":native[0].type,"message":native[0].message}}
                    else:
                        result=request("snapshot");assert result["ok"],result
                        data=result["data"];last=data
                    _,view,dialog=decode_snapshot(data)
                    action=session.advance(view,time.monotonic(),dialog)
                    trace.append((view.number,session.state,action.target,action.kind))
                    if action.kind in {"click","scroll"}:
                        if native:
                            assert action.target in {"confirm","ack"},action
                            native.pop(0).accept()
                        else:
                            result=request("action",{"target":action.target,"kind":action.kind,"selected":action.selected,"amount":action.amount,"revision":data["revision"]})
                            assert result["ok"],result
                        page.wait_for_timeout(35)
                    if scenario=="native_dialog_resume"and not paused and action.target.startswith("option:"):
                        session.stop("本地测试暂停")
                        session.resume(time.monotonic());paused=True
                    if session.done:break
                actual=page.evaluate("getTestResult()")
                assert not any(e['type']=='previous' for e in actual['events']),actual
                assert (not actual['submitted'] and len(session.incomplete)==1)if scenario=="missing"else(actual['submitted'] and session.submitted), (scenario,trace,actual,session.reason)
                if scenario!="missing":assert actual['selections'][1:]==[['C','D'],['A']],actual
                reports.append({"scenario":scenario,"passed":True,"submitted":actual['submitted'],"frames":len(trace),"native_mouse_input":False,"trace":trace})
                print('BROWSER_FLOW_PASSED',scenario,len(trace),flush=True)
                page.close()
            browser.close()
        bridge_ok=verify_bridge()
        report={"ok":True,"browser_scenarios":reports,"authenticated_bridge":bridge_ok,"fresh_headless_profile":True,"system_mouse_control":False}
        output=ROOT/'tmp/validation/browser-no-mouse-report.json'
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('NO_MOUSE_TESTS_PASSED',flush=True)
    finally:server.shutdown()


if __name__=='__main__':main()
