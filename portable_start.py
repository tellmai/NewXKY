"""Desktop entry point with a visible error message if startup fails."""
import argparse
import ctypes
import runpy
import sys
import traceback
from pathlib import Path


def main():
    from newxky.lifetime import startup_allowed
    if not startup_allowed():
        return
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--data-dir", type=Path, default=root / "data")
    args, _ = parser.parse_known_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None or sys.stderr is None:
        log = (args.data_dir / "startup.log").open("a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    try:
        runpy.run_path(str(root / "main.py"), run_name="__main__")
    except SystemExit as error:
        if error.code not in (None, 0):
            raise
    except Exception as error:
        report = args.data_dir / "startup-error.log"
        report.write_text(traceback.format_exc(), encoding="utf-8")
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(None, f"启动失败：{error}\n\n详细记录：{report}", "NewXKY 启动失败", 16)
        else:
            raise


if __name__ == "__main__":
    main()
