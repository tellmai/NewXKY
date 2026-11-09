"""Files a packaged build must contain.

One list is shared by the frozen application (startup check), the PyInstaller
spec (build-time check) and the packaging script (ZIP-time check), so a build
that would fail on a clean Windows install cannot be shipped.
"""
from __future__ import annotations

from pathlib import Path

# Relative to the PyInstaller bundle directory, which is ``_internal`` for an
# onedir build (``sys._MEIPASS`` in the frozen application).
RUNTIME_FILES = (
    "python311.dll",
    "VCRUNTIME140.dll",
    "VCRUNTIME140_1.dll",
    "MSVCP140.dll",
    "ucrtbase.dll",
    "api-ms-win-core-sysinfo-l1-2-0.dll",
    "api-ms-win-crt-runtime-l1-1-0.dll",
    "PySide6/Qt6Core.dll",
    "PySide6/plugins/platforms/qwindows.dll",
)

# Bundled question bank: inside the bundle directory or next to the executable.
BANK_FILES = ("题库/default-bank.json", "_internal/题库/default-bank.json")

RUNTIME_HINT = (
    "1. 重新解压整个压缩包，保留 _internal 文件夹与“题库”文件夹；不要只复制 NewXKY.exe。\n"
    "2. 不要把程序放在 OneDrive/百度网盘等同步目录里运行，也不要在压缩包里直接双击。\n"
    "3. 安装“Microsoft Visual C++ 2015-2022 运行库（x64）”后重试。\n"
    "4. 提示缺少 api-ms-win-*.dll 时，说明系统版本过低或系统文件被精简，"
    "本程序需要 Windows 10 1809 或更新的 64 位系统。"
)


def missing_runtime(bundle_dir: str | Path) -> list[str]:
    """Runtime files absent from the bundle directory (``_internal``)."""
    bundle = Path(bundle_dir)
    return [name for name in RUNTIME_FILES if not (bundle / name).is_file()]


def missing_bank(app_dir: str | Path) -> list[str]:
    """The question bank is missing from both accepted locations."""
    app = Path(app_dir)
    if any((app / name).is_file() for name in BANK_FILES):
        return []
    return [BANK_FILES[0]]


def startup_problem(bundle_dir: str | Path, app_dir: str | Path) -> str:
    """User-facing explanation for an incomplete installation, or ``""``."""
    missing = missing_runtime(bundle_dir) + missing_bank(app_dir)
    if not missing:
        return ""
    return (
        "程序文件不完整，缺少以下组件：\n  " + "\n  ".join(missing) + "\n\n"
        f"安装位置：{Path(app_dir)}\n\n" + RUNTIME_HINT
    )
