"""Discover Windows browsers without invoking a shell or user profiles."""
import os
import re
import sys
import asyncio
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BrowserChoice:
    name: str
    path: str
    priority: int
    compatible: bool = True


KNOWN = {
    "chrome.exe": ("Google Chrome", 0),
    "msedge.exe": ("Microsoft Edge", 1),
    "brave.exe": ("Brave", 2),
    "vivaldi.exe": ("Vivaldi", 2),
    "opera.exe": ("Opera", 2),
    "360chrome.exe": ("360 极速浏览器", 2),
    "360se.exe": ("360 安全浏览器", 2),
    "qqbrowser.exe": ("QQ 浏览器", 2),
    "chromium.exe": ("Chromium", 2),
    "360chromex.exe": ("360 极速浏览器 X", 2),
}

UNSUPPORTED = {
    "firefox.exe": "Mozilla Firefox",
    "iexplore.exe": "Internet Explorer",
}


def browser_path_key(path):
    return str(Path(path).resolve()).casefold() if path else ""


def executable_from_command(command):
    command = os.path.expandvars(str(command)).strip()
    match = re.match(r'^"([^"]+\.exe)"|^(.+?\.exe)(?:\s|$)', command, re.I)
    return (match[1] or match[2]) if match else ""


def _registry_paths():
    paths = []
    try:
        import winreg
    except ImportError:
        return paths
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            for exe in (*KNOWN, *UNSUPPORTED):
                try:
                    with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}", 0, winreg.KEY_READ | view) as key:
                        paths.append(winreg.QueryValue(key, None))
                except OSError:
                    pass
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Clients\StartMenuInternet", 0, winreg.KEY_READ | view) as root:
                    for index in range(winreg.QueryInfoKey(root)[0]):
                        name = winreg.EnumKey(root, index)
                        try:
                            with winreg.OpenKey(root, name + r"\shell\open\command") as key:
                                paths.append(winreg.QueryValue(key, None))
                        except OSError:
                            pass
            except OSError:
                pass
    return paths


def discover_browsers(*, include_unsupported=False):
    raw = list(_registry_paths())
    locations = (
        "Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe",
        "BraveSoftware/Brave-Browser/Application/brave.exe", "Vivaldi/Application/vivaldi.exe",
        "Programs/Opera/opera.exe", "Opera/opera.exe", "Chromium/Application/chrome.exe",
        "360/360Chrome/Chrome/Application/360chrome.exe", "360/360se6/Application/360se.exe",
        "Tencent/QQBrowser/QQBrowser.exe",
        "360/360ChromeX/Chrome/Application/360ChromeX.exe",
        "Mozilla Firefox/firefox.exe", "Programs/Mozilla Firefox/firefox.exe",
        "Internet Explorer/iexplore.exe",
    )
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        if os.environ.get(variable):
            raw.extend(str(Path(os.environ[variable]) / path) for path in locations)
    choices, seen = [], set()
    for value in raw:
        path = executable_from_command(value)
        key = browser_path_key(path)
        name = Path(path).name.lower()
        if path and key not in seen and Path(path).is_file():
            compatible = name in KNOWN
            if not compatible and not include_unsupported:
                continue
            label, priority = KNOWN.get(name, (UNSUPPORTED.get(name, Path(path).stem), 4))
            choices.append(BrowserChoice(label, path, priority, compatible))
            seen.add(key)
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    for relative in ("chrome/chrome-win64/chrome.exe", "tools/chrome/chrome-win64/chrome.exe"):
        path = base / relative
        if path.is_file() and browser_path_key(path) not in seen:
            choices.append(BrowserChoice("随附 Chrome for Testing", str(path), 3))
            seen.add(browser_path_key(path))
    return sorted(choices, key=lambda item: (item.priority, item.name.casefold(), item.path.casefold()))


async def launch_browser(playwright, explicit="", headless=False, progress=lambda _: None):
    name = Path(explicit).name.lower()
    if explicit and name in UNSUPPORTED:
        raise ValueError(f"当前自动化模块不兼容 {UNSUPPORTED[name]}，请选择 Chrome / Edge 等兼容浏览器")
    label = KNOWN.get(name, ("指定浏览器", -1))[0]
    choices = [BrowserChoice(label, explicit, -1)] if explicit else discover_browsers()
    if not choices:
        raise ValueError("未找到兼容浏览器，请选择 Chrome / Edge 程序或检查随附浏览器文件")
    for choice in choices:
        try:
            browser = await playwright.chromium.launch(executable_path=choice.path, headless=headless)
        except Exception:
            progress(f"{choice.name} 启动失败，正在检查其他可用浏览器" if not explicit else "手动指定的浏览器启动失败")
            continue
        progress(f"使用浏览器：{choice.name}")
        return browser, choice
    raise ValueError("可用浏览器均启动失败，请检查软件文件或手动选择兼容浏览器程序")


@dataclass
class BrowserHandle:
    process: subprocess.Popen
    profile: Path
    endpoint: str
    choice: BrowserChoice


async def launch_retained_browser(data_dir, explicit="", *, headless=False, progress=lambda _: None):
    """Launch an independent profile; disconnecting the driver leaves it open."""
    if explicit and Path(explicit).name.lower() in UNSUPPORTED:
        raise ValueError("此浏览器不支持考试登录，请选择 Chrome / Edge 等 Chromium 浏览器")
    choices = ([BrowserChoice(KNOWN.get(Path(explicit).name.lower(), ("自定义浏览器", -1))[0], explicit, -1)]
               if explicit else discover_browsers())
    if not choices:
        raise ValueError("未找到兼容浏览器，请指定浏览器程序或安装 Chrome / Edge")
    for choice in choices:
        profile = Path(data_dir).resolve() / "browser-profiles" / uuid.uuid4().hex
        profile.mkdir(parents=True)
        arguments = [choice.path, f"--user-data-dir={profile}", "--remote-debugging-address=127.0.0.1",
                     "--remote-debugging-port=0", "--no-first-run", "--no-default-browser-check",
                     "--start-maximized", "about:blank"]
        if headless:
            arguments.insert(1, "--headless=new")
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        try:
            process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, creationflags=flags,
                                       start_new_session=sys.platform != "win32")
        except OSError:
            if explicit:
                raise ValueError("所选浏览器启动失败，请检查程序文件") from None
            continue
        progress(f"正在打开 {choice.name}")
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                port, socket_path = (profile / "DevToolsActivePort").read_text(encoding="utf-8").splitlines()[:2]
                if 0 < int(port) < 65536 and socket_path.startswith("/devtools/browser/"):
                    return BrowserHandle(process, profile, f"http://127.0.0.1:{port}", choice)
            except (OSError, ValueError):
                pass
            if process.poll() is not None:
                break
            await asyncio.sleep(.1)
        if explicit:
            raise ValueError("浏览器没有提供本机连接入口，请使用新版 Chrome / Edge；已打开的窗口可手动保留")
    raise ValueError("未能连接兼容浏览器，请手动指定 Chrome / Edge")
