"""Portable ZIP built on the bundled CPython runtime (no PyInstaller needed).

The release machine may have no pip, no PyInstaller and no network, so this
script assembles the application next to the ``runtime/`` folder that already
contains every dependency, and compiles ``NewXKY.exe`` with the C# compiler
that ships with Windows. The result is the same user experience as the
PyInstaller build: extract the ZIP, double-click NewXKY.exe.

Usage:
    runtime\\python.exe scripts\\package_runtime.py
    runtime\\python.exe scripts\\package_runtime.py --keep-runtime   # no pruning
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from newxky import __version__  # noqa: E402
from newxky.default_bank import CACHE_NAME, BUNDLE_DIRECTORY, SOURCE_PDF_NAME  # noqa: E402
from newxky.license_config import LICENSE_SERVER_URL  # noqa: E402

VERSION = __version__
CSC_CANDIDATES = (
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe",
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET/Framework/v4.0.30319/csc.exe",
)

# Never used by the client: distribution tooling (openpyxl), the bank builder
# (pdfplumber/pdfminer), and packages left over from the removed automation
# feature. rapidocr keeps shapely, pyyaml, six, tqdm and pyclipper.
PRUNE_PACKAGES = (
    "playwright", "pyee", "greenlet",
    "ddddocr", "pypdfium2", "pypdfium2_cfg", "pypdfium2_cli", "pypdfium2_raw",
    "pdfminer", "pdfplumber", "websockets",
    "cryptography", "cffi", "pycparser",
    "openpyxl", "et_xmlfile",
)
PRUNE_DIRECTORIES = {"__pycache__"}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pruned(name: str) -> bool:
    if name in PRUNE_DIRECTORIES:
        return True
    lowered = name.lower()
    return any(lowered == package or lowered.startswith((package + "-", package + "."))
               for package in PRUNE_PACKAGES)


def copy_runtime(source: Path, target: Path, *, keep: bool) -> dict:
    before = sum(file.stat().st_size for file in source.rglob("*") if file.is_file())

    def ignore(directory, names):
        dropped = {name for name in names if name in PRUNE_DIRECTORIES}
        if not keep:
            dropped |= {name for name in names if pruned(name)}
        return dropped

    shutil.copytree(source, target, ignore=ignore)
    after = sum(file.stat().st_size for file in target.rglob("*") if file.is_file())
    return {"bytes_before": before, "bytes_after": after}


def check_runtime(runtime: Path) -> None:
    python = runtime / "pythonw.exe"
    if not python.is_file():
        raise SystemExit(f"runtime 不完整，缺少 {python}")
    for dll in ("python311.dll", "vcruntime140.dll"):
        if not (runtime / dll).is_file():
            raise SystemExit(f"runtime 缺少 {dll}")
    for plugin in ("PySide6/plugins/platforms/qwindows.dll",):
        if not (runtime / "Lib/site-packages" / plugin).is_file():
            raise SystemExit(f"runtime 缺少 {plugin}")


def verify_bank() -> dict:
    bank = ROOT / BUNDLE_DIRECTORY / CACHE_NAME
    manifest = ROOT / BUNDLE_DIRECTORY / "manifest.json"
    pdf = ROOT / BUNDLE_DIRECTORY / SOURCE_PDF_NAME
    if not bank.is_file() or not manifest.is_file():
        raise SystemExit("题库/default-bank.json 或 manifest.json 缺失")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("cache_sha256") != digest(bank):
        raise SystemExit("题库缓存与 manifest 不一致，请重新执行 scripts/build.ps1")
    if not pdf.is_file():
        raise SystemExit(f"缺少源 PDF：{pdf}")
    if data.get("pdf_sha256") != digest(pdf):
        raise SystemExit("源 PDF 与 manifest 记录的哈希不一致")
    return data


def copy_sources(app: Path) -> None:
    shutil.copy2(ROOT / "main.py", app / "main.py")
    shutil.copy2(ROOT / "portable_start.py", app / "portable_start.py")
    package = app / "newxky"
    package.mkdir(exist_ok=True)
    for source in sorted((ROOT / "newxky").glob("*.py")):
        shutil.copy2(source, package / source.name)
    shutil.copytree(ROOT / "assets", app / "assets",
                    ignore=lambda directory, names: {name for name in names if name.endswith(".svg")})
    bundle = app / BUNDLE_DIRECTORY
    bundle.mkdir(exist_ok=True)
    shutil.copy2(ROOT / BUNDLE_DIRECTORY / CACHE_NAME, bundle / CACHE_NAME)
    shutil.copy2(ROOT / BUNDLE_DIRECTORY / "manifest.json", bundle / "manifest.json")
    shutil.copy2(ROOT / "README.md", app / "使用说明.md")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", app / "THIRD_PARTY_NOTICES.md")


def compile_launcher(app: Path) -> Path:
    compiler = next((path for path in CSC_CANDIDATES if path.is_file()), None)
    if compiler is None:
        raise SystemExit("找不到 .NET 编译器 csc.exe，无法生成 NewXKY.exe")
    target = app / "NewXKY.exe"
    result = subprocess.run(
        [str(compiler), "/nologo", "/target:winexe", "/platform:anycpu", "/codepage:65001",
         "/optimize+", f"/win32icon:{ROOT / 'assets' / 'NewXKY.ico'}",
         f"/out:{target}", str(ROOT / "scripts" / "launcher.cs")],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0 or not target.is_file():
        raise SystemExit("NewXKY.exe 编译失败：\n" + (result.stdout or "") + (result.stderr or ""))
    return target


LAUNCHER_CMD = """@echo off
rem Fallback launcher: identical to double-clicking NewXKY.exe.
cd /d "%~dp0"
if not exist "NewXKY.exe" (echo NewXKY.exe is missing. & pause & exit /b 1)
start "" "NewXKY.exe"
"""

CHECKER_CMD = r"""@echo off
rem ASCII only: cmd.exe parses batch files with the console code page.
setlocal
cd /d "%~dp0"
echo ==========================================
echo    NewXKY runtime check
echo ==========================================
echo.
ver
set "BUILD="
for /f "tokens=4,5,6 delims=. " %%A in ('ver') do set "BUILD=%%C"
set "TOOOLD="
for /f "delims=0123456789" %%X in ("%BUILD%") do set "BUILD=0"
if not defined BUILD set "BUILD=0"
if "%BUILD%"=="" set "BUILD=0"
if %BUILD% LSS 17763 (
  echo   [WARN] Windows build %BUILD% is older than 1809 ^(17763^).
  set "TOOOLD=1"
) else (
  echo   [ ok ] Windows build %BUILD% ^(1809 or newer^)
)
echo.
set "MISSING="
for %%F in (
  "NewXKY.exe"
  "portable_start.py"
  "main.py"
  "runtime\pythonw.exe"
  "runtime\python311.dll"
  "runtime\vcruntime140.dll"
  "runtime\Lib\site-packages\PySide6\Qt6Core.dll"
  "runtime\Lib\site-packages\PySide6\plugins\platforms\qwindows.dll"
  "runtime\Lib\site-packages\rapidocr_onnxruntime\__init__.py"
) do (
  if exist "%%~F" (echo   [ ok ] %%~F) else (echo   [MISS] %%~F & set "MISSING=1")
)
set "BANK="
for /d %%D in ("*") do if exist "%%~D\default-bank.json" set "BANK=1"
if defined BANK (echo   [ ok ] question bank found) else (
  echo   [MISS] question bank: default-bank.json & set "MISSING=1"
)
echo.
reg query "HKLM\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full" /v Release >nul 2>&1
if errorlevel 1 (
  echo   [WARN] .NET Framework 4.x not found - NewXKY.exe is a tiny launcher
  echo          that needs it. Windows 10 1809+ ships it.
  set "TOOOLD=1"
) else (
  echo   [ ok ] .NET Framework 4.x present
)
echo.
if defined MISSING (
  echo RESULT: INCOMPLETE - extract the whole ZIP again and keep runtime/
  echo         Do not copy NewXKY.exe alone. Do not run from inside the ZIP
  echo         or from a OneDrive-synced folder.
) else if not defined TOOOLD (
  echo RESULT: FILES OK - if it still fails, install
  echo         "Microsoft Visual C++ 2015-2022 Redistributable (x64)".
)
echo.
echo Requires Windows 10 1809 x64 or newer.
echo See the readme file in this folder for details.
echo.
pause
"""

USAGE_TXT = """NewXKY 区域答题助手 V{version} 免安装版

