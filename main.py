"""NewXKY entry point."""
from __future__ import annotations

import sys
from pathlib import Path


def _frozen_dirs() -> tuple[Path, Path] | None:
    """(bundle dir, app dir) for a packaged build, else ``None``."""
    if not getattr(sys, "frozen", False):
        return None
    bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent / "_internal"))
    return bundle, Path(sys.executable).parent


def _message(text: str, title: str = "NewXKY 启动失败"):
    """Report a startup problem without Qt, which may be exactly what is broken."""
    if sys.platform != "win32":
        print(text, file=sys.stderr)
        return
    import ctypes

    ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)


def _startup_problem() -> str:
    """Explain a broken installation before importing Qt.

    A missing ``_internal`` folder, an antivirus-quarantined DLL or a missing
    Visual C++ runtime all surface as "DLL load failed while importing QtCore"
    or a silent exit, which users cannot act on.
    """
    directories = _frozen_dirs()
    if directories is None:
        return ""
    from newxky.runtime_manifest import startup_problem

    return startup_problem(*directories)


def main():
    import argparse
    from multiprocessing import freeze_support

    freeze_support()
    parser = argparse.ArgumentParser(description="NewXKY 区域答题助手")
    parser.add_argument("--data-dir", help="授权记录和区域设置的保存目录")
    parser.add_argument("--hide-console", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-check", nargs=2, metavar=("IMAGE", "REPORT"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_check:
        from newxky.selfcheck import self_check
        return self_check(*args.self_check)
    problem = _startup_problem()
    if problem:
        _message(problem)
        return 2
    try:
        from newxky.ui import run
    except (ImportError, OSError) as error:
        from newxky.runtime_manifest import RUNTIME_HINT

        if _frozen_dirs() is None:
            raise
        _message(f"无法加载界面组件（Qt/PySide6）：{error}\n\n" + RUNTIME_HINT)
        return 2
    return run(args.data_dir, hide_console=args.hide_console)


if __name__ == "__main__":
    raise SystemExit(main())
