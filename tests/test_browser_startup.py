import asyncio
from pathlib import Path

from newxky import browsers


def test_successful_launcher_handoff_waits_for_child_connection_file(tmp_path,monkeypatch):
    executable=tmp_path/"msedge.exe"
    executable.touch()
    profiles=[]
    class Process:
        def __init__(self,arguments,**kwargs):
            profiles.append(Path(next(a.split("=",1)[1] for a in arguments if a.startswith("--user-data-dir="))))
        def poll(self):return 0
    sleeps=[]
    async def ready_after_handoff(delay):
        sleeps.append(delay)
        if len(sleeps)==2:
            (profiles[0]/"DevToolsActivePort").write_text("12345\n/devtools/browser/local-test\n",encoding="utf-8")
    monkeypatch.setattr(browsers.subprocess,"Popen",Process)
    monkeypatch.setattr(browsers.asyncio,"sleep",ready_after_handoff)
    handle=asyncio.run(browsers.launch_retained_browser(tmp_path,str(executable),headless=True))
    assert handle.endpoint=="http://127.0.0.1:12345" and len(sleeps)==2
