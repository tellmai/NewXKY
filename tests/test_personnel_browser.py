"""Real, isolated browsers against a local site; no real credentials or input."""
import asyncio
import base64
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

from newxky.browsers import discover_browsers, launch_retained_browser
from newxky.identities import Candidate, SiteConfig
from newxky.login_session import CaptchaFailure, LoginFailure, SiteSession


ROOT = Path(__file__).resolve().parents[1]
PERSON = Candidate(2, "黔江区", "演示考生", "110101199001010010")
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jC1sAAAAASUVORK5CYII=")
ENTRY = '<div id="districtGrid"><button class="district-card" aria-label="进入黔江区考试入口" onclick="location.href=\'/exam/login\'">黔江区</button></div>'
LOGIN = '''<div id="roleSwitch"><button data-role="student" onclick="this.className='active';username.placeholder='请输入姓名';password.placeholder='请输入身份证号码'">考生登录</button></div>
<input id="username"><input id="password"><input id="captchaInput"><div id="captchaImage" onclick="refresh()"><img id="captcha" src="/captcha.png?n=0"></div>
<div id="loginNotice" hidden></div><div id="pageLoading" hidden></div><button id="loginButton" onclick="login()">登录</button>
<script>let n=0;function refresh(){captcha.src='/captcha.png?n='+(++n)}
async function login(){const r=await fetch('/submit',{method:'POST',body:JSON.stringify({name:username.value,id:password.value,code:captchaInput.value})});const t=await r.text();if(t==='ok'){location.href='/exam/user/home'}else{refresh();loginNotice.hidden=false;loginNotice.textContent=t}}</script>'''
HOME = '''<h1>演示考生</h1><a>个人资料</a><button data-action="exam">进入考试</button><div id="actions"></div><section id="examScanModal" hidden>请本人完成人员验证<button id="verify" onclick="fetch('/verify',{method:'POST'}).then(()=>location.href='/exam/user/exam/1?start=0')">人工验证</button></section><script src="/home.js"></script>'''
HOME_SCRIPT = '''document.querySelector('[data-action=exam]').onclick=async()=>{await fetch('/enter',{method:'POST'});actions.innerHTML='<button id="start">开始考试</button>';document.querySelector('#start').onclick=async()=>{await fetch('/start',{method:'POST'});examScanModal.hidden=false}};'''


@pytest.fixture
def local_site():
    state = {"posts": 0, "enters": 0, "starts": 0, "verifications": 0, "identity_error": False}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlparse(self.path).path
            mime = "text/html; charset=utf-8"
            if path == "/captcha.png":
                body, mime = PNG, "image/png"
            elif path == "/home.js":
                time.sleep(.15)
                body, mime = HOME_SCRIPT.encode(), "text/javascript"
            elif path.startswith("/exam/user/exam/"):
                body = (ROOT / "tests/fixtures/automatic_exam.html").read_bytes()
            else:
                body = (ENTRY if path == "/exam/" else HOME if path == "/exam/user/home" else LOGIN).encode()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            import json
            data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.path == "/submit":
                state["posts"] += 1
                values = json.loads(data)
                assert values["name"] == PERSON.name and values["id"] == PERSON.id_number
                result = "姓名或身份证号不匹配" if state["identity_error"] else "ok" if values["code"] == "TEST" else "验证码错误"
            else:
                state[{"/enter": "enters", "/start": "starts", "/verify": "verifications"}[self.path]] += 1
                result = "ok"
            body = result.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/exam/", state
    server.shutdown()
    server.server_close()
    thread.join()


class FixedOCR:
    def __init__(self, code="TEST"):
        self.code = code
    async def recognize(self, _):
        return self.code


def browser_choices():
    choices = discover_browsers()
    if not choices:
        pytest.skip("No installed Chromium browser")
    return choices


async def close_test_browser(playwright, handle):
    try:
        browser = await playwright.chromium.connect_over_cdp(handle.endpoint, timeout=3000)
        cdp = await browser.new_browser_cdp_session()
        await cdp.send("Browser.close")
    except Exception:
        pass


