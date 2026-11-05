# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
from importlib.metadata import distributions

root = Path(SPECPATH)
datas = collect_data_files('rapidocr_onnxruntime')
datas += [(str(root / 'README.md'), '.'), (str(root / 'THIRD_PARTY_NOTICES.md'), '.')]
datas += [(str(root / 'assets' / name), 'assets') for name in ('NewXKY.ico', 'chevron-down.svg')]
for distribution in distributions():
    for entry in distribution.files or []:
        parts = tuple(str(part).lower() for part in entry.parts)
        if any(part.endswith('.dist-info') for part in parts) and any('license' in part or part in ('copying', 'notice', 'authors') for part in parts):
            file = Path(distribution.locate_file(entry))
            if file.is_file():
                datas.append((str(file), 'licenses/' + distribution.metadata['Name']))
a = Analysis([str(root / 'main.py')], pathex=[str(root)],
    binaries=collect_dynamic_libs('onnxruntime'), datas=datas,
    hiddenimports=['rapidocr_onnxruntime', 'pdfplumber', 'PIL', 'onnxruntime'],
    excludes=['tkinter', 'matplotlib', 'IPython', 'notebook', 'pytest', 'playwright', 'ddddocr', 'torch', 'tensorflow'],
    noarchive=False)
# Prevent unrelated PATH tools from contributing incompatible versioned ICU DLLs.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in {'icuuc.dll', 'icuin.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='NewXKY', console=False, upx=False,
          icon=str(root / 'assets' / 'NewXKY.ico'))
coll = COLLECT(exe, a.binaries, a.datas, name='NewXKY', upx=False)