1. 将整个 ZIP 解压到普通文件夹（不要在压缩包里直接双击），双击 NewXKY.exe。
2. 首次启动输入软件验证码。每个验证码只能激活一台电脑，可用 40 分钟。
3. 40 分钟内关闭软件后可以重新打开；到期后该验证码失效，需要新的验证码。
4. 框住一道题的滚动区域，把答案窗口移到区域外，点击“开始识别”。
5. 选项不全时自动滚动补全题干与选项，全部核对后显示当前页面的答案字母。
6. 无法完全对应时，用红字标明题库顺序参考；请按选项内容核对。
7. 滚动时会临时将鼠标移入框内；不点击选项或换题按钮。按 Esc 或暂停识别停止。

必须保留 runtime 与 题库 两个文件夹，它们和 NewXKY.exe 是一套的。

如果双击没有反应或提示缺少 DLL，请先双击“运行环境检查.cmd”，它会指出缺少哪个文件。
本程序需要 Windows 10 1809 或更新的 64 位系统。

截图和识别均在本机完成，不上传网络。保留 data 文件夹可恢复上次框选区域。
"""


def write_launchers(app: Path) -> None:
    # cmd.exe parses batch files with the console code page, so a single
    # non-ASCII byte can corrupt the command block on some systems.
    for name, text in (("启动软件.cmd", LAUNCHER_CMD), ("运行环境检查.cmd", CHECKER_CMD)):
        text.encode("ascii")
    (app / "启动软件.cmd").write_text(LAUNCHER_CMD, encoding="ascii", newline="\r\n")
    (app / "运行环境检查.cmd").write_text(CHECKER_CMD, encoding="ascii", newline="\r\n")
    (app / "使用说明.txt").write_text(USAGE_TXT.format(version=VERSION), encoding="utf-8")


def verify_application(app: Path) -> None:
    python = app / "runtime" / "python.exe"
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    checks = [
        ("imports", "import PySide6.QtWidgets, cv2, numpy, PIL.Image, onnxruntime, "
                    "rapidocr_onnxruntime, newxky.ui; print('imports ok')"),
        ("qt", "from PySide6.QtWidgets import QApplication; app=QApplication([]);"
               "from PySide6.QtGui import QIcon; print('qt ok')"),
    ]
    for label, code in checks:
        result = subprocess.run([str(python), "-c", code], cwd=str(app), env=environment,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise SystemExit(f"打包校验失败（{label}）：\n{result.stdout}\n{result.stderr}")


def zip_application(app: Path, output: Path) -> None:
    files = [app / "NewXKY.exe", app / "启动软件.cmd", app / "运行环境检查.cmd",
             app / "使用说明.md", app / "使用说明.txt", app / "THIRD_PARTY_NOTICES.md",
             app / "build-info.json", app / "main.py", app / "portable_start.py"]
    files += sorted((app / "newxky").glob("*.py"))
    files += sorted((app / "assets").glob("*"))
    files += sorted((app / BUNDLE_DIRECTORY).glob("*"))
    files += sorted((app / "runtime").rglob("*"))
    files = [path for path in files if path.is_file()]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + "." + uuid4().hex + ".partial")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6) as archive:
            for path in files:
                archive.write(path, (Path("NewXKY") / path.relative_to(app)).as_posix())
        with zipfile.ZipFile(temporary) as archive:
            assert archive.testzip() is None
            names = set(archive.namelist())
            for required in ("NewXKY/NewXKY.exe", "NewXKY/main.py",
                             f"NewXKY/{BUNDLE_DIRECTORY}/{CACHE_NAME}",
                             "NewXKY/runtime/pythonw.exe"):
                assert required in names, required
            assert not any(name.startswith("NewXKY/data/") or name.endswith("/license.dat")
                           for name in names)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=ROOT / "runtime")
    parser.add_argument("--dist-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--keep-runtime", action="store_true",
                        help="ship the runtime without pruning unused packages")
    parser.add_argument("--reuse", action="store_true",
                        help="重新打包 --dist-root 下已组装好的目录（跳过复制与编译）")
    args = parser.parse_args()

    runtime = args.runtime.resolve()
    check_runtime(runtime)
    manifest = verify_bank()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dist_root = (args.dist_root or (ROOT / "dist" / f"release-runtime-{stamp}")).resolve()
    output = (args.output or (ROOT / "dist" / f"NewXKY-V{VERSION}-Portable.zip")).resolve()
    dist = (ROOT / "dist").resolve()
    if not dist_root.is_relative_to(dist) or not output.is_relative_to(dist):
        parser.error("构建目录与压缩包必须位于项目 dist 目录内")

    app = dist_root / "NewXKY"
    if args.reuse:
        if not (app / "NewXKY.exe").is_file():
            parser.error(f"--reuse 需要已组装好的目录：{app}")
        print("REUSE_APP", flush=True)
    else:
        if app.exists():
            shutil.rmtree(app)
        app.mkdir(parents=True)
        print("COPY_SOURCES", flush=True)
        copy_sources(app)
        print("COPY_RUNTIME", flush=True)
        sizes = copy_runtime(runtime, app / "runtime", keep=args.keep_runtime)
        print("COMPILE_LAUNCHER", flush=True)
        executable = compile_launcher(app)
        write_launchers(app)
    sizes = {
        "bytes_before": sum(file.stat().st_size for file in runtime.rglob("*") if file.is_file()),
        "bytes_after": sum(file.stat().st_size for file in (app / "runtime").rglob("*")
                           if file.is_file()),
    }
    executable = app / "NewXKY.exe"
    executable_info = {
        "name": "NewXKY.exe",
        "format": "C# launcher for the bundled CPython runtime",
        "sha256": digest(executable),
        "size": executable.stat().st_size,
    }
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    (app / "build-info.json").write_text(json.dumps({
        "format": "portable-runtime",
        "product": "NewXKY",
        "version": VERSION,
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "source_revision": revision,
        "source_modified": bool(dirty),
        "python": sys.version.split()[0],
        "license_server_url": str(LICENSE_SERVER_URL or ""),
        "launcher": executable_info,
        "runtime_bytes": sizes,
        "runtime": "pruned" if not args.keep_runtime else "full",
        "pruned_packages": [] if args.keep_runtime else list(PRUNE_PACKAGES),
        "bank": manifest,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("VERIFY_APPLICATION", flush=True)
    verify_application(app)
    print("ZIP", flush=True)
    zip_application(app, output)
    checksum = digest(output)
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{checksum}  {output.name}\n", encoding="utf-8")
    print("PORTABLE_READY", output, output.stat().st_size, checksum, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