def test_login_human_verification_answer_submission_and_two_retained_browsers(local_site, tmp_path):
    from playwright.async_api import async_playwright
    from newxky.automation import AutoSession
    from newxky.browser_bridge import decode_snapshot
    from newxky.matching import KnowledgeIndex
    from newxky.models import Question
    url, state = local_site
    choices = browser_choices()
    async def run():
        handles = []
        try:
            for choice in choices[:2]:
                handle = await launch_retained_browser(tmp_path, choice.path, headless=True)
                handles.append(handle)
                async with async_playwright() as p:
                    browser = await p.chromium.connect_over_cdp(handle.endpoint)
                    session = SiteSession(p, SiteConfig(url, choice.path, 5000, True), browser=browser)
                    await session.login(PERSON, FixedOCR())
                    assert await session.prepare_exam() == "等待人工验证"
                    assert state["verifications"] == 0
                # Reconnect after the login driver has exited; the same page survives.
                async with async_playwright() as p:
                    browser = await p.chromium.connect_over_cdp(handle.endpoint)
                    page = next(page for page in browser.contexts[0].pages
                                if urlparse(page.url).path == "/exam/user/home")
                    assert await page.locator("#examScanModal").is_visible()
                    if len(handles) == 1:
                        # Simulate the human verification step only in this local fixture.
                        await page.locator("#verify").click()
                        await page.wait_for_url("**/exam/user/exam/1?start=0")
                        await page.evaluate("globalThis.chrome={runtime:{id:'newxky-test',onMessage:{addListener(fn){globalThis.__receive=fn}}}}")
                        await page.evaluate((ROOT / "browser_extension/content.js").read_text(encoding="utf-8"))
                        data = await page.evaluate("bank")
                        questions = [Question(i+1, q["kind"], q["stem"], q["options"], tuple(q["answers"]), (1,))
                                     for i, q in enumerate(data)]
                        auto = AutoSession(KnowledgeIndex(questions))
                        for _ in range(100):
                            result = await page.evaluate("()=>new Promise(resolve=>__receive({newxky:true,method:'snapshot'}, {id:'newxky-test'},resolve))")
                            assert result["ok"]
                            snapshot = result["data"]
                            _, view, dialog = decode_snapshot(snapshot)
                            action = auto.advance(view, time.monotonic(), dialog)
                            if action.kind == "stop":
                                assert auto.submitted, action.message
                                break
                            if action.kind in {"click", "scroll"}:
                                params = {"kind": action.kind, "target": action.target, "revision": snapshot["revision"],
                                          "amount": action.amount, "selected": action.selected}
                                response = await page.evaluate("params=>new Promise(resolve=>__receive({newxky:true,method:'action',params},{id:'newxky-test'},resolve))", params)
                                assert response["ok"], response
                            await asyncio.sleep(.03)
                        else:
                            pytest.fail("automatic answering did not finish")
                        result = await page.evaluate("getTestResult()")
                        assert result["submitted"]
                        assert [sorted(v) for v in result["selections"]] == [sorted(v) for v in result["expected"]]
                        state["verifications"] = 0
            async with async_playwright() as p:
                first = await p.chromium.connect_over_cdp(handles[0].endpoint)
                assert await first.contexts[0].pages[0].locator("#success").is_visible()
                if len(handles) == 2:
                    assert handles[0].profile != handles[1].profile
                    assert handles[0].choice.path != handles[1].choice.path
            assert state["posts"] == state["enters"] == state["starts"] == len(handles)
        finally:
            async with async_playwright() as p:
                for handle in handles:
                    await close_test_browser(p, handle)
    asyncio.run(run())


def test_login_captcha_retry_and_manual_browser_fallback(local_site, tmp_path):
    from playwright.async_api import async_playwright
    url, state = local_site
    choice = browser_choices()[0]
    async def run():
        handle = await launch_retained_browser(tmp_path, choice.path, headless=True)
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(handle.endpoint)
                session = SiteSession(p, SiteConfig(url, choice.path, 5000, True), browser=browser)
                with pytest.raises(CaptchaFailure):
                    await session.login(PERSON, FixedOCR("wrong"))
                assert state["posts"] == 3
                waiting = asyncio.create_task(session.wait_manual_login(PERSON, timeout=5))
                await session.page.locator("#captchaInput").fill("TEST")
                await session.page.locator("#loginButton").click()
                await waiting
                assert state["posts"] == 4
                assert await session.prepare_exam() == "等待人工验证"
            finally:
                await close_test_browser(p, handle)
    asyncio.run(run())


def test_identity_failure_does_not_retry_or_start_exam(local_site, tmp_path):
    from playwright.async_api import async_playwright
    url, state = local_site
    state["identity_error"] = True
    choice = browser_choices()[0]
    async def run():
        handle = await launch_retained_browser(tmp_path, choice.path, headless=True)
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(handle.endpoint)
                session = SiteSession(p, SiteConfig(url, choice.path, 5000, True), browser=browser)
                with pytest.raises(LoginFailure):
                    await session.login(PERSON, FixedOCR())
                assert state["posts"] == 1 and state["enters"] == state["starts"] == 0
            finally:
                await close_test_browser(p, handle)
    asyncio.run(run())


def test_cancelling_personnel_worker_preserves_browser(local_site, tmp_path, monkeypatch):
    from playwright.async_api import async_playwright
    from PySide6.QtWidgets import QApplication
    from newxky import personnel_controller
    url, _ = local_site
    choice = browser_choices()[0]
    app = QApplication.instance() or QApplication([])
    entered = threading.Event()
    async def headless_launch(data_dir, explicit, **kwargs):
        return await launch_retained_browser(data_dir, explicit, headless=True, **kwargs)
    async def pending_login(self, candidate, ocr):
        await self.open()
        entered.set()
        await asyncio.sleep(30)
    monkeypatch.setattr(personnel_controller, "launch_retained_browser", headless_launch)
    monkeypatch.setattr(personnel_controller.SiteSession, "login", pending_login)
    worker = personnel_controller.PersonnelWorker(tmp_path, PERSON, SiteConfig(url, choice.path, 5000, True))
    failures = []
    worker.failed.connect(failures.append)
    worker.start()
    try:
        assert entered.wait(10)
        worker.cancel()
        assert worker.wait(10000)
        app.processEvents()
        assert failures and "保留" in failures[0]
        async def inspect():
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(worker.handle.endpoint)
                assert any(urlparse(page.url).path == "/exam/" for page in browser.contexts[0].pages)
        asyncio.run(inspect())
    finally:
        worker.cancel()
        worker.wait(10000)
        if worker.handle is not None:
            async def cleanup():
                async with async_playwright() as p:
                    await close_test_browser(p, worker.handle)
            asyncio.run(cleanup())
