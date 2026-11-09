# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = Path(SPECPATH)
datas = collect_data_files("rapidocr_onnxruntime")
datas += [(str(root / "README.md"), "."), (str(root / "THIRD_PARTY_NOTICES.md"), ".")]
datas += [(str(root / "assets" / "NewXKY.ico"), "assets")]
datas += [(str(root / "题库" / "default-bank.json"), "题库")]

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=collect_dynamic_libs("onnxruntime"),
    datas=datas,
    hiddenimports=["rapidocr_onnxruntime", "PIL", "onnxruntime"],
    excludes=[
        "tkinter", "matplotlib", "IPython", "notebook", "pytest", "torch",
        "tensorflow", "pdfplumber", "pdfminer", "playwright", "ddddocr",
        "websockets", "openpyxl", "cryptography", "pypdfium2",
    ],
    noarchive=False,
)
# Prevent unrelated PATH tools from contributing incompatible versioned ICU DLLs,
# and drop OpenCV's unused video/FFmpeg plugin from this screenshot-only app.
a.binaries = [
    entry for entry in a.binaries
    if Path(entry[0]).name.lower() not in {"icuuc.dll", "icuin.dll", "icudt78.dll"}
    and not Path(entry[0]).name.lower().startswith("opencv_videoio_ffmpeg")
]
# A bundle that misses the UCRT / VC++ runtime or a Qt DLL starts fine on the
# build machine and fails on the customer's with "DLL load failed while
# importing QtCore" or "计算机中丢失 api-ms-win-*.dll". Refuse to build one.
import os as _os
import sys as _sys

_sys.path.insert(0, str(root))
from newxky.runtime_manifest import RUNTIME_FILES

_present = {Path(dest).as_posix().lower() for dest, _source, _kind in a.binaries}
_missing = [name for name in RUNTIME_FILES if name.lower() not in _present]
if _missing:
    _system = Path(_os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    _unresolved = []
    for _name in _missing:
        _source = _system / Path(_name).name
        if "/" not in _name and _source.is_file():
            a.binaries.append((_name, str(_source), "BINARY"))
        else:
            _unresolved.append(_name)
    if _unresolved:
        raise SystemExit(
            "打包缺少运行库文件（在客户电脑上会提示 DLL 缺失）：" + "、".join(_unresolved)
        )
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="NewXKY", console=False,
    upx=False, icon=str(root / "assets" / "NewXKY.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="NewXKY", upx=False)
