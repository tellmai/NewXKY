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
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="NewXKY", console=False,
    upx=False, icon=str(root / "assets" / "NewXKY.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="NewXKY", upx=False)
